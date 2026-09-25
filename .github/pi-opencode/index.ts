import {
    createHash,
    randomBytes
} from "node:crypto";
import {
    type Api,
    type Model,
    type Provider,
    type ProviderHeaders,
    type RefreshModelsContext,
    type TranscriptContext,
    createProvider,
} from "@earendil-works/pi-ai";
import {
    opencodeProvider
} from "@earendil-works/pi-ai/providers/opencode";
import type {
    ExtensionAPI,
    ExtensionContext,
} from "@earendil-works/pi-coding-agent";

// Registers pi's `opencode` provider against the opencode zen gateway.
//
// Three concerns, no overlap:
//
//   1. Catalog — a native provider built on pi's own `opencodeProvider()` and
//      pi's `createProvider({ fetchModels })` transaction: pi restores
//      `models-store.json`, throttles and persists, and the only thing this
//      file supplies is the pi.dev fetch plus the free-model policy. The list
//      is never assembled here, so a model published after the last pi release
//      shows up without an extension update.
//   2. Wire identity — zen rejects anything that does not look like the
//      OpenCode CLI, so every request carries the per-endpoint User-Agent, the
//      `x-opencode-*` headers and the SDK-free telemetry profile. The ids are
//      generated with opencode's algorithm, never baked in.
//   3. Transcript — encrypted reasoning blobs and empty tool ids are dropped
//      before dispatch, because the gateway rejects them on replay.
//
// Credentials stay out of this file: `opencodeProvider()` declares
// `OPENCODE_API_KEY` and pi resolves it from `auth.json` before the
// environment, so the bearer lives in pi's credential store only.

const PROVIDER_ID = "opencode";
const CATALOG_URL = "https://pi.dev/api/models/providers/opencode";
const CATALOG_TIMEOUT_MS = 4_000;
// Same freshness window pi's own remote catalog uses; `context.stored` carries
// `checkedAt`, so a session start never costs more than one request per window.
const CATALOG_REFRESH_INTERVAL_MS = 4 * 60 * 60 * 1000;
const ZEN_ORIGIN = "https://opencode.ai/zen";
/** The project scope opencode reports when it has no repository to name. */
const OPENCODE_GLOBAL_PROJECT = "global";
/**
 * Named headers pi's OpenAI/Responses adapters inject when `options.sessionId`
 * is set. opencode's capture contains none of them; the unnamed `x-stainless-*`
 * telemetry is matched by prefix in the fetch wrapper.
 */
const NON_OPENCODE_HEADERS = new Set([
    "x-client-request-id",
    "x-session-affinity",
    "session_id",
]);

