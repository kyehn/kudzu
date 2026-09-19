import { execFile } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { promisify } from "node:util";
import {
	type Api,
	type AssistantMessageEventStream,
	type Context,
	type Model,
	type SimpleStreamOptions,
	streamSimple,
} from "@earendil-works/pi-ai/compat";
import { OPENCODE_MODELS } from "@earendil-works/pi-ai/providers/opencode.models";
import type {
	ExtensionAPI,
	ProviderConfig,
	ProviderModelConfig,
} from "@earendil-works/pi-coding-agent";

// Makes Zen requests indistinguishable from the opencode CLI on the wire:
// per-endpoint User-Agent plus x-opencode-project/session/request headers.
// Wire captures live in overlays/maki/opencode/ (opencode-ai 1.18.31).

const BASE_URL = "https://opencode.ai/zen/v1";
const API_KEY = "public";
const OPENCODE_VERSION = "1.18.31";

// Chat-completions captures pin provider-utils 4.0.23, responses 4.0.40.
const USER_AGENT_OPENAI = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`;
const USER_AGENT_RESPONSES = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14`;

type EndpointApi =
	| "anthropic-messages"
	| "google-generative-ai"
	| "openai-completions"
	| "openai-responses";

function userAgentFor(api: EndpointApi): string {
	return api === "openai-completions"
		? USER_AGENT_OPENAI
		: USER_AGENT_RESPONSES;
}

const RANDOM_CHARS =
	"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

let lastTimestamp = 0;
let counter = 0;

// 26-char identifier: 12 hex chars of (timestamp ms << 12 | counter),
// bitwise-NOT'ed when descending, plus 14 random base62 chars.
function identifier(descending: boolean): string {
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

// One descending ses_ id per pi session, reused as prompt_cache_key;
// each request carries a fresh ascending msg_ id.
let sessionId = `ses_${identifier(true)}`;

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

let projectId: string | undefined;

function opencodeHeaders(api: EndpointApi): Record<string, string> {
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

function isFreeModel(id: string): boolean {
	const model = OPENCODE_MODELS[id as keyof typeof OPENCODE_MODELS];
	if (!model) return false;
	return (model.cost?.input ?? 0) === 0 && (model.cost?.output ?? 0) === 0;
}

// Extension routing only calls streamSimple when model.api matches the
// provider default, so the real per-model endpoint lives in this map.
const endpoints = new Map<string, EndpointApi>();

function resolveEndpoint(modelId: string): EndpointApi {
	const api = endpoints.get(modelId);
	if (!api) {
		throw new Error(
			`opencode model ${modelId} was never registered; refusing to guess the endpoint`,
		);
	}
	return api;
}

function buildModelConfig(id: string): ProviderModelConfig {
	const model = OPENCODE_MODELS[id as keyof typeof OPENCODE_MODELS];
	if (!model) {
		throw new Error(
			`opencode model ${id} is not in the built-in catalog; refusing to guess its wire shape`,
		);
	}
	if (model.baseUrl !== BASE_URL) {
		throw new Error(
			`opencode model ${id} baseUrl drifted to ${model.baseUrl}; update BASE_URL routing`,
		);
	}

	endpoints.set(id, model.api as EndpointApi);
	const thinkingLevelMap = (model as Model<Api>).thinkingLevelMap;
	return {
		id,
		name: model.name,
		reasoning: model.reasoning,
		input: model.input,
		cost: model.cost,
		contextWindow: model.contextWindow,
		maxTokens: model.maxTokens,
		...(model.compat ? { compat: model.compat } : {}),
		...(thinkingLevelMap ? { thinkingLevelMap } : {}),
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

function sanitizeZenContext(context: Context, api?: EndpointApi): Context {
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

function streamOpencodeZen(
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
): AssistantMessageEventStream {
	const api = resolveEndpoint(model.id);
	if (model.baseUrl !== BASE_URL) {
		throw new Error(
			`opencode model ${model.id} baseUrl drifted to ${model.baseUrl}; update BASE_URL routing`,
		);
	}
	const wrappedOptions: SimpleStreamOptions = {
		...options,
		headers: { ...options?.headers, ...opencodeHeaders(api) },
		fetch: stripStainlessFetch(api, options?.fetch),
	};
	const wrappedModel = {
		...model,
		api,
		baseUrl: BASE_URL,
	};
	return streamSimple(
		wrappedModel as Model<Api>,
		sanitizeZenContext(context, api),
		wrappedOptions,
	);
}

export default async function (pi: ExtensionAPI): Promise<void> {
	const modelIds = Object.keys(OPENCODE_MODELS).filter(isFreeModel).sort();
	if (modelIds.length === 0) return;
	projectId = await resolveProjectId(process.cwd());
	pi.on("session_start", () => {
		sessionId = `ses_${identifier(true)}`;
	});

	pi.registerProvider("opencode", {
		baseUrl: BASE_URL,
		apiKey: API_KEY,
		api: "openai-completions",
		streamSimple:
			streamOpencodeZen as unknown as ProviderConfig["streamSimple"],
		models: modelIds.map((id) => buildModelConfig(id)),
	});
}
