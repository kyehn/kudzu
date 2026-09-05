/**
 * pi extension that makes requests to OpenCode Zen indistinguishable from the
 * real opencode CLI on the wire: User-Agent plus the x-opencode and x-session
 * identifier header families. (Body key order and TLS fingerprint are owned
 * by the pi-ai adapters / fix.patch respectively, not by this extension.)
 *
 * Sources mirrored (opencode v2, opencode2 v0.0.0-beta-19151):
 *   - packages/schema/src/identifier.ts
 *     (ses_ descending, 12 hex time chars + 14 base62 chars)
 *   - packages/core/src/session/model-request.ts (sessionHeaders, no
 *     x-opencode-request; x-session-affinity + X-Session-Id added)
 *   - packages/core/src/app.ts (App.useragent: opencode/{channel}/{version}/{name})
 *   - packages/schema/src/project-id.ts (x-opencode-project, "global" fallback)
 */
import { execFile } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
// 显式导入而非依赖全局 process：类型解析不再依赖环境自动发现 @types/node。
import process from "node:process";
import path from "node:path";
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
// Matches the beta CLI our fix.patch mimics (overlays/reasonix/opencode/).
const OPENCODE_VERSION = "0.0.0-beta-19151";
const OPENCODE_CHANNEL = "beta";

// ─── opencode wire identity ─────────────────────────────────────────────────

// App.useragent(): `opencode/${channel}/${version}/${name}` — a single exact
// string on every endpoint. v2 sends no ai-sdk/runtime suffix (v1 did).
const USER_AGENT = `opencode/${OPENCODE_CHANNEL}/${OPENCODE_VERSION}/cli`;

type EndpointApi =
	| "anthropic-messages"
	| "google-generative-ai"
	| "openai-completions"
	| "openai-responses";

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

// Sessions use the descending encoding and are fixed per client instance,
// stamped on x-opencode-session/x-session-affinity/X-Session-Id and reused
// as prompt_cache_key — exactly like the CLI reusing one ses_ ID per session.
// (v2 dropped the per-request x-opencode-request header, so no msg_ IDs.)
const SESSION_ID = `ses_${identifier(true)}`;

// ─── x-opencode-project (packages/schema/src/project-id.ts) ─────────────────

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

// ─── request headers ────────────────────────────────────────────────────────

function opencodeHeaders(): Record<string, string> {
	return {
		"User-Agent": USER_AGENT,
		"x-opencode-client": "cli",
		"x-opencode-project": getProjectId(),
		"x-opencode-session": SESSION_ID,
		"x-session-affinity": SESSION_ID,
		"X-Session-Id": SESSION_ID,
	};
}

// The openai / @anthropic-ai SDK clients stamp X-Stainless-* telemetry
// headers the real CLI never sends; the pinned pi-ai adapter surface offers no
// fetch-injection option to strip them, so that residue is not simulatable —
// everything else matches the CLI.

// ─── bootstrap: discover free models from pi built-in catalog ───────────────

function isFreeModel(id: string): boolean {
	const model = OPENCODE_MODELS[id as keyof typeof OPENCODE_MODELS];
	if (!model) return false;
	return (model.cost?.input ?? 0) === 0 && (model.cost?.output ?? 0) === 0;
}

function loadModelIds(): string[] {
	return Object.keys(OPENCODE_MODELS).filter(isFreeModel).sort(compareStrings);
}

// ─── thinking-level mapping ─────────────────────────────────────────────────

// Models that always think; upstream rejects any other effort level.
const ALWAYS_THINKS_PREFIXES = ["big-pickle"];
const ALWAYS_THINKS_EFFORTS = ["low", "high", "max"];

// pi built-in models already carry a typed `thinkingLevelMap`; for models
// not in the catalog we fall back to a sensible default.
function getThinkingLevelMap(
	modelId: string,
	model: Model<Api>,
): Model<Api>["thinkingLevelMap"] {
	const alwaysThinks = ALWAYS_THINKS_PREFIXES.some((prefix) =>
		modelId.startsWith(prefix),
	);
	if (alwaysThinks) {
		// Force the always-thinks efforts that upstream accepts.
		const map: Record<string, string | null> = {};
		for (const level of [
			"off",
			"minimal",
			"low",
			"medium",
			"high",
			"xhigh",
			"max",
		]) {
			map[level] = ALWAYS_THINKS_EFFORTS.includes(level) ? level : null;
		}
		return map as Model<Api>["thinkingLevelMap"];
	}
	// Use the thinkingLevelMap from the pi catalog directly.
	return model.thinkingLevelMap;
}

// ─── model catalog ──────────────────────────────────────────────────────────

