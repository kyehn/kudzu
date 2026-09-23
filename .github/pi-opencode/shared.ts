import { execFile } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import type {
	Api,
	AssistantMessageEventStream,
	Context,
	Model,
	SimpleStreamOptions,
} from "@earendil-works/pi-ai/compat";

// Makes Zen requests indistinguishable from the opencode CLI on the wire:
// per-endpoint User-Agent plus x-opencode-project/session/request headers.
// Wire captures live in overlays/maki/opencode/; version and per-endpoint
// User-Agent pins follow overlays/maki/README.md and providers-config.py.
// This module is host-neutral: pi.ts (pi, node) and omp.ts (omp, bun) share
// it verbatim, and only the catalog/registration seams differ per host.

const ZEN_ORIGIN = "https://opencode.ai/zen";
const BASE_URL = "https://opencode.ai/zen/v1";
const API_KEY = "public";
const OPENCODE_VERSION = "1.18.32";

// Per-endpoint provider-utils pins: chat-completions 4.0.23, responses
// 4.0.40, anthropic 4.0.46.
const USER_AGENT_OPENAI = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`;
const USER_AGENT_RESPONSES = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14`;
const USER_AGENT_ANTHROPIC = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.46 runtime/bun/1.3.14`;

export { API_KEY, BASE_URL, ZEN_ORIGIN };

// Endpoints this extension is wired for; a new api from the dynamic catalog
// must be added explicitly — guessing would put the request on the wrong wire.
const ENDPOINTS = [
	"anthropic-messages",
	"google-generative-ai",
	"openai-completions",
	"openai-responses",
] as const;
export type EndpointApi = (typeof ENDPOINTS)[number];

export function isEndpointApi(api: unknown): api is EndpointApi {
	return (
		typeof api === "string" && (ENDPOINTS as readonly string[]).includes(api)
	);
}

function userAgentFor(api: EndpointApi): string {
	if (api === "openai-completions") return USER_AGENT_OPENAI;
	if (api === "anthropic-messages") return USER_AGENT_ANTHROPIC;
	return USER_AGENT_RESPONSES;
}

const RANDOM_CHARS =
	"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

let lastTimestamp = 0;
let counter = 0;

// 26-char identifier: 12 hex chars of (timestamp ms << 12 | counter),
// bitwise-NOT'ed when descending, plus 14 random base62 chars.
export function identifier(descending: boolean): string {
	const now = Date.now();
	if (now !== lastTimestamp) {
		lastTimestamp = now;
		counter = 0;
	}
	counter++;

	const current = BigInt(now) * 0x1000n + BigInt(counter);
	const value = descending ? ~current : current;
	const time = Array.from({ length: 6 }, (_, index) =>
		Number((value >> BigInt(40 - 8 * index)) & 0xffn)
			.toString(16)
			.padStart(2, "0"),
	).join("");
	return (
		time +
		Array.from(randomBytes(14), (byte) => RANDOM_CHARS[byte % 62]).join("")
	);
}

// One descending ses_ id per session, reused as prompt_cache_key; each
// request carries a fresh ascending msg_ id.
let sessionId = `ses_${identifier(true)}`;
let projectId: string | undefined;

// Entries call this once at boot with their cwd; session_start rotates the
// session id via rotateSession.
export async function initProject(cwd: string): Promise<void> {
	projectId = await resolveProjectId(cwd);
}

export function rotateSession(): void {
	sessionId = `ses_${identifier(true)}`;
}

async function gitOut(cwd: string, args: string[]): Promise<string | null> {
	try {
		const { stdout } = await promisify(execFile)("git", args, {
			cwd,
			maxBuffer: 1024 * 1024,
		});
		return stdout.trim() || null;
	} catch {
		return null;
	}
}

function normalizeRemote(value: string): string | undefined {
	const trimmed = value.trim();
	if (!trimmed) return undefined;
	const parts = (host: string, name: string): string | undefined => {
		const pathname = name
			.replace(/^\/+/, "")
			.replace(/\.git\/?$/, "")
			.replace(/\/+$/, "");
		if (!host || !pathname) return undefined;
		return `${host.toLowerCase()}/${pathname}`;
	};
	try {
		const parsed = new URL(trimmed);
		if (parsed.protocol === "file:") return undefined;
		return parts(parsed.hostname, parsed.pathname);
	} catch {
		const scp = trimmed.match(/^([^@/:]+@)?([^/:]+):(.+)$/);
		const host = scp?.[2];
		const name = scp?.[3];
		if (host && name) return parts(host, name);
		return undefined;
	}
}

// Project id priority: remote URL hash -> cached <common-dir>/opencode file
// -> first root commit hash -> "global".
async function resolveProjectId(cwd: string): Promise<string> {
	const commonDirRaw = await gitOut(cwd, ["rev-parse", "--git-common-dir"]);
	if (!commonDirRaw) return "global";
	const commonDir = path.isAbsolute(commonDirRaw)
		? commonDirRaw
		: path.resolve(cwd, commonDirRaw);

	const origin = await gitOut(cwd, ["remote", "get-url", "origin"]);
	const normalized = origin ? normalizeRemote(origin) : undefined;
	if (normalized) {
		return createHash("sha1").update(`git-remote:${normalized}`).digest("hex");
	}

	try {
		const cached = (
			await readFile(path.join(commonDir, "opencode"), "utf8")
		).trim();
		if (cached) return cached;
	} catch {
		// No cached id; fall through to root commit.
	}

	const roots = await gitOut(cwd, ["rev-list", "--max-parents=0", "HEAD"]);
	const firstRoot = roots
		? roots
				.split("\n")
				.map((line) => line.trim())
				.filter(Boolean)
				.sort()[0]
		: undefined;
	return firstRoot ?? "global";
}

export function opencodeHeaders(api: EndpointApi): Record<string, string> {
	return {
		"User-Agent": userAgentFor(api),
		"x-opencode-client": "cli",
		"x-opencode-project": projectId ?? "global",
		"x-opencode-session": sessionId,
		"x-opencode-request": `msg_${identifier(false)}`,
	};
}

// The SDK clients stamp X-Stainless-* telemetry headers the CLI never sends;
// strip them and pin the User-Agent behind opencodeHeaders().
function stripStainlessFetch(
	api: EndpointApi,
	inner: typeof globalThis.fetch = globalThis.fetch,
): typeof globalThis.fetch {
	const userAgent = userAgentFor(api);
	return (async (...args: Parameters<typeof globalThis.fetch>) => {
		const [input, init] = args;
		const headers = new Headers(init?.headers);
		headers.forEach((_value, name) => {
			if (name.toLowerCase().startsWith("x-stainless-")) headers.delete(name);
		});
		headers.set("User-Agent", userAgent);
		return inner(input, { ...init, headers });
	}) as typeof globalThis.fetch;
}

// Only free models surface — both cost legs must be zero, the same rule
// overlays/maki/providers-config.py applies to the models.dev catalog.
export function isFreeModel(entry: {
	cost?: { input?: number; output?: number };
}): boolean {
	return (entry.cost?.input ?? 0) === 0 && (entry.cost?.output ?? 0) === 0;
}

// Hosts register models without the per-model api (pi routes to a custom
// streamSimple only when model.api matches the provider default; omp
// reserves the built-in api names), so the real per-model endpoint lives
// in this map, filled by each entry's builder at registration time.
export const endpoints = new Map<
	string,
	{ api: EndpointApi; baseUrl: string; compat: unknown }
>();

function resolveEndpoint(modelId: string): {
	api: EndpointApi;
	baseUrl: string;
	compat: unknown;
} {
	const endpoint = endpoints.get(modelId);
	if (!endpoint) {
		throw new Error(
			`opencode model ${modelId} was never registered; refusing to guess the endpoint`,
		);
	}
	return endpoint;
}

// Ids upstream registry sources retired but the gateway /models list still
// carries: deprecated on models.dev (mimo-v2.5-free), dead upstream
// (deepseek-v4-flash-free), and never free-listed upstream at all
// (jev-1.13-free). The registry-source filters cannot re-add them, but the
// offline bundled-snapshot fallback never reaches a registry, so this set is
// enforced inside the gate — the one chokepoint every catalog path crosses.
const RETIRED_ZEN_IDS: ReadonlySet<string> = new Set([
	"deepseek-v4-flash-free",
	"jev-1.13-free",
	"mimo-v2.5-free",
]);

// Live gateway ids gate the catalog, mirroring
// overlays/maki/providers-config.py: a model retired from the gateway
// (absent from the official /models list) must never surface, unknown
// live ids never inject models the host catalog does not know, and
// permanently-retired ids drop on every path (including offline). Any
// fetch/shape failure falls back to the eligible free catalog so boot never
// depends on the network.
const GATE_ATTEMPT_TIMEOUT_MS = 4_000;

export async function gateByLive<T extends { id: string }>(
	models: T[],
	fetchImpl: typeof globalThis.fetch = globalThis.fetch,
): Promise<T[]> {
	const eligible = models.filter((model) => !RETIRED_ZEN_IDS.has(model.id));
	let response: Response;
	try {
		response = await fetchImpl(`${BASE_URL}/models`, {
			headers: { "User-Agent": USER_AGENT_OPENAI },
			signal: AbortSignal.timeout(GATE_ATTEMPT_TIMEOUT_MS),
		});
	} catch {
		return eligible;
	}
	if (!response.ok) return eligible;
	let payload: unknown;
	try {
		payload = await response.json();
	} catch {
		return eligible;
	}
	if (typeof payload !== "object" || payload === null || !("data" in payload)) {
		return eligible;
	}
	const ids: unknown = payload.data;
	if (!Array.isArray(ids)) return eligible;
	const live = new Set(
		ids.flatMap((item) =>
			typeof (item as { id?: unknown })?.id === "string"
				? [(item as { id: string }).id]
				: [],
		),
	);
	if (live.size === 0) return eligible;
	const gated = eligible.filter((model) => live.has(model.id));
	return gated.length > 0 ? gated : eligible;
}

// pi.dev publishes the opencode provider registry — the same endpoint the
// host's withRemoteCatalog refreshes from — and both hosts read it as the
// authoritative free-model list: it surfaces newly published free models
// and never carries ids deprecated upstream.
const PI_CATALOG_URL = "https://pi.dev/api/models/providers/opencode";
export const REMOTE_CATALOG_ATTEMPT_TIMEOUT_MS = 4_000;

// Every pi.dev/store record is re-validated: an entry this extension cannot
// route is skipped instead of taking the whole provider down with it. Only
// actionable entries warn: well-formed models for another route (e.g. paid
// anthropic-messages models on the bare /zen baseUrl) can never surface
// through the free filter, so they skip silently, while a free-but-unroutable
// or malformed entry warns.
export function normalizeZenModel(
	value: unknown,
	source: string,
): Model<Api> | undefined {
	if (typeof value !== "object" || value === null) {
		console.warn(`pi-opencode: ${source} is not an object; skipping`);
		return undefined;
	}
	const entry = value as Record<string, unknown>;
	if (!isEndpointApi(entry.api)) {
		console.warn(
			`pi-opencode: ${source} ${String(entry.id)} has unknown api ${String(entry.api)}; skipping`,
		);
		return undefined;
	}
	const cost =
		typeof entry.cost === "object" && entry.cost !== null
			? (entry.cost as Record<string, unknown>)
			: undefined;
	// Paid entries never survive the free filter; skip them before the
	// remaining checks so routine paid models stay out of the logs.
	if (
		cost !== undefined &&
		typeof cost.input === "number" &&
		typeof cost.output === "number" &&
		(cost.input !== 0 || cost.output !== 0)
	) {
		return undefined;
	}
	if (
		typeof entry.id !== "string" ||
		typeof entry.name !== "string" ||
		typeof entry.reasoning !== "boolean" ||
		entry.baseUrl !== BASE_URL ||
		!Array.isArray(entry.input) ||
		!entry.input.every((item) => item === "text" || item === "image") ||
		typeof entry.contextWindow !== "number" ||
		typeof entry.maxTokens !== "number" ||
		cost === undefined ||
		typeof cost.input !== "number" ||
		typeof cost.output !== "number" ||
		typeof cost.cacheRead !== "number" ||
		typeof cost.cacheWrite !== "number"
	) {
		console.warn(
			`pi-opencode: ${source} ${String(entry.id)} failed validation (id/name/reasoning/api/baseUrl/input/cost/limits); skipping`,
		);
		return undefined;
	}
	// Required fields are validated above; optional fields (compat,
	// inputLimits, thinkingLevelMap, ...) pass through verbatim, exactly like
	// the host's own catalog loader.
	return { ...entry, provider: "opencode" } as Model<Api>;
}

// Live pi.dev records, same endpoint and validator protocol the host's
// withRemoteCatalog uses. The catalog is a map keyed by id; unknown shapes
// fall back to undefined so boot never depends on the network.
export async function fetchRemoteCatalog(
	etag: string | undefined,
	signal: AbortSignal,
	fetchImpl: typeof globalThis.fetch = globalThis.fetch,
): Promise<
	| {
			status: "fresh";
			models: Model<Api>[];
			lastModified: number;
			etag?: string;
	  }
	| { status: "revalidated" }
	| undefined
> {
	let response: Response;
	try {
		response = await fetchImpl(PI_CATALOG_URL, {
			headers: {
				accept: "application/json",
				"User-Agent": USER_AGENT_OPENAI,
				...(etag ? { "if-none-match": etag } : {}),
			},
			signal,
		});
	} catch {
		return undefined;
	}
	if (response.status === 304) return { status: "revalidated" };
	if (!response.ok) return undefined;
	let payload: unknown;
	try {
		payload = await response.json();
	} catch {
		return undefined;
	}
	let raw: unknown;
	if (Array.isArray(payload)) {
		raw = payload;
	} else if (typeof payload === "object" && payload !== null) {
		raw =
			"models" in payload && Array.isArray(payload.models)
				? payload.models
				: Object.values(payload);
	} else {
		raw = undefined;
	}
	if (!Array.isArray(raw)) return undefined;
	const lastModified = Date.parse(response.headers.get("last-modified") ?? "");
	return {
		status: "fresh",
		models: raw
			.map((model) => normalizeZenModel(model, "pi.dev entry"))
			.filter((model): model is Model<Api> => model !== undefined),
		lastModified: Number.isNaN(lastModified) ? 0 : lastModified,
		etag: response.headers.get("etag") ?? undefined,
	};
}

const COMPLETIONS_REASONING_FIELDS = new Set([
	"reasoning",
	"reasoning_content",
	"reasoning_text",
]);

function hasReasoningPayload(item: Record<string, unknown>): boolean {
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
	api?: EndpointApi,
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
				(detail as { type?: unknown }).type !== "reasoning.encrypted",
		);
		if (kept.length === parsed.length) return signature;
		if (kept.length === 0) return undefined;
		return JSON.stringify(kept);
	}
	if (typeof parsed === "object" && parsed !== null) {
		const record = parsed as Record<string, unknown>;
		if (record.type === "reasoning.encrypted") return undefined;
		if ("encrypted_content" in record) {
			const { encrypted_content: _encrypted, id: _id, ...rest } = record;
			void _encrypted;
			void _id;
			if (!hasReasoningPayload(rest)) return undefined;
			return JSON.stringify(rest);
		}
		if (api === "openai-responses" && typeof record.id === "string") {
			const { id: _id, ...rest } = record;
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
	repairs: Map<string, string>,
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

export function sanitizeZenContext(
	context: Context,
	api?: EndpointApi,
): Context {
	const repairs = new Map<string, string>();
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
						content.push({ type: "text", text: block.thinking });
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
							content.push({ ...block, thinkingSignature: stripped });
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
							nextBlock = { ...nextBlock, thoughtSignature: stripped };
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
						nextBlock = { ...nextBlock, id: repairedId };
					}
					content.push(nextBlock);
				} else {
					content.push(block);
				}
			}
			if (!messageChanged) return message;
			changed = true;
			return { ...message, content };
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
				return { ...message, toolCallId: repairedId };
			}
			return message;
		}
		return message;
	});
	if (!changed) return context;
	return { ...context, messages };
}

type ZenStreamer = (
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
) => AssistantMessageEventStream;

// Each host passes its own streamSimple (pi from @earendil-works/pi-ai/compat,
// omp from @oh-my-pi/pi-ai); the wire wrapping around it is identical.
export function makeZenStreamer(streamSimple: ZenStreamer): ZenStreamer {
	return (model, context, options) => {
		const endpoint = resolveEndpoint(model.id);
		if (!endpoint.baseUrl.startsWith(ZEN_ORIGIN)) {
			throw new Error(
				`opencode model ${model.id} baseUrl left ${ZEN_ORIGIN}: ${endpoint.baseUrl}`,
			);
		}
		const wrappedOptions: SimpleStreamOptions = {
			...options,
			headers: { ...options?.headers, ...opencodeHeaders(endpoint.api) },
			fetch: stripStainlessFetch(endpoint.api, options?.fetch),
		};
		const wrappedModel = {
			...model,
			api: endpoint.api,
			baseUrl: endpoint.baseUrl,
			compat: endpoint.compat,
		};
		return streamSimple(
			wrappedModel as Model<Api>,
			sanitizeZenContext(context, endpoint.api),
			wrappedOptions,
		);
	};
}
