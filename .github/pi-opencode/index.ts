import { createHash, randomBytes } from "node:crypto";
import {
	type Api,
	type AssistantMessageEventStream,
	type Context,
	type Model,
	type SimpleStreamOptions,
	streamSimpleAnthropic,
	streamSimpleGoogle,
	streamSimpleOpenAICompletions,
	streamSimpleOpenAIResponses,
} from "@earendil-works/pi-ai";
import type {
	ExtensionAPI,
	ProviderModelConfig,
} from "@earendil-works/pi-coding-agent";

const BASE_URL = "https://opencode.ai/zen/v1";
const MODELS_DEV_URL = "https://models.dev/api.json";
const API_KEY = "public";

// ─── opencode wire constants ────────────────────────────────────────────────
// User-Agent matching the real opencode CLI on the wire (Bun runtime appends
// the AI SDK and runtime segments). Verified against v1.18.21:
//   opencode version        -> packages/opencode/package.json "version"
//   ai-sdk/provider-utils   -> @ai-sdk/openai-compatible@2.0.41 dependency
//   runtime/bun             -> root package.json "packageManager": bun@1.3.14
const OPENCODE_USER_AGENT =
	"opencode/1.18.21 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14";
const OPENCODE_ACCEPT_ENCODING = "gzip, deflate, br, zstd";

// opencode identifier simulation ────────────────────────────────────────────
// Real opencode uses a 26-char identifier format:
//   ses_<time+random>  for session IDs
//   msg_<time+random>  for request IDs
//   prj_<time+random>  for project IDs
//
// The first 12 chars are HEX-encoded time (not base62!), the remaining 14 are
// random characters from a 62-char alphabet. For "descending" IDs, the time
// value is bitwise-NOT inverted so newer timestamps produce larger strings.
//
// Source: packages/schema/src/identifier.ts in anomalyco/opencode

const RANDOM_CHARS =
	"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
const IDENT_LENGTH = 26;
const TIME_HEX_LENGTH = 12; // 6 bytes × 2 hex chars
const RANDOM_PART_LENGTH = IDENT_LENGTH - TIME_HEX_LENGTH; // 14 chars

/** Per-millisecond counter (matches real opencode behavior). */
let lastTimestamp = 0;
let counter = 0;

/**
 * Generate a 26-char identifier matching real opencode's exact format.
 *
 * Real opencode (packages/schema/src/identifier.ts):
 *   current = BigInt(timestamp) * 0x1000n + BigInt(counter)
 *   value = descending ? ~current : current
 *   time = 12 hex chars from value (6 bytes)
 *   random = 14 chars from RANDOM_CHARS (62-char alphabet)
 *
 * We generate descending IDs so newer timestamps produce larger strings,
 * which matches real opencode's session/request ID behavior.
 */
function descendingId(): string {
	const now = Date.now();
	if (now !== lastTimestamp) {
		lastTimestamp = now;
		counter = 0;
	}
	counter++;

	// Match real opencode: timestamp * 0x1000 + counter, then bitwise NOT
	const current = BigInt(now) * 0x1000n + BigInt(counter);
	const value = ~current; // descending = bitwise NOT

	// Encode as 12 hex characters (6 bytes)
	const timePart = Array.from({ length: 6 }, (_, i) =>
		Number((value >> BigInt(40 - 8 * i)) & 0xffn)
			.toString(16)
			.padStart(2, "0"),
	).join("");

	// 14-char random suffix from RANDOM_CHARS
	const bytes = randomBytes(RANDOM_PART_LENGTH);
	const randomPart = Array.from(bytes, (b) => RANDOM_CHARS[b % 62]).join("");

	return timePart + randomPart;
}

/** Stable session ID — persists for the lifetime of this extension. */
const STABLE_SESSION_ID = `ses_${descendingId()}`;

/** Generate a unique request ID per API call. */
function requestId(): string {
	return `msg_${descendingId()}`;
}

/** Stable project ID derived deterministically from cwd. */
function deriveProjectId(dir: string): string {
	// Use the same identifier format as real opencode: 12 hex chars + 14 random chars
	// For determinism, we derive the time part from a hash of the directory path
	const hash = createHash("sha256").update(dir).digest();
	// Use first 6 bytes as a "timestamp" for the hex part
	const timePart = Array.from({ length: 6 }, (_, i) =>
		hash[i].toString(16).padStart(2, "0"),
	).join("");
	// Use bytes 6-19 to derive 14 chars from RANDOM_CHARS
	const randomPart = Array.from(
		{ length: RANDOM_PART_LENGTH },
		(_, i) => RANDOM_CHARS[hash[6 + i] % 62],
	).join("");
	return `prj_${timePart}${randomPart}`;
}

