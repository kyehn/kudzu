import { randomBytes } from "node:crypto";
import type {
	Api,
	Model,
	ProviderHeaders,
	RefreshModelsContext,
} from "@earendil-works/pi-ai";
import type {
	ExtensionAPI,
	ModelRegistry,
	ProviderModelConfig,
} from "@earendil-works/pi-coding-agent";

// Simulates the OpenCode CLI on the wire so the zen gateway cannot tell pi
// apart, per overlays/maki/README.md. Three jobs, each on a hook pi already
// provides. No catalog is fetched and no wheel is reinvented:
//
//   1. Model list — one `registerProvider("opencode", …)` at discovery. The
//      visible tier is the free tier only, through one projection shared by
//      the registration snapshot and the `refreshModels` hook. The hook
//      re-projects from `context.stored` — the pi.dev catalog pi itself
//      synced into `models-store.json` — so `pi update --models` is the only
//      refresh path and anything pi.dev dropped (a withdrawn baseline id
//      included) disappears from the registered list on the next refresh.
//      Entries carry pi's own catalog fields through (`findModelDefaults`
//      only fills `api`/`baseUrl` fallbacks), because downstream readers need
//      the rest; pi keeps owning baseline, overlay, storage and throttling,
//      and no `pi.dev` or `models.dev` request is made from here.
//   2. Wire identity — `before_provider_headers` rewrites the assembled
//      headers: the per-endpoint `User-Agent`, the `x-opencode-*` trio, and a
//      session id built with opencode's own algorithm. This hook covers every
//      api, which a provider overlay cannot: `ProviderConfig` names a single
//      `api`, and the capture table spans three.
//   3. Transcript — `before_provider_request` edits the payload in place, the
//      data-format level the maki overlay asks for, and again covers every api.
//
// Credentials stay out of this file: pi's own `opencode` provider declares
// `OPENCODE_API_KEY` and pi resolves it from `auth.json` before the
// environment, so the bearer lives in pi's credential store only.

const PROVIDER_ID = "opencode";

// Per-endpoint provider-utils pins: chat-completions 4.0.23, responses 4.0.40,
// anthropic 4.0.46 — the capture table in overlays/maki/README.md. The
// provider also serves `google-generative-ai`, which the table does not cover,
// so no User-Agent is claimed for it rather than borrowing another pin.
const OPENCODE_VERSION = "1.18.32";
const USER_AGENT_BY_API: Partial<Record<Api, string>> = {
	"anthropic-messages": `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.46 runtime/bun/1.3.14`,
	"openai-responses": `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14`,
	"openai-completions": `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`,
};

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

// pi assembles these headers per request, so the request id is minted per call
// and stays correct across retries. Literals stay inline: each is used once,
// and an alias would only hide the wire value being claimed.
function applyWireIdentity(headers: ProviderHeaders, api: Api): void {
	const userAgent = USER_AGENT_BY_API[api];
	if (userAgent !== undefined) headers["User-Agent"] = userAgent;
	// pi sends `x-opencode-client: pi`; the CLI reports `cli`.
	headers["x-opencode-client"] = "cli";
	// The project scope opencode reports when it has no repository to name.
	headers["x-opencode-project"] = "global";
	// pi sends its own session id here; the CLI sends one from its algorithm.
	headers["x-opencode-session"] = sessionId;
	headers["x-opencode-request"] = `msg_${identifier(false)}`;
}

const ENCRYPTED_REASONING_TYPE = "reasoning.encrypted";

/**
 * The id a tool call travels under, and the id its result travels under, for
 * each of the three shapes pi builds:
 *
 *   - chat completions — `tool_calls[].id` and `tool_call_id`
 *   - responses — `function_call.call_id` and `function_call_output.call_id`
 *   - anthropic — `tool_use.id` and `tool_result.tool_use_id`
 *
 * `id` covers the call in all three; the result needs naming per shape, and
 * `call_id` is shared by both, so the node's `type` decides there.
 */