/**
 * Always-thinking 档位翻译 (纯函数, 供单测):
 * - 未指定档位 → "low" (上游接受的最低档);
 * - "max" → "max" (绝不能是 "xhigh": getThinkingLevelMap 把 xhigh 映为
 *   null, pi-ai 适配层的 null 档会被丢弃, big-pickle 遂以无 effort 发出并被
 *   上游 400; live pi.dev 证实 big-pickle 无 thinkingLevelMap,
 *   ALWAYS_THINKS 表中 max→"max" 为有值档);
 * - 其余档位原样透传 (含用户显式 xhigh: 上游适配层行为, 本扩展不改写用户选择)。
 */
export function translateAlwaysThinksReasoning(
	requested: string | undefined,
): string {
	if (!requested) return "low";
	if (requested === "max") return "max";
	return requested;
}

// Routing through streamSimple requires model.api === extension.api, so every
// registered model carries the provider default ("openai-completions"); the
// real per-model endpoint lives in this map instead.
const endpoints = new Map<string, EndpointApi>();

export function resolveEndpoint(modelId: string): EndpointApi {
	const api = endpoints.get(modelId);
	if (!api) {
		// fail-closed: 未注册模型静默 default 会把请求送错 wire;
		// 调用方只应传入 buildModelConfig 注册过的 id。
		throw new Error(`opencode model ${modelId} was never registered; refusing to guess the endpoint`);
	}
	return api;
}

const ZEN_BASE_URLS = [BASE_URL, "https://opencode.ai/zen"];

/** pi 目录里出现过的合法 zen 根 (live pi.dev 实证: /zen/v1 49 族 + 裸 /zen 14 族, 后者当前全付费)。 */
export function isKnownZenBaseUrl(url: string): boolean {
	return ZEN_BASE_URLS.includes(url);
}

export function buildModelConfig(id: string): ProviderModelConfig {
	const model = OPENCODE_MODELS[id as keyof typeof OPENCODE_MODELS];
	// 各模型的权威 baseUrl 在 pi 目录里: anthropic-messages 族走裸 /zen
	// (live 实证, 当前全为付费模型故不进免费集), 其余走 /zen/v1。
	// 目录一旦漂移到未知根必须大声报错而非静默错路。
	if (
		model &&
		"baseUrl" in model &&
		typeof (model as { baseUrl?: unknown }).baseUrl === "string" &&
		!isKnownZenBaseUrl((model as { baseUrl: string }).baseUrl)
	) {
		throw new Error(
			`opencode model ${id} baseUrl drifted to ${(model as { baseUrl: string }).baseUrl}; update BASE_URL routing`,
		);
	}
	if (!model) {
		// Should never happen: callers only pass IDs present in OPENCODE_MODELS.
		endpoints.set(id, "openai-completions");
		return {
			id,
			name: id,
			reasoning: false,
			input: ["text"],
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			contextWindow: 128_000,
			maxTokens: 4_096,
		};
	}

	endpoints.set(id, model.api as EndpointApi);
	const thinkingLevelMap = getThinkingLevelMap(id, model as Model<Api>);
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

// ─── streaming ──────────────────────────────────────────────────────────────

function streamOpencodeZen(
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
): AssistantMessageEventStream {
	const api = resolveEndpoint(model.id);

	const wrappedOptions: SimpleStreamOptions = {
		...options,
		headers: { ...opencodeHeaders(), ...options?.headers },
	};

	// Always-thinking models reject requests without an accepted effort level
	// (400: "cannot be disabled; please use low, high, or max"). The session
	// default omits the option entirely and the host can emit "max"; translate
	// both onto levels whose thinkingLevelMap entry lands on an accepted wire
	// effort (see translateAlwaysThinksReasoning: "max" must stay "max",
	// never "xhigh", whose map entry is null and gets dropped by the adapter).
	const requested = wrappedOptions.reasoning as string | undefined;
	if (
		ALWAYS_THINKS_PREFIXES.some((prefix) => model.id.startsWith(prefix)) &&
		(!requested || requested === "max")
	) {
		wrappedOptions.reasoning =
			translateAlwaysThinksReasoning(requested) as SimpleStreamOptions["reasoning"];
	}

	const wrappedModel = { ...model, api, baseUrl: BASE_URL };
	return streamSimple(wrappedModel as Model<Api>, context, wrappedOptions);
}

export default async function (pi: ExtensionAPI): Promise<void> {
	const modelIds = loadModelIds();
	if (modelIds.length === 0) return;
	projectId = await resolveProjectId(process.cwd());

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
		streamSimple: streamOpencodeZen as unknown as ProviderConfig["streamSimple"],
		models: modelIds.map((id) => buildModelConfig(id)),
	});
}