let cachedProjectId: string | undefined;

interface EndpointConfig {
	api:
		| "anthropic-messages"
		| "google-generative-ai"
		| "openai-completions"
		| "openai-responses";
	baseUrl: string;
}

interface ModelsDevModelInfo {
	status?: string | null;
	name?: string | null;
	description?: string | null;
	reasoning?: boolean | null;
	reasoning_options?: Array<{
		type: string;
		values?: string[];
		max?: number;
	}> | null;
	modalities?: {
		input?: Array<string> | null;
		output?: Array<string> | null;
	} | null;
	limit?: {
		context?: number | null;
		output?: number | null;
		input?: number | null;
	} | null;
	cost?: {
		input?: number | null;
		output?: number | null;
		cache_read?: number | null;
		cache_write?: number | null;
	} | null;
}

interface UpstreamModelListResponse {
	data?: Array<{ id?: string }>;
}

interface BootstrapState {
	modelIds: string[];
	modelsDevInfo: Record<string, ModelsDevModelInfo>;
}

type SupportedInput = "text" | "image";

type ModelRecord = ProviderModelConfig & {
	id: string;
	name: string;
	reasoning: boolean;
	input: SupportedInput[];
	cost: {
		input: number;
		output: number;
		cacheRead: number;
		cacheWrite: number;
	};
	contextWindow: number;
	maxTokens: number;
	thinkingLevelMap?: Record<string, string | null>;
};

let bootstrapPromise: Promise<BootstrapState> | undefined;
const MAX_BOOTSTRAP_ATTEMPTS = 3;

/**
 * Build headers that mimic the real opencode client (source: request.ts).
 *
 * Real opencode sends:
 *   User-Agent: "opencode/{version}"
 *   Accept: star/star (matches any content type)
 *   x-opencode-client:   RuntimeFlags.client (default "cli")
 *   x-opencode-session:  "ses_" + descending-id  (stable per session)
 *   x-opencode-project:  project.ID               (stable per project)
 *   x-opencode-request:  "msg_" + descending-id  (unique per request)
 */
function opencodeHeaders(): Record<string, string> {
	if (!cachedProjectId) {
		try {
			cachedProjectId = deriveProjectId(process.cwd());
		} catch {
			cachedProjectId = deriveProjectId("unknown");
		}
	}

	return {
		"Accept": "*/*",
		"User-Agent": OPENCODE_USER_AGENT,
		"Accept-Encoding": OPENCODE_ACCEPT_ENCODING,
		"x-opencode-client": "cli",
		"x-opencode-session": STABLE_SESSION_ID,
		"x-opencode-project": cachedProjectId,
		"x-opencode-request": requestId(),
	};
}

function isDeprecated(model: ModelsDevModelInfo | undefined): boolean {
	return model?.status === "deprecated";
}

/**
 * Determine whether a model is free based on models.dev cost data.
 * Falls back to name heuristic when cost data is unavailable.
 */
function isFreeModel(id: string, info?: ModelsDevModelInfo): boolean {
	if (info?.cost) {
		return (info.cost.input ?? 0) === 0 && (info.cost.output ?? 0) === 0;
	}
	return id.toLowerCase().includes("free");
}

/**
 * pi thinking levels (from least to most thinking):
 *   off → minimal → low → medium → high → xhigh → max
 *
 * models.dev reasoning_options format:
 *   [{ type: "toggle" }, { type: "effort", values: ["low","medium","high"] }]
 *
 * Mapping rules:
 *   "toggle" → model supports reasoning on/off
 *   "effort" → model supports specific effort levels
 *   null in thinkingLevelMap → level not supported
 *
 * DeepSeek-specific (from API docs):
 *   - Low and medium are mapped to high
 *   - xhigh is mapped to max
 *
 * General mapping strategy:
 *   - Collect provider-supported effort levels
 *   - Map pi levels to nearest supported provider level
 *   - "off" always maps to null (thinking disabled)
 */
const PI_THINKING_LEVELS = [
	"off",
	"minimal",
	"low",
	"medium",
	"high",
	"xhigh",
	"max",
] as const;

/** Sort order for effort levels (lowest to highest) */
const EFFORT_ORDER = [
	"minimal",
	"low",
	"medium",
	"high",
	"xhigh",
	"max",
] as const;

// Models that always think; upstream rejects any effort outside this set
// (400: "cannot be disabled; please use low, high, or max"). models.dev gives
// no static signal distinguishing these, so list them here.
const ALWAYS_THINKS_MODELS = ["big-pickle"];
const ALWAYS_THINKS_EFFORTS = new Set(["low", "high", "max"]);

