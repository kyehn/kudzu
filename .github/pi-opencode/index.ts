/**
 * pi extension that makes requests to OpenCode Zen indistinguishable from the
 * real opencode CLI on the wire: User-Agent plus the x-opencode headers.
 *
 * Sources mirrored (opencode-ai v1.18.31:
 *   - packages/schema/src/identifier.ts
 *     (ses_ descending / msg_ ascending, 12 hex time chars + 14 base62 chars)
 *   - packages/opencode/src/session/llm/request.ts (USER_AGENT
 *     `opencode/${InstallationVersion}` plus ai-sdk suffix on the wire;
 *     opencode provider → x-opencode-project/session/request/client only,
 *     other providers → x-session-affinity/X-Session-Id only)
 *   - packages/opencode/src/installation/index.ts (userAgent():
 *     `opencode/${channel}/${version}/${client}` for models.dev)
 *   - packages/core/src/project.ts (remote → cached → root, sha1
 *     "git-remote:<host/path>", "global" fallback)
 *
 * Wire captures (overlays/reasonix/opencode/): chat-completions wires carry
 * `ai-sdk/provider-utils/4.0.23`, responses wires carry `4.0.40` under the
 * same `opencode/1.18.31 ... runtime/bun/1.3.14` prefix, so the User-Agent is
 * selected per endpoint instead of a single constant.
 *
 * Reliability: history replay never carries the issuer-bound reasoning
 * `encrypted_content` blob (responses `thinkingSignature` object /
 * completions `reasoning.encrypted` detail / legacy `thoughtSignature`).
 * The Console gateway 400s a replayed blob with "was not issued to this
 * caller" once a different caller serves the turn; plaintext summary alone
 * replays cleanly (reasonix responses retry proof), so sanitizeZenContext()
 * strips the blob proactively before streamSimple. Empty `call_id` items are
 * repaired deterministically for the same reason: the Responses gateway
 * 400s `input[N].call_id` with "length must be >= 1" once a normalized id
 * collapses to empty, so the sanitizer never lets an empty call_id reach
 * the wire.
 */
import { execFile } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
// 显式导入而非依赖全局 process：类型解析不再依赖环境自动发现 @types/node。
import process from "node:process";
import { promisify } from "node:util";
// Import from the compat entrypoint: the host aliases extension imports of
// "@earendil-works/pi-ai/compat" to its bundled copy (loader.js), and this
// surface exposes the api-dispatching streamSimple that routes by model.api —
// one call covers all four wire protocols without per-protocol imports.
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

const BASE_URL = "https://opencode.ai/zen/v1";
const API_KEY = "public";
const OPENCODE_VERSION = "1.18.31";

// ─── opencode wire identity ─────────────────────────────────────────────────

// request.ts: `opencode/${InstallationVersion}` as the base; the ai-sdk
// provider-utils fetch wrapper appends ` ai-sdk/provider-utils/<v>
// runtime/bun/<v>` on the wire. Real captures diverge per endpoint:
// chat-completions → 4.0.23, responses → 4.0.40 (same opencode/1.18.31 prefix).
const USER_AGENT_OPENAI = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`;
const USER_AGENT_RESPONSES = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14`;

type EndpointApi =
	| "anthropic-messages"
	| "google-generative-ai"
	| "openai-completions"
	| "openai-responses";

/** Per-endpoint User-Agent: chat-completions capture pins 4.0.23, responses
 * capture pins 4.0.40; non-free anthropic/google wires have no free capture
 * and follow the responses suffix. */
function userAgentFor(api: EndpointApi): string {
	return api === "openai-completions"
		? USER_AGENT_OPENAI
		: USER_AGENT_RESPONSES;
}

// ─── opencode identifiers (packages/schema/src/identifier.ts) ───────────────

const RANDOM_CHARS =
	"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

let lastTimestamp = 0;
let counter = 0;

/**
 * 26-char identifier: 12 hex chars encoding (timestamp ms << 12 | counter),
 * bitwise-NOT'ed when descending so newer IDs sort larger, plus 14 random
 * base62 chars.
 */