const RESULT_ID_FIELDS = new Set(["tool_call_id", "tool_use_id"]);

function isResultItem(record: Record<string, unknown>, field: string): boolean {
	if (RESULT_ID_FIELDS.has(field)) return true;
	const type = record.type;
	return typeof type === "string" && type.endsWith("_output");
}

// One pass over the payload for both transcript repairs, so the three request
// shapes need no per-api branch. The rule set is deliberately tiny and each
// entry is a place pi demonstrably replays issuer-bound data: the
// `encrypted_content` a Responses reasoning item carries, the
// `reasoning.encrypted` entries of a chat-completions `reasoning_details`
// array, and a tool call id that collapsed to empty. Everything else, the
// plaintext reasoning summary included, is left byte for byte alone.
function sanitizeRequest(payload: unknown): void {
	// pi emits exactly one result per call and it follows the call, and
	// document order is the order `visit` walks, so a queue pairs them even
	// when several calls share one assistant message.
	const repairedCallIds: string[] = [];

	function visit(value: unknown): void {
		if (Array.isArray(value)) {
			for (const entry of value) visit(entry);
			return;
		}
		if (value === null || typeof value !== "object") return;
		const record = value as Record<string, unknown>;

		if (typeof record.encrypted_content === "string") {
			// The blob and the reasoning item id are issued together and
			// validated as a pair, so both go; pi omits the id elsewhere for
			// the same reason.
			delete record.encrypted_content;
			delete record.id;
		}

		for (const field of ["id", "call_id", "tool_call_id", "tool_use_id"]) {
			if (record[field] !== "") continue;
			if (isResultItem(record, field)) {
				// A result with no call to pair against is not repairable, so
				// it is left as it is rather than given a fabricated partner.
				const paired = repairedCallIds.shift();
				if (paired !== undefined) record[field] = paired;
				continue;
			}
			const repaired = `call_${repairedCallIds.length + 1}`;
			repairedCallIds.push(repaired);
			record[field] = repaired;
		}

		for (const [key, nested] of Object.entries(record)) {
			if (key === "reasoning_details" && Array.isArray(nested)) {
				// pi re-adds the key whenever the parsed signature yielded
				// anything, so an emptied array has to be removed as well.
				const kept = nested.filter(
					(detail) =>
						(detail as { type?: unknown } | null)?.type !==
						ENCRYPTED_REASONING_TYPE,
				);
				if (kept.length === 0) {
					delete record.reasoning_details;
					continue;
				}
				record.reasoning_details = kept;
				continue;
			}
			visit(nested);
		}
	}

	visit(payload);
}

// The anonymous zen key buys only the zero-cost tier, so cost is the whole
// policy, and every opencode model is served from zen.
function isFreeZenModel(model: Model<Api>): boolean {
	return (
		model.provider === PROVIDER_ID &&
		model.cost?.input === 0 &&
		model.cost?.output === 0
	);
}

// The projection shared by the registration snapshot and the refresh hook, so
// the two can never drift. Every field pi's own catalog entry carries is
// passed through (only `headers` is left for pi to assemble per request and
// `provider` for the composer to stamp); registering a thinner shape breaks
// downstream readers that assume a catalog entry.
function projectFreeTier(
	models: ReadonlyArray<Model<Api>>,
): ProviderModelConfig[] {
	return models.filter(isFreeZenModel).map((model) => ({
		id: model.id,
		name: model.name,
		api: model.api,
		baseUrl: model.baseUrl,
		reasoning: model.reasoning,
		thinkingLevelMap: model.thinkingLevelMap,
		input: model.input,
		inputLimits: model.inputLimits,
		cost: model.cost,
		promptCache: model.promptCache,
		contextWindow: model.contextWindow,
		maxTokens: model.maxTokens,
		compat: model.compat,
	}));
}