/** Snap a pi thinking level to one the always-thinking model accepts. */
function snapAlwaysThinks(level?: string): string {
	switch (level) {
		case "xhigh":
		case "max":
			return "max";
		case "medium":
			return "high";
		default:
			return "low";
	}
}

function buildThinkingLevelMap(
	modelId: string,
	info?: ModelsDevModelInfo,
): Record<string, string | null> | undefined {
	if (!info?.reasoning) return undefined;

	const map: Record<string, string | null> = {};

	// Collect supported effort levels from reasoning_options
	const supportedEffort = new Set<string>();
	let hasToggle = false;

	const alwaysThinks = ALWAYS_THINKS_MODELS.some((p) => modelId.startsWith(p));
	if (alwaysThinks) {
		// Restrict the visible/requestable levels to what upstream accepts.
		for (const opt of info.reasoning_options ?? []) {
			if (opt.type === "effort" && opt.values) {
				for (const v of opt.values) {
					if (ALWAYS_THINKS_EFFORTS.has(v)) supportedEffort.add(v);
				}
			}
		}
	} else {
		for (const opt of info.reasoning_options ?? []) {
			if (opt.type === "toggle") hasToggle = true;
			if (opt.type === "effort" && opt.values) {
				for (const v of opt.values) supportedEffort.add(v);
			}
		}
	}

	// If no effort levels but has toggle, only off/high are available
	if (supportedEffort.size === 0 && hasToggle) {
		supportedEffort.add("high");
	}

	// If reasoning is true but no effort levels found in reasoning_options,
	// provide default low/medium/high (MiMo, Nemotron, etc. support these
	// but models.dev doesn't always list them)
	if (supportedEffort.size === 0 && info.reasoning) {
		supportedEffort.add("low");
		supportedEffort.add("medium");
		supportedEffort.add("high");
	}

	// Helper: find the nearest supported effort level for a given pi level
	// When distances are equal, prefer the higher level (matches DeepSeek's behavior)
	const findNearest = (level: string): string | null => {
		if (supportedEffort.has(level)) return level;

		const levelIdx = EFFORT_ORDER.indexOf(
			level as (typeof EFFORT_ORDER)[number],
		);
		if (levelIdx === -1) return null;

		let best: string | null = null;
		let bestIdx = -1;
		let bestDist = Infinity;
		for (let i = 0; i < EFFORT_ORDER.length; i++) {
			const e = EFFORT_ORDER[i];
			if (!supportedEffort.has(e)) continue;
			const dist = Math.abs(i - levelIdx);
			if (dist < bestDist || (dist === bestDist && i > bestIdx)) {
				bestDist = dist;
				bestIdx = i;
				best = e;
			}
		}
		return best;
	};

	// Build the map: pi levels → provider values (or null if unsupported)
	for (const level of PI_THINKING_LEVELS) {
		if (level === "off") {
			// "off" maps to null (no thinking) unless the model cannot disable thinking
			map[level] = alwaysThinks ? findNearest("low") : null;
		} else {
			const mapped = findNearest(level);
			map[level] = mapped;
		}
	}

	// Only return if there's at least one supported non-off level
	const hasNonOff = PI_THINKING_LEVELS.some(
		(l) => l !== "off" && map[l] !== null,
	);
	return hasNonOff ? map : undefined;
}