function identifier(descending: boolean): string {
	const now = Date.now();
	if (now !== lastTimestamp) {
		lastTimestamp = now;
		counter = 0;
	}
	counter++;

	const current = BigInt(now) * 0x1000n + BigInt(counter);
	const value = descending ? ~current : current;
	const time = Array.from({ length: 6 }, (_, i) =>
		Number((value >> BigInt(40 - 8 * i)) & 0xffn)
			.toString(16)
			.padStart(2, "0"),
	).join("");
	const bytes = randomBytes(14);
	return time + Array.from(bytes, (b) => RANDOM_CHARS[b % 62]).join("");
}

// Sessions use the descending encoding, one ses_ ID per pi session stamped
// on x-opencode-session and reused as prompt_cache_key — like the CLI reusing
// one ses_ ID per session. Each request carries a fresh ascending msg_ ID on
// x-opencode-request (SessionMessage ID). Rotated on session_start so separate
// pi conversations do not share a session ID like separate `opencode run`
// invocations do not (captured ses_ differ per run).
let sessionId = `ses_${identifier(true)}`;

// ─── x-opencode-project (packages/core/src/project.ts) ─────────────────────

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

/** Lexicographic order by UTF-16 code units (matches git/opencode sorting). */
function compareStrings(a: string, b: string): number {
	if (a === b) return 0;
	return a < b ? -1 : 1;
}

/** Mirrors opencode's remote URL normalization (host/path, no .git suffix). */
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

async function resolveProjectId(cwd: string): Promise<string> {
	const commonDirRaw = await gitOut(cwd, ["rev-parse", "--git-common-dir"]);
	if (!commonDirRaw) return "global";
	const commonDir = path.isAbsolute(commonDirRaw)
		? commonDirRaw
		: path.resolve(cwd, commonDirRaw);

	// opencode resolves project ID with priority: remote → cached → root.
	// remote(): normalize remote URL → sha1("git-remote:<normalized>")
	// cached(): read <common-dir>/opencode file
	// root(): first root commit hash (sorted lexicographically)

	// 1. Try remote URL first (highest priority).
	const origin = await gitOut(cwd, ["remote", "get-url", "origin"]);
	const normalized = origin ? normalizeRemote(origin) : undefined;
	if (normalized) {
		return createHash("sha1").update(`git-remote:${normalized}`).digest("hex");
	}

	// 2. Try cached ID from <common-dir>/opencode.
	try {
		const cached = (
			await readFile(path.join(commonDir, "opencode"), "utf8")
		).trim();
		if (cached) return cached;
	} catch {
		// No cached id; fall through to root commit.
	}

	// 3. Repos without an origin fall back to their root commit hash.
	// opencode sorts root hashes and takes the first for determinism.
	const roots = await gitOut(cwd, ["rev-list", "--max-parents=0", "HEAD"]);
	const firstRoot = roots
		? roots
				.split("\n")
				.map((line) => line.trim())
				.filter(Boolean)
				.sort(compareStrings)[0]
		: undefined;
	return firstRoot ?? "global";
}

// Resolved once at bootstrap, before any request can be built.
let projectId: string | undefined;

function getProjectId(): string {
	return projectId ?? "global";
}

// ─── request headers (packages/opencode/src/session/llm/request.ts) ─────────
// opencode provider → x-opencode-* only (no x-session-affinity/X-Session-Id;
// those are for non-opencode providers). x-opencode-request is a fresh
// ascending msg_ ID per request (SessionMessage ID), not the session ID.

function opencodeHeaders(api: EndpointApi): Record<string, string> {
	return {
		"User-Agent": userAgentFor(api),
		"x-opencode-client": "cli",
		"x-opencode-project": getProjectId(),
		"x-opencode-session": sessionId,
		"x-opencode-request": `msg_${identifier(false)}`,
	};
}

// The openai / @anthropic-ai SDK clients stamp X-Stainless-* telemetry
// headers the real CLI never sends (local echo proof: 8 headers — Lang,
// Package-Version, OS, Arch, Runtime, Runtime-Version, Retry-Count, Timeout).
// SimpleStreamOptions.fetch allows a custom fetch, so strip them on the wire
// and pin the User-Agent as a second lock behind opencodeHeaders().

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

