/**
 * pi extension that makes requests to OpenCode Zen indistinguishable from the
 * real opencode CLI on the wire: User-Agent, Accept/Accept-Encoding and the
 * x-opencode-* identifier headers.
 *
 * Sources mirrored (opencode v1.18.26):
 *   - packages/schema/src/identifier.ts + packages/opencode/src/id/id.ts
 *     (ses_ descending, msg_ ascending, 12 hex time chars + 14 base62 chars)
 *   - packages/opencode/src/session/llm/request.ts (headers, per-provider UA)
 *   - packages/core/src/models-dev.ts (models.dev fetch UA)
 *   - packages/core/src/project.ts + util/hash.ts (x-opencode-project)
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
import type {
	ExtensionAPI,
	ProviderConfig,
	ProviderModelConfig,
} from "@earendil-works/pi-coding-agent";

const BASE_URL = "https://opencode.ai/zen/v1";
const MODELS_DEV_URL = "https://models.dev/api.json";
const API_KEY = "public";
const OPENCODE_VERSION = "1.18.26";
const MAX_BOOTSTRAP_ATTEMPTS = 3;

// ─── opencode wire identity ─────────────────────────────────────────────────

// The CLI's request.ts sends `User-Agent: opencode/<version>`; the AI SDK's
// withUserAgentSuffix appends `ai-sdk/provider-utils/<version>` plus the
// runtime segment. The provider-utils version is the one resolved under each
// @ai-sdk package in opencode v1.18.21's lockfile.
type EndpointApi =
	| "anthropic-messages"
	| "google-generative-ai"
	| "openai-completions"
	| "openai-responses";

const PROVIDER_UTILS_VERSIONS: Record<EndpointApi, string> = {
	"openai-completions": "4.0.23", // @ai-sdk/openai-compatible@2.0.41
	"openai-responses": "4.0.38", // @ai-sdk/openai@3.0.84
	"anthropic-messages": "4.0.27", // @ai-sdk/anthropic@3.0.82
	"google-generative-ai": "4.0.27", // @ai-sdk/google@3.0.73
};

// models.dev catalog fetches use opencode/<channel>/<version>/<client>
// (packages/core/src/models-dev.ts; channel "prod" for releases).
const MODELS_DEV_USER_AGENT = `opencode/prod/${OPENCODE_VERSION}/cli`;

/** Mirrors the AI SDK's getRuntimeEnvironmentUserAgent(). */
function runtimeSegment(): string {
	const g = globalThis as {
		window?: unknown;
		navigator?: { userAgent?: string };
		process?: { version?: string };
	};
	if (g.window) return "runtime/browser";
	if (g.navigator?.userAgent)
		return `runtime/${g.navigator.userAgent.toLowerCase()}`;
	if (g.process?.version) return `runtime/node.js/${g.process.version}`;
	return "runtime/unknown";
}