function buildModelRecord(id: string, info?: ModelsDevModelInfo): ModelRecord {
	const thinkingLevelMap = buildThinkingLevelMap(id, info);

	// Map modalities.input to supported input types
	const input: SupportedInput[] = [];
	if (info?.modalities?.input) {
		for (const mod of info.modalities.input) {
			if (mod === "text" || mod === "image") {
				input.push(mod);
			}
		}
	}
	if (input.length === 0) input.push("text");

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

function resolveEndpoint(modelId: string): EndpointConfig {
	// muse-spark is served through the Responses API; over chat/completions its
	// stream never emits finish_reason (verified against /v1/responses).
	if (modelId.startsWith("muse-spark")) {
		return { api: "openai-responses", baseUrl: BASE_URL };
	}
	if (modelId.startsWith("claude-")) {
		return { api: "anthropic-messages", baseUrl: BASE_URL };
	}
	if (modelId.startsWith("gemini-")) {
		return { api: "google-generative-ai", baseUrl: BASE_URL };
	}
	if (modelId.startsWith("gpt-")) {
		return { api: "openai-responses", baseUrl: BASE_URL };
	}
	return { api: "openai-completions", baseUrl: BASE_URL };
}

async function fetchUpstreamModelIds(): Promise<string[] | undefined> {
	try {
		const response = await fetch(`${BASE_URL}/models`, {
			headers: opencodeHeaders(),
		});
		if (!response.ok) return undefined;
		const json = (await response.json()) as UpstreamModelListResponse;
		return (json.data ?? [])
			.map((entry) => entry.id?.trim())
			.filter((id): id is string => Boolean(id));
	} catch {
		return undefined;
	}
}

async function fetchModelsDevInfo(): Promise<
	Record<string, ModelsDevModelInfo> | undefined
> {
	try {
		const response = await fetch(MODELS_DEV_URL);
		if (!response.ok) return undefined;
		const json = (await response.json()) as {
			opencode?: { models?: Record<string, ModelsDevModelInfo> };
		};
		return json.opencode?.models;
	} catch {
		return undefined;
	}
}

async function loadBootstrapState(): Promise<BootstrapState> {
	// Cache: once resolved, all future calls return the same result
	if (bootstrapPromise) return bootstrapPromise;

	bootstrapPromise = (async () => {
		for (let attempt = 0; attempt < MAX_BOOTSTRAP_ATTEMPTS; attempt++) {
			try {
				const [upstreamModelIds, modelsDevInfo] = await Promise.all([
					fetchUpstreamModelIds(),
					fetchModelsDevInfo(),
				]);

				// Upstream API is the source of truth for which models are actually available.
				// models.dev only provides metadata enrichment (context window, reasoning options, etc).
				const upstreamSet = new Set(upstreamModelIds ?? []);
				const modelIds = [...upstreamSet]
					.filter((id) => isFreeModel(id, modelsDevInfo?.[id]))
					.filter((id) => !isDeprecated(modelsDevInfo?.[id]));

				if (modelIds.length > 0) {
					return { modelIds, modelsDevInfo: modelsDevInfo ?? {} };
				}
			} catch {
				// Retry on next iteration
			}
			await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
		}
		return { modelIds: [], modelsDevInfo: {} };
	})();

	return bootstrapPromise;
}

function getVisibleModels(
	modelIds: string[],
	modelsDevInfo: Record<string, ModelsDevModelInfo>,
): ProviderModelConfig[] {
	return modelIds.map((id) => {
		const model = buildModelRecord(id, modelsDevInfo[id]);
		return {
			id: model.id,
			name: model.name,
			reasoning: model.reasoning,
			input: model.input,
			cost: { ...model.cost },
			contextWindow: model.contextWindow,
			maxTokens: model.maxTokens,
			...(model.thinkingLevelMap
				? { thinkingLevelMap: model.thinkingLevelMap }
				: {}),
		};
	});
}

function streamOpencodeZen(
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
): AssistantMessageEventStream {
	const endpoint = resolveEndpoint(model.id);

	const wrappedModel = {
		...model,
		api: endpoint.api,
		baseUrl: endpoint.baseUrl,
	} as Model<Api>;

	const wrappedOptions: SimpleStreamOptions = {
		...options,
		headers: { ...opencodeHeaders(), ...options?.headers },
	};

	// Always-thinking models reject requests without an explicit effort level.
	// Session default is "off" (omitted downstream), so lift it to the minimum
	// accepted value; user-selected levels pass through unchanged.
	if (ALWAYS_THINKS_MODELS.some((p) => model.id.startsWith(p))) {
		const requested = wrappedOptions.reasoning;
		if (!requested || !ALWAYS_THINKS_EFFORTS.has(requested)) {
			wrappedOptions.reasoning = snapAlwaysThinks(requested);
		}
	}

	switch (endpoint.api) {
		case "anthropic-messages":
			return streamSimpleAnthropic(
				wrappedModel as Model<"anthropic-messages">,
				context,
				wrappedOptions,
			);
		case "google-generative-ai":
			return streamSimpleGoogle(
				wrappedModel as Model<"google-generative-ai">,
				context,
				wrappedOptions,
			);
		case "openai-responses":
			return streamSimpleOpenAIResponses(
				wrappedModel as Model<"openai-responses">,
				context,
				wrappedOptions,
			);
		default:
			return streamSimpleOpenAICompletions(
				wrappedModel as Model<"openai-completions">,
				context,
				wrappedOptions,
			);
	}
}

export default async function (pi: ExtensionAPI): Promise<void> {
	const { modelIds, modelsDevInfo } = await loadBootstrapState();
	const visibleModels = getVisibleModels(modelIds, modelsDevInfo);

	pi.registerProvider("opencode-zen", {
		baseUrl: BASE_URL,
		apiKey: API_KEY,
		api: "openai-completions",
		streamSimple: streamOpencodeZen,
		models: visibleModels,
	});
}