// ─── bootstrap: discover free models from pi built-in catalog ───────────────

function isFreeModel(id: string): boolean {
	const model = OPENCODE_MODELS[id as keyof typeof OPENCODE_MODELS];
	if (!model) return false;
	return (model.cost?.input ?? 0) === 0 && (model.cost?.output ?? 0) === 0;
}

function loadModelIds(): string[] {
	return Object.keys(OPENCODE_MODELS).filter(isFreeModel).sort(compareStrings);
}

// ─── model catalog ──────────────────────────────────────────────────────────

// Routing through streamSimple requires model.api === extension.api, so every
// registered model carries the provider default ("openai-completions"); the
// real per-model endpoint lives in this map instead.
const endpoints = new Map<string, EndpointApi>();

export function resolveEndpoint(modelId: string): EndpointApi {
	const api = endpoints.get(modelId);
	if (!api) {
		// fail-closed: 未注册模型静默 default 会把请求送错 wire;
		// 调用方只应传入 buildModelConfig 注册过的 id。
		throw new Error(
			`opencode model ${modelId} was never registered; refusing to guess the endpoint`,
		);
	}
	return api;
}

const ZEN_BASE_URLS = [BASE_URL, "https://opencode.ai/zen"];

/** pi 目录里出现过的合法 zen 根 (live 实证 2026-09-17: /zen/v1 54 族 + 裸 /zen 14 族, 后者当前全付费)。 */
export function isKnownZenBaseUrl(url: string): boolean {
	return ZEN_BASE_URLS.includes(url);
}

function catalogBaseUrlOf(model: Model<Api>): string {
	return "baseUrl" in model && typeof model.baseUrl === "string"
		? model.baseUrl
		: BASE_URL;
}