// Per-endpoint provider-utils pins: chat-completions 4.0.23, responses 4.0.40,
// anthropic 4.0.46 — the capture table in overlays/maki/README.md.
const OPENCODE_VERSION = "1.18.32";
const USER_AGENT_OPENAI = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`;
const USER_AGENT_RESPONSES = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14`;
const USER_AGENT_ANTHROPIC = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.46 runtime/bun/1.3.14`;

let sessionId = "";
let counter = 0;
let lastTimestamp = 0;

// 26-char identifier, byte for byte what opencode's `iC()` builds: six bytes of
// `(Date.now() * 0x1000 + counter)` taken from the low 48 bits — bit-inverted
// in full for a descending id — as 12 hex chars, then 14 base62 chars drawn
// from a CSPRNG. Never baked in: every request recomputes it.
function identifier(descending: boolean): string {
    const now = Date.now();
    if (now !== lastTimestamp) {
        lastTimestamp = now;
        counter = 0;
    }
    // opencode bumps the counter before reading it, so the first id of a
    // millisecond carries 1; one counter is shared by every id kind.
    counter += 1;
    const packed = (BigInt(now) * 0x1000n + BigInt(counter)) & 0xffffffffffffn;
    const value = descending ? ~packed & 0xffffffffffffn : packed;
    const scope = value.toString(16).padStart(12, "0");
    const alphabet =
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
    const bytes = randomBytes(14);
    let suffix = "";
    for (let i = 0; i < 14; i++) {
        suffix += alphabet[bytes[i] % alphabet.length];
    }
    return scope + suffix;
}

function rotateSession(): void {
    // Descending: opencode restarts the id space when a session begins so every
    // later id of that session sorts before the previous one.
    sessionId = `ses_${identifier(true)}`;
}

function userAgentFor(api: Api): string {
    if (api === "anthropic-messages") return USER_AGENT_ANTHROPIC;
    if (api === "openai-responses") return USER_AGENT_RESPONSES;
    return USER_AGENT_OPENAI;
}

function opencodeHeaders(api: Api): ProviderHeaders {
    return {
        "User-Agent": userAgentFor(api),
        "x-opencode-client": "cli",
        "x-opencode-project": OPENCODE_GLOBAL_PROJECT,
        "x-opencode-session": sessionId,
        "x-opencode-request": `msg_${identifier(false)}`,
    };
}

// opencode's own fetch layer emits none of the AI SDK's `x-stainless-*`
// telemetry and none of pi's session-affinity trio, and zen cannot tell the
// difference; collect the names first, because deleting from a live Headers
// iteration skips the next entry. `options.headers` are merged last, so they
// can override a header but never remove one — this is the only place that
// can.
function stripStainlessFetch(inner: typeof fetch = globalThis.fetch): typeof fetch {
    return (input, init) => {
        const headers = new Headers(
            input instanceof Request ? input.headers : undefined,
        );
        if (init?.headers) {
            new Headers(init.headers).forEach((value, name) =>
                headers.set(name, value),
            );
        }
        const telemetry: string[] = [];
        headers.forEach((_value, name) => {
            const key = name.toLowerCase();
            if (key.startsWith("x-stainless-") || NON_OPENCODE_HEADERS.has(key)) {
                telemetry.push(name);
            }
        });
        for (const name of telemetry) headers.delete(name);
        return inner(input, {
            ...init,
            headers
        });
    };
}

function isFreeZenModel(model: Model < Api > ): boolean {
    return (
        model.cost?.input === 0 &&
        model.cost?.output === 0 &&
        (model.baseUrl ?? ZEN_ORIGIN).startsWith(ZEN_ORIGIN)
    );
}

// pi.dev publishes the registry pi itself reads: a map keyed by model id, but
// accept the array and `{ models }` shapes too so a registry reshuffle fails
// loudly at the HTTP layer instead of silently yielding an empty catalog.
function parseCatalog(payload: unknown): Model < Api > [] {
    let entries: unknown;
    if (Array.isArray(payload)) {
        entries = payload;
    } else if (
        payload !== null &&
        typeof payload === "object" &&
        "models" in payload &&
        Array.isArray((payload as {
            models: unknown
        }).models)
    ) {
        entries = (payload as {
            models: unknown
        }).models;
    } else if (payload !== null && typeof payload === "object") {
        entries = Object.values(payload);
    } else {
        throw new Error(
            `pi.dev catalog: unexpected payload ${JSON.stringify(payload)?.slice(0, 120) ?? typeof payload}`,
        );
    }
    return (entries as Model < Api > []).map((model) => ({
        ...model,
        provider: PROVIDER_ID,
    }));
}

async function fetchZenCatalog(
    context: RefreshModelsContext,
): Promise < readonly Model < Api > [] > {
    const stored = context.stored?.models.filter(
        (model) => model.provider === PROVIDER_ID,
    );
    if (
        !context.force &&
        stored !== undefined &&
        context.stored?.checkedAt !== undefined &&
        Date.now() - context.stored.checkedAt < CATALOG_REFRESH_INTERVAL_MS
    ) {
        return stored;
    }
    const response = await fetch(CATALOG_URL, {
        signal: AbortSignal.any([
            context.signal,
            AbortSignal.timeout(CATALOG_TIMEOUT_MS),
        ]),
    });
    if (!response.ok) {
        throw new Error(`pi.dev catalog: HTTP ${response.status}`);
    }
    // Raw: the stored entry mirrors pi.dev so pi can still read it if the
    // extension is ever uninstalled. Availability is a separate concern and
    // lives on `getModels` below.
    return parseCatalog(await response.json());
}

const COMPLETIONS_REASONING_FIELDS = new Set([
    "reasoning",
    "reasoning_content",
    "reasoning_text",
]);

function hasReasoningPayload(item: Record < string, unknown > ): boolean {
    const summary = item.summary;
    if (Array.isArray(summary) && summary.length > 0) return true;
    const content = item.content;
    if (Array.isArray(content) && content.length > 0) return true;
    if (typeof content === "string" && content.length > 0) return true;
    const text = item.text;
    if (typeof text === "string" && text.length > 0) return true;
    return false;
}

// Drops issuer-bound reasoning blobs the gateway rejects on replay with
// "was not issued to this caller": reasoning.encrypted details and
// encrypted_content plus its cross-turn id. Plaintext summary replays
// cleanly, so only that survives; empty remainders return undefined.
function stripEncryptedSignature(
    signature: string | undefined,
    api ? : Api,
): string | undefined {
    if (!signature) return signature;
    let parsed: unknown;
    try {
        parsed = JSON.parse(signature);
    } catch {
        return COMPLETIONS_REASONING_FIELDS.has(signature) ? signature : undefined;
    }
    if (Array.isArray(parsed)) {
        const kept = parsed.filter(
            (detail) =>
            typeof detail !== "object" ||
            detail === null ||
            (detail as {
                type ? : unknown
            }).type !== "reasoning.encrypted",
        );
        if (kept.length === parsed.length) return signature;
        if (kept.length === 0) return undefined;
        return JSON.stringify(kept);
    }
    if (typeof parsed === "object" && parsed !== null) {
        const record = parsed as Record < string,
            unknown > ;
        if (record.type === "reasoning.encrypted") return undefined;
        if ("encrypted_content" in record) {
            const {
                encrypted_content: _encrypted,
                id: _id,
                ...rest
            } = record;
            void _encrypted;
            void _id;
            if (!hasReasoningPayload(rest)) return undefined;
            return JSON.stringify(rest);
        }
        if (api === "openai-responses" && typeof record.id === "string") {
            const {
                id: _id,
                ...rest
            } = record;
            void _id;
            if (!hasReasoningPayload(rest)) return undefined;
            return JSON.stringify(rest);
        }
        return signature;
    }
    return signature;
}

// Same normalization the host applies: an id collapsing to empty fails the
// gateway with "call_id length must be >= 1", so repair it deterministically.
function isEmptyCallIdPart(callId: string): boolean {
    const sanitized = callId
        .replace(/[^a-zA-Z0-9_-]/g, "_")
        .slice(0, 64)
        .replace(/_+$/, "");
    return sanitized.length === 0;
}

function fallbackCallId(seed: string): string {
    return `call_repaired_${createHash("sha1").update(seed).digest("hex").slice(0, 8)}`;
}

function repairToolId(
    fullId: string,
    seedHint: string,
    repairs: Map < string, string > ,
    index: number,
): string {
    const cached = repairs.get(fullId);
    if (cached) return cached;
    const separator = fullId.indexOf("|");
    const callId = separator === -1 ? fullId : fullId.slice(0, separator);
    const itemPart = separator === -1 ? "" : fullId.slice(separator + 1);
    if (!isEmptyCallIdPart(callId)) return fullId;
    const repairedCall = fallbackCallId(`${seedHint}:${index}:${fullId}`);
    const repaired = itemPart ? `${repairedCall}|${itemPart}` : repairedCall;
    repairs.set(fullId, repaired);
    return repaired;
}

function sanitizeZenContext(
    context: TranscriptContext,
    api ? : Api,
): TranscriptContext {
    const repairs = new Map < string,
        string > ();
    let toolIndex = 0;
    let changed = false;
    const messages = context.messages.map((message) => {
        if (message.role === "assistant") {
            let messageChanged = false;
            const content: typeof message.content = [];
            for (const block of message.content) {
                if (block.type === "thinking") {
                    if (block.redacted) {
                        if (!block.thinking || block.thinking.trim() === "") {
                            messageChanged = true;
                            continue;
                        }
                        messageChanged = true;
                        content.push({
                            type: "text",
                            text: block.thinking
                        });
                        continue;
                    }
                    if (typeof block.thinkingSignature === "string") {
                        const stripped = stripEncryptedSignature(
                            block.thinkingSignature,
                            api,
                        );
                        if (stripped !== block.thinkingSignature) {
                            messageChanged = true;
                            if (
                                stripped === undefined &&
                                (!block.thinking || block.thinking.trim() === "")
                            ) {
                                continue;
                            }
                            content.push({
                                ...block,
                                thinkingSignature: stripped
                            });
                            continue;
                        }
                    }
                    content.push(block);
                } else if (block.type === "toolCall") {
                    let nextBlock = block;
                    if (typeof block.thoughtSignature === "string") {
                        const stripped = stripEncryptedSignature(
                            block.thoughtSignature,
                            api,
                        );
                        if (stripped !== block.thoughtSignature) {
                            messageChanged = true;
                            nextBlock = {
                                ...nextBlock,
                                thoughtSignature: stripped
                            };
                        }
                    }
                    const repairedId = repairToolId(
                        block.id,
                        `${block.name}:${JSON.stringify(block.arguments)}`,
                        repairs,
                        toolIndex++,
                    );
                    if (repairedId !== block.id) {
                        messageChanged = true;
                        nextBlock = {
                            ...nextBlock,
                            id: repairedId
                        };
                    }
                    content.push(nextBlock);
                } else {
                    content.push(block);
                }
            }
            if (!messageChanged) return message;
            changed = true;
            return {
                ...message,
                content
            };
        }
        if (message.role === "toolResult") {
            const repairedId = repairToolId(
                message.toolCallId,
                `${message.toolName}:${message.toolCallId}`,
                repairs,
                toolIndex++,
            );
            if (repairedId !== message.toolCallId) {
                changed = true;
                return {
                    ...message,
                    toolCallId: repairedId
                };
            }
            return message;
        }
        return message;
    });
    if (!changed) return context;
    return {
        ...context,
        messages
    };
}

// Headers plus the fetch layer, applied at the only point that knows both the
// request's real api (for the right User-Agent) and the options object that
// pi's own `withOpenCodeSessionHeader` will consult before overwriting.
function wireRequest(
    model: Model < Api > ,
    options:
    |
    {
        headers ? : ProviderHeaders;fetch ? : typeof globalThis.fetch
    } |
    undefined,
) {
    return {
        headers: {
            ...options?.headers,
            ...opencodeHeaders(model.api)
        },
        fetch: stripStainlessFetch(options?.fetch),
    };
}

// pi owns every refresh pass; this only reports failures instead of letting
// them die inside the registry's error map.
async function onSessionStart(ctx: ExtensionContext): Promise < void > {
    rotateSession();
    const {
        errors
    } = await ctx.modelRegistry.refresh({
        providers: [PROVIDER_ID],
        allowNetwork: true,
    });
    for (const [providerId, error] of errors) {
        console.warn(
            `pi-opencode: model refresh for ${providerId} failed: ${error.message}`,
        );
    }
}

export default async function(pi: ExtensionAPI): Promise < void > {
    // The builtin carries pi's model metadata and every stream implementation;
    // only its catalog and wire behavior are replaced.
    const builtin = opencodeProvider() as Provider < Api > ;
    if (builtin.getModels().filter(isFreeZenModel).length === 0) {
        // The bundled catalog is pi's own build data; an empty free projection
        // is a bug, and registering an unusable provider would hide it until
        // the first request failed.
        throw new Error(
            "pi-opencode: bundled catalog carries no free zen model; refusing to register an unusable provider",
        );
    }
    pi.on("session_start", (_event, ctx) => onSessionStart(ctx));
    const provider = createProvider < Api > ({
        id: PROVIDER_ID,
        name: builtin.name,
        auth: builtin.auth,
        models: builtin.getModels(),
        fetchModels: fetchZenCatalog,
        api: {
            stream: (model, context, options) =>
                builtin.stream(model, sanitizeZenContext(context, model.api), {
                    ...options,
                    ...wireRequest(model, options),
                }),
            streamSimple: (model, context, options) =>
                builtin.streamSimple(model, sanitizeZenContext(context, model.api), {
                    ...options,
                    ...wireRequest(model, options),
                }),
        },
    });
    pi.registerProvider({
        ...provider,
        // pi merges the bundled catalog with its pi.dev entry; the merged list
        // is then cut down to what the anonymous zen key can actually buy, so
        // every surface (list, picker, request lookup) sees the same set.
        getModels: () => provider.getModels().filter(isFreeZenModel),
    });
}