// ModelsStoreEntry shapes differ across pi builds (array or Map), so the
// refresh hook reads through one helper instead of repeating the branch.
// Entries pass through only with a string `id`: anything else cannot name a
// model, and dropping it here beats registering an `id: undefined` entry
// that would fail far from the cause. The remaining fields are pi's own
// persisted catalog shape, resolved against the live entry by the composer.
function storedModelsOf(stored: unknown): Array<Model<Api>> {
	if (stored === null || typeof stored !== "object") return [];
	const models = (stored as { models?: unknown }).models;
	const entries = Array.isArray(models)
		? models
		: models instanceof Map
			? [...models.values()]
			: [];
	return entries.filter(
		(entry): entry is Model<Api> =>
			typeof entry === "object" &&
			entry !== null &&
			typeof (entry as { id?: unknown }).id === "string",
	);
}

export default async function (pi: ExtensionAPI): Promise<void> {
	// Descending: opencode restarts the id space when a session begins so every
	// later id of that session sorts before the previous one.
	sessionId = `ses_${identifier(true)}`;

	// One registration no matter how often discovery fires: re-registering
	// merges over itself, so the guard keeps startup to a single declaration.
	// Registration runs on `resources_discover` — it fires after the runtime's
	// own snapshot pass on every host (sessions, print, agents) and carries
	// the composed registry. `session_start` is deliberately not used: the
	// runtime is mid-refresh there and rejects provider calls.
	let registered = false;
	const registerFreeTier = (registry: ModelRegistry): void => {
		if (registered) return;

		// `models` keeps the picker populated before the first refresh;
		// `refreshModels` re-projects from pi's own persisted catalog on every
		// refresh cycle. The empty set throws instead of registering a broken
		// list: an empty projection is a broken catalog, and surfacing it
		// here beats hiding the cause until the first request.
		const models = projectFreeTier(registry.getAll());
		if (models.length === 0) {
			throw new Error(
				`pi-opencode: pi's "${PROVIDER_ID}" catalog has no free zen model`,
			);
		}
		pi.registerProvider(PROVIDER_ID, {
			models,
			refreshModels: async (
				context: RefreshModelsContext,
			): Promise<ProviderModelConfig[]> => {
				const free = projectFreeTier(storedModelsOf(context.stored));
				if (free.length === 0) {
					throw new Error(
						`pi-opencode: pi's persisted "${PROVIDER_ID}" catalog projects to no free zen model`,
					);
				}
				return free;
			},
		});
		registered = true;
		// Trigger the cycle that makes the hook authoritative: without this,
		// only a later `pi update --models` or refresh would replace the
		// snapshot. The registry handle is used once, synchronously — a
		// captured handle goes stale after a session replacement or reload
		// and pi throws on any later use, so nothing here is awaited or
		// retried. Both failure paths report: a rejected refresh and a
		// resolved one carrying this provider in its error map.
		void registry.refresh({ providers: [PROVIDER_ID] }).then(
			(result) => {
				const failure = result.errors.get(PROVIDER_ID);
				if (failure !== undefined) {
					console.error(
						`pi-opencode: free-tier refresh failed: ${failure.message}`,
					);
				}
			},
			(error: unknown) => {
				console.error(
					`pi-opencode: free-tier refresh failed: ${error instanceof Error ? error.message : String(error)}`,
				);
			},
		);
	};
	// A failed first attempt leaves `registered` false, so the next
	// discovery pass retries the whole declaration from a fresh `ctx`.
	pi.on("resources_discover", (_event, ctx) => {
		try {
			registerFreeTier(ctx.modelRegistry);
		} catch (error) {
			console.error(
				`pi-opencode: free-tier registration failed: ${error instanceof Error ? error.message : String(error)}`,
			);
		}
	});

	// Both request hooks fire for every provider, so each is scoped to the one
	// this extension exists for.
	pi.on("before_provider_headers", async (event, ctx) => {
		if (ctx.model?.provider !== PROVIDER_ID) return;
		applyWireIdentity(event.headers, ctx.model.api);
	});

	pi.on("before_provider_request", async (event, ctx) => {
		if (ctx.model?.provider !== PROVIDER_ID) return;
		sanitizeRequest(event.payload);
	});
}