export function buildModelConfig(id: string): ProviderModelConfig {
	const model = OPENCODE_MODELS[id as keyof typeof OPENCODE_MODELS];
	if (!model) {
		throw new Error(
			`opencode model ${id} is not in the built-in catalog; refusing to guess its wire shape`,
		);
	}
	// 各模型的权威 baseUrl 在 pi 目录里: anthropic-messages 族走裸 /zen
	// (live 实证, 当前全为付费模型故不进免费集), 其余走 /zen/v1。
	// 目录一旦漂移到未知根必须大声报错而非静默错路。
	const rawBaseUrl =
		"baseUrl" in model && typeof model.baseUrl === "string"
			? model.baseUrl
			: BASE_URL;
	if (!isKnownZenBaseUrl(rawBaseUrl)) {
		throw new Error(
			`opencode model ${id} baseUrl drifted to ${rawBaseUrl}; update BASE_URL routing`,
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

// ─── history sanitizing (Console 400 fixes) ─────────────────────────────────
// Two issuer-bound failure modes share one proactive pass before streamSimple:
//
// 1. reasoning `encrypted_content` was not issued to this caller — muse-spark
//    等 responses 模型回放上一轮 reasoning 时会带上 issuer 绑定的 opaque
//    `encrypted_content` (pi-ai 存在 thinking.thinkingSignature, completions
//    通道是 reasoning_details 数组里的 reasoning.encrypted 项 /
//    toolCall.thoughtSignature 的 legacy 加密项)。网关换 caller 承接
//    (reroute / 轮换 key / 恢复的历史会话) 即 400。reasonix 已用“失败后去
//    blob 重试”证明只留 plaintext summary 即可干净重放；此处取更简单的主
//    动剥离——单次请求即成功，无需消费事件流判错做重试 (streamSimple 返回
//    事件流而非 Promise，重试复杂度远高于此)。剥离时连同 provider-issued
//    `id` 一起去掉 (reasonix omitReasoningID: Console 在 stateless 下无法
//    resolve 跨轮 id，"not found or has expired" 亦 400)，只留 summary /
//    content 明文；剥后无载荷的空 reasoning 项直接丢弃，避免空回放。
// 2. `input[N].call_id` length must be >= 1 — Responses 网关要求每个
//    function_call / function_call_output 的 call_id 非空；pi 内 `id` 是
//    `{call_id}|{item_id}` 双段式，跨模型归一化 (`_+` 尾剥) 或网关空回
//    可能把 call_id 压成空串。空串直发即 400，故此处用确定性 fallback
//    (`call_repaired_<8hex>`) 修复并在 assistant/toolResult 间保持一致，
//    绝不让空 call_id 上线。

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

function stripEncryptedSignature(
	signature: string | undefined,
	api?: EndpointApi,
): string | undefined {
	if (!signature) return signature;
	let parsed: unknown;
	try {
		parsed = JSON.parse(signature);
	} catch {
		// completions 推理字段名 ("reasoning_content" 等) 不是 JSON，原样保留；
		// 其余非 JSON opaque (responses 下会导致 pi-ai JSON.parse 直抛) 直接丢弃。
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
			// responses/stateless 下 id 与 blob 同为 issuer 绑定 (reasonix
			// omitReasoningID)，一并去掉；completions 亦去 id，避免 stale 配对。
			if (!hasReasoningPayload(rest)) return undefined;
			return JSON.stringify(rest);
		}
		// responses/stateless 无 blob 但带跨轮 id 亦无法 resolve (reasonix 实证
		// "not found or has expired")，主动去 id 只留明文载荷。
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

/** 与 pi-ai openai-responses 归一化同算法：压成空即视为上不了线的空 call_id。 */
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
						// redacted 即 opaque 加密载荷，zen 下无 issuer 即不可回放；
						// 有明文 thinking 则转纯文本保留 (responses 无签名 thinking
						// 不回放，直接丢会丢失可见思考)，无则整块丢弃。
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

// ─── streaming ──────────────────────────────────────────────────────────────

function streamOpencodeZen(
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
): AssistantMessageEventStream {
	const api = resolveEndpoint(model.id);

	// Wire identity wins for the opencode keys; other caller headers
	// (Authorization etc.) pass through untouched. The fetch wrapper strips
	// SDK-stamped X-Stainless-* telemetry the CLI never sends.
	const wrappedOptions: SimpleStreamOptions = {
		...options,
		headers: { ...options?.headers, ...opencodeHeaders(api) },
		fetch: stripStainlessFetch(api, options?.fetch),
	};

	// Honor the catalog's authoritative baseUrl (anthropic-messages uses bare
	// /zen, the rest /zen/v1); the free set currently only hits /zen/v1.
	// Unknown roots fail closed instead of silently rerouting.
	const catalogBaseUrl = catalogBaseUrlOf(model);
	if (!isKnownZenBaseUrl(catalogBaseUrl)) {
		throw new Error(
			`opencode model ${model.id} baseUrl drifted to ${catalogBaseUrl}; update BASE_URL routing`,
		);
	}
	const wrappedModel = {
		...model,
		api,
		baseUrl: catalogBaseUrl,
	};
	return streamSimple(
		wrappedModel as Model<Api>,
		sanitizeZenContext(context, api),
		wrappedOptions,
	);
}

export default async function (pi: ExtensionAPI): Promise<void> {
	const modelIds = loadModelIds();
	if (modelIds.length === 0) return;
	projectId = await resolveProjectId(process.cwd());
	// Closest to the CLI: a fresh descending ses_ per pi session, like separate
	// `opencode run` invocations carrying different ses_ IDs in the captures.
	pi.on("session_start", () => {
		sessionId = `ses_${identifier(true)}`;
	});

	pi.registerProvider("opencode", {
		baseUrl: BASE_URL,
		apiKey: API_KEY,
		api: "openai-completions",
		// Two pi-ai copies exist at runtime (the extension-local one this file
		// imports and the host's nested copy that declares this callback); they
		// differ only by version drift, hence the boundary cast.
		// SAFETY: the host invokes us with its own Model/SimpleStreamOptions
		// instances, which we consume duck-typed (id, reasoning, header merge)
		// and forward to the extension-local adapters; no cross-copy identity
		// checks (instanceof/brand) are performed on either side.
		streamSimple:
			streamOpencodeZen as unknown as ProviderConfig["streamSimple"],
		models: modelIds.map((id) => buildModelConfig(id)),
	});
}