function userAgent(api: EndpointApi): string {
	return [
		`opencode/${OPENCODE_VERSION}`,
		`ai-sdk/provider-utils/${PROVIDER_UTILS_VERSIONS[api]}`,
		runtimeSegment(),
	].join(" ");
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

// Sessions use the descending encoding and are fixed per client instance;
// message (request) IDs use the ascending encoding, fresh per request.
const SESSION_ID = `ses_${identifier(true)}`;

function requestId(): string {
	return `msg_${identifier(false)}`;
}

// ─── x-opencode-project (packages/core/src/project.ts) ──────────────────────

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

	// opencode caches the resolved id in <common-dir>/opencode.
	try {
		const cached = (
			await readFile(path.join(commonDir, "opencode"), "utf8")
		).trim();
		if (cached) return cached;
	} catch {
		// No cached id; fall through to derivation.
	}

	const origin = await gitOut(cwd, ["remote", "get-url", "origin"]);
	const normalized = origin ? normalizeRemote(origin) : undefined;
	if (normalized) {
		return createHash("sha1").update(`git-remote:${normalized}`).digest("hex");
	}

	// Repos without an origin fall back to their root commit hash.
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

function opencodeHeaders(api: EndpointApi): Record<string, string> {
	return {
		Accept: "*/*",
		"User-Agent": userAgent(api),
		"Accept-Encoding": "gzip, deflate, br, zstd",
		"x-opencode-client": "cli",
		"x-opencode-project": getProjectId(),
		"x-opencode-session": SESSION_ID,
		"x-opencode-request": requestId(),
	};
}

// The openai / @anthropic-ai SDK clients stamp X-Stainless-* telemetry
// headers the real CLI never sends; the pinned pi-ai adapter surface offers no
// fetch-injection option to strip them, so that residue is not simulatable —
// everything else matches the CLI.

// ─── models.dev metadata ────────────────────────────────────────────────────

interface ModelsDevModelInfo {
	status?: string | null;
	name?: string | null;
	reasoning?: boolean | null;
	reasoning_options?: Array<{
		type: string;
		values?: Array<string | null>;
	}> | null;
	modalities?: {
		input?: Array<string> | null;
		output?: Array<string> | null;
	} | null;
	limit?: {
		context?: number | null;
		output?: number | null;
	} | null;
	cost?: {
		input?: number | null;
		output?: number | null;
		cache_read?: number | null;
		cache_write?: number | null;
	} | null;
	provider?: {
		npm?: string | null;
	} | null;
}

interface BootstrapState {
	modelIds: string[];
	modelsDevInfo: Record<string, ModelsDevModelInfo>;
}

async function fetchUpstreamModelIds(): Promise<string[] | undefined> {
	const response = await fetch(`${BASE_URL}/models`, {
		headers: opencodeHeaders("openai-completions"),
	});
	if (!response.ok) return undefined;
	const json = (await response.json()) as { data?: Array<{ id?: string }> };
	return (json.data ?? [])
		.map((entry) => entry.id?.trim())
		.filter((id): id is string => Boolean(id));
}

async function fetchModelsDevInfo(): Promise<
	Record<string, ModelsDevModelInfo> | undefined
> {
	const response = await fetch(MODELS_DEV_URL, {
		headers: { "User-Agent": MODELS_DEV_USER_AGENT },
	});
	if (!response.ok) return undefined;
	const json = (await response.json()) as {
		opencode?: { models?: Record<string, ModelsDevModelInfo> };
	};
	return json.opencode?.models;
}

function isFreeModel(id: string, info?: ModelsDevModelInfo): boolean {
	if (id.toLowerCase().includes("-free")) return true;
	if (!info) return false;
	const cost = info.cost ?? {};
	return (cost.input ?? 0) === 0 && (cost.output ?? 0) === 0;
}

let bootstrapPromise: Promise<BootstrapState> | undefined;

function loadBootstrapState(): Promise<BootstrapState> {
	bootstrapPromise ??= (async () => {
		for (let attempt = 0; attempt < MAX_BOOTSTRAP_ATTEMPTS; attempt++) {
			try {
				const [upstreamModelIds, modelsDevInfo] = await Promise.all([
					fetchUpstreamModelIds(),
					fetchModelsDevInfo(),
				]);

				// The Zen API is the source of truth for what is actually served;
				// models.dev only enriches metadata (limits, reasoning, pricing).
				const modelIds = [...new Set(upstreamModelIds ?? [])]
					.filter((id) => isFreeModel(id, modelsDevInfo?.[id]))
					.filter((id) => modelsDevInfo?.[id]?.status !== "deprecated")
					.sort(compareStrings);

				if (modelIds.length > 0) {
					return { modelIds, modelsDevInfo: modelsDevInfo ?? {} };
				}
			} catch {
				// Retry with backoff; give up after MAX_BOOTSTRAP_ATTEMPTS.
			}
			await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
		}
		return { modelIds: [], modelsDevInfo: {} };
	})();
	return bootstrapPromise;
}

// ─── thinking-level mapping ─────────────────────────────────────────────────

// pi levels from least to most thinking:
//   off → minimal → low → medium → high → xhigh → max
// models.dev reasoning_options: [{ type: "toggle" }, { type: "effort", values }]
// The ladder is a plain string list on purpose: models.dev efforts and the
// host's thinking levels both live here, and the pinned pi-ai's typed union
// only knows up to "xhigh".
const THINKING_LADDER = ["minimal", "low", "medium", "high", "xhigh", "max"];

// Models that always think; upstream rejects any other effort level. models.dev
// gives no static signal for this, so they are listed here.
const ALWAYS_THINKS_PREFIXES = ["big-pickle"];
const ALWAYS_THINKS_EFFORTS = ["low", "high", "max"];

function buildThinkingLevelMap(
	modelId: string,
	info?: ModelsDevModelInfo,
): Model<Api>["thinkingLevelMap"] {
	if (!info?.reasoning) return undefined;

	const alwaysThinks = ALWAYS_THINKS_PREFIXES.some((prefix) =>
		modelId.startsWith(prefix),
	);
	const supported = new Set<string>();
	if (alwaysThinks) {
		for (const effort of ALWAYS_THINKS_EFFORTS) supported.add(effort);
	} else {
		let hasToggle = false;
		for (const opt of info.reasoning_options ?? []) {
			if (opt.type === "toggle") hasToggle = true;
			if (opt.type === "effort") {
				for (const value of opt.values ?? []) {
					if (value) supported.add(value);
				}
			}
		}
		if (supported.size === 0) {
			// Toggle-only means on/off; missing metadata falls back to low/medium/high.
			if (hasToggle) {
				supported.add("high");
			} else {
				supported.add("low");
				supported.add("medium");
				supported.add("high");
			}
		}
	}

	// Snap a pi level to the nearest supported effort; ties prefer the higher
	// level (matches DeepSeek's mapping).
	const nearest = (level: string): string | null => {
		if (supported.has(level)) return level;
		const index = THINKING_LADDER.indexOf(level);
		if (index === -1) return null;
		let best: string | null = null;
		let bestIndex = -1;
		let bestDistance = Number.POSITIVE_INFINITY;
		for (let i = 0; i < THINKING_LADDER.length; i++) {
			const effort = THINKING_LADDER[i]!;
			if (!supported.has(effort)) continue;
			const distance = Math.abs(i - index);
			if (
				distance < bestDistance ||
				(distance === bestDistance && i > bestIndex)
			) {
				bestDistance = distance;
				bestIndex = i;
				best = effort;
			}
		}
		return best;
	};

	// "off" stays null: the host disables thinking by omitting the option, so
	// declaring it supported would only invite a no-effort request.
	const map: Record<string, string | null> = {};
	for (const level of ["off", ...THINKING_LADDER]) {
		map[level] = level === "off" ? null : nearest(level);
	}
	return map as Model<Api>["thinkingLevelMap"];
}

// ─── model catalog ──────────────────────────────────────────────────────────

const NPM_TO_API: Record<string, EndpointApi> = {
	"@ai-sdk/openai-compatible": "openai-completions",
	"@ai-sdk/openai": "openai-responses",
	"@ai-sdk/anthropic": "anthropic-messages",
	"@ai-sdk/google": "google-generative-ai",
};

// Routing through streamSimple requires model.api === extension.api, so every
// registered model carries the provider default ("openai-completions"); the
// real per-model endpoint lives in this map instead.
const endpoints = new Map<string, EndpointApi>();

function resolveEndpoint(modelId: string): EndpointApi {
	return endpoints.get(modelId) ?? "openai-completions";
}

function buildModelConfig(
	id: string,
	info?: ModelsDevModelInfo,
): ProviderModelConfig {
	endpoints.set(
		id,
		NPM_TO_API[info?.provider?.npm ?? "@ai-sdk/openai-compatible"] ??
			"openai-completions",
	);

	const input: ("text" | "image")[] = [];
	for (const modality of info?.modalities?.input ?? []) {
		if (modality === "text" || modality === "image") input.push(modality);
	}
	if (input.length === 0) input.push("text");

	const thinkingLevelMap = buildThinkingLevelMap(id, info);
	return {
		id,
		name: info?.name?.trim() || id,
		reasoning: info?.reasoning ?? true,
		input,
		cost: {
			input: info?.cost?.input ?? 0,
			output: info?.cost?.output ?? 0,
			cacheRead: info?.cost?.cache_read ?? 0,
			cacheWrite: info?.cost?.cache_write ?? 0,
		},
		contextWindow: info?.limit?.context ?? 128000,
		maxTokens: info?.limit?.output ?? 4096,
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
		headers: { ...opencodeHeaders(api), ...options?.headers },
	};

	// Always-thinking models reject requests without an accepted effort level
	// (400: "cannot be disabled; please use low, high, or max"). The session
	// default omits the option entirely and the host can emit "max", which the
	// pinned adapter's clamp does not know; translate both onto levels whose
	// thinkingLevelMap entry lands on an accepted wire effort.
	const requested = wrappedOptions.reasoning as string | undefined;
	if (
		ALWAYS_THINKS_PREFIXES.some((prefix) => model.id.startsWith(prefix)) &&
		(!requested || requested === "max")
	) {
		wrappedOptions.reasoning = (
			requested ? "xhigh" : "low"
		) as SimpleStreamOptions["reasoning"];
	}

	const wrappedModel = { ...model, api, baseUrl: BASE_URL };
	return streamSimple(wrappedModel as Model<Api>, context, wrappedOptions);
}

export default async function (pi: ExtensionAPI): Promise<void> {
	const [state, resolvedProjectId] = await Promise.all([
		loadBootstrapState(),
		resolveProjectId(process.cwd()),
	]);
	const { modelIds, modelsDevInfo } = state;
	// Offline or upstream failure: keep pi's builtin opencode catalog untouched.
	if (modelIds.length === 0) return;
	projectId = resolvedProjectId;

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
		models: modelIds.map((id) => buildModelConfig(id, modelsDevInfo[id])),
	});
}
