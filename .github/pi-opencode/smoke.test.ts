import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
	gateByLive,
	identifier,
	isFreeModel,
	opencodeHeaders,
	sanitizeZenContext,
} from "./shared.ts";

// Shared suite runs on both runtimes (node + bun); the entry suite below
// runs the host matching the runtime: pi.ts under node, omp.ts under bun.

// identifier: 12 hex time chars + 14 base62 random chars, both directions.
for (const descending of [true, false]) {
	const id = identifier(descending);
	assert.equal(id.length, 26, "identifier is 26 chars");
	assert.match(id, /^[0-9a-f]{12}[0-9A-Za-z]{14}$/, "identifier format");
}

// Headers carry the full opencode CLI wire shape with fresh generated ids.
const headers = opencodeHeaders("openai-completions");
assert.deepEqual(
	Object.keys(headers).sort(),
	[
		"User-Agent",
		"x-opencode-client",
		"x-opencode-project",
		"x-opencode-request",
		"x-opencode-session",
	],
	"all five wire headers present",
);
assert.match(
	headers["x-opencode-session"],
	/^ses_[0-9a-f]{12}[0-9A-Za-z]{14}$/,
	"session id shape",
);
assert.match(
	headers["x-opencode-request"],
	/^msg_[0-9a-f]{12}[0-9A-Za-z]{14}$/,
	"request id shape",
);
assert.equal(headers["x-opencode-project"], "global");
assert.match(
	headers["User-Agent"],
	/^opencode\/1\.18\.32 ai-sdk\/provider-utils\/4\.0\.23 runtime\/bun\//,
	"chat-completions UA pin",
);

// Live gate: retired models drop, unknown live ids never inject, and any
// failure shape falls back to the full list so boot never depends on it.
const jsonFetch = (body: unknown) =>
	(async () => ({ ok: true, status: 200, json: async () => body })) as unknown as typeof fetch;
const candidates = [
	{ id: "big-pickle" },
	{ id: "hy3-free" },
	{ id: "mimo-v2.6-flash-free" },
];
assert.deepEqual(
	(
		await gateByLive(
			candidates,
			jsonFetch({ data: [{ id: "big-pickle" }, { id: "mimo-v2.6-flash-free" }] }),
		)
	).map((model) => model.id),
	["big-pickle", "mimo-v2.6-flash-free"],
	"retired model gated out",
);
assert.deepEqual(
	(
		await gateByLive([{ id: "big-pickle" }], jsonFetch({ data: [{ id: "big-pickle" }, { id: "not-a-real-model" }] }))
	).map((model) => model.id),
	["big-pickle"],
	"unknown live id does not inject models",
);
assert.equal(
	(await gateByLive(candidates, (() => Promise.reject(new Error("offline"))) as typeof fetch)).length,
	3,
	"fetch failure falls back to the full list",
);
assert.equal(
	(await gateByLive(candidates, jsonFetch({ data: [] }))).length,
	3,
	"empty live list falls back to the full list",
);
assert.equal(
	(await gateByLive(candidates, (async () => ({ ok: false, status: 500, json: async () => ({}) })) as unknown as typeof fetch)).length,
	3,
	"non-200 falls back to the full list",
);

// Permanently-retired ids (deprecated/dead upstream) drop on every path:
// offline, where the bundled fallback has no registry to learn from, and
// online even when the gateway /models list still carries them.
assert.deepEqual(
	(
		await gateByLive(
			[{ id: "big-pickle" }, { id: "mimo-v2.5-free" }],
			(() => Promise.reject(new Error("offline"))) as typeof fetch,
		)
	).map((model) => model.id),
	["big-pickle"],
	"retired id drops offline",
);
assert.deepEqual(
	(
		await gateByLive(
			[{ id: "big-pickle" }, { id: "mimo-v2.5-free" }, { id: "deepseek-v4-flash-free" }],
			jsonFetch({ data: [{ id: "big-pickle" }, { id: "mimo-v2.5-free" }, { id: "deepseek-v4-flash-free" }] }),
		)
	).map((model) => model.id),
	["big-pickle"],
	"gateway-listed retired ids drop online",
);

// Free filter: both cost legs must be zero.
assert.ok(isFreeModel({ cost: { input: 0, output: 0 } }), "zero cost is free");
assert.ok(!isFreeModel({ cost: { input: 1, output: 0 } }), "paid model is not free");

// Sanitize: empty call ids repair, redacted thinking blocks drop/convert.
type Ctx = Parameters<typeof sanitizeZenContext>[0];
const sanitized = sanitizeZenContext(
	{
		messages: [
			{
				role: "assistant",
				content: [
					{ type: "thinking", thinking: "", redacted: true },
					{ type: "thinking", thinking: "keep me", redacted: true },
					{
						type: "toolCall",
						id: "___",
						name: "bash",
						arguments: { command: "true" },
					},
				],
			},
			{
				role: "toolResult",
				toolCallId: "___",
				toolName: "bash",
				content: [{ type: "text", text: "ok" }],
			},
		],
	} as unknown as Ctx,
	"openai-completions",
);
const assistant = sanitized.messages[0];
assert.equal(assistant.content.length, 2, "redacted empty thinking dropped");
const firstBlock = assistant.content[0];
if (typeof firstBlock === "string") throw new Error("expected a text block");
assert.equal(firstBlock.type, "text", "redacted thinking converted to text");
assert.equal(
	(firstBlock as { text: string }).text,
	"keep me",
	"redacted thinking text preserved",
);
assert.match(
	(assistant.content[1] as { id: string }).id,
	/^call_repaired_[0-9a-f]{8}$/,
	"empty tool call id repaired",
);
const repairedMsg = sanitized.messages[1];
if (repairedMsg.role !== "toolResult") {
	throw new Error("expected a toolResult message");
}
assert.equal(
	repairedMsg.toolCallId,
	(assistant.content[1] as { id: string }).id,
	"matching tool result id repaired identically",
);

const isBun = typeof (globalThis as { Bun?: unknown }).Bun !== "undefined";

if (!isBun) {
	// ── pi entry (node) ──────────────────────────────────────────────────
	type CapturedModel = {
		id: string;
		name: string;
		cost?: { input?: number; output?: number };
		contextWindow: number;
		maxTokens: number;
	};

	type RegisteredProvider = {
		models: CapturedModel[];
		refreshModels?: (context: {
			stored?: unknown;
			publish: (publication: {
				persist?: unknown;
				update?: () => void;
			}) => Promise<boolean> | boolean;
			allowNetwork?: boolean;
			force?: boolean;
			signal?: AbortSignal;
		}) => Promise<CapturedModel[]>;
	};

	// getAgentDir() resolves the models-store path at module load, so the env
	// override and the fixture must exist before pi.ts is imported.
	const agentDir = await mkdtemp(path.join(tmpdir(), "pi-opencode-smoke-"));
	process.env.PI_CODING_AGENT_DIR = agentDir;
	const storePath = path.join(agentDir, "models-store.json");

	const storedModel = (
		id: string,
		cost = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
	) => ({
		id,
		name: id,
		provider: "opencode",
		api: "openai-completions",
		baseUrl: "https://opencode.ai/zen/v1",
		reasoning: true,
		input: ["text"],
		cost,
		contextWindow: 200000,
		maxTokens: 32000,
	});

	async function writeStore(
		models: unknown[],
		lastModified: number,
		extra: Record<string, unknown> = {},
	) {
		await writeFile(
			storePath,
			JSON.stringify({ opencode: { models, lastModified, ...extra } }),
		);
	}

	// The store carries one free model the fresh pi.dev registry below does
	// not publish (boot precedence), one paid entry (silently skipped) and
	// two malformed entries (warned) — the revalidation contract. The free
	// model the boot list must surface comes from the pi.dev fetch.
	await writeStore(
		[
			storedModel("claude-opus-5", {
				input: 15,
				output: 75,
				cacheRead: 1.5,
				cacheWrite: 18.75,
			}),
			storedModel("stale-store-free"),
			{ id: "broken-model", name: "broken", api: "telnet" },
			"not-an-object",
		],
		Date.now(),
	);

	const { getBuiltinModelDataGeneratedAt, getBuiltinModels } = await import(
		"@earendil-works/pi-ai/providers/all"
	);
	const generatedAt = getBuiltinModelDataGeneratedAt();
	assert.equal(typeof generatedAt, "number", "bundled catalog has generated-at");

	const bundledFreeIds = getBuiltinModels("opencode")
		.filter(
			(model) =>
				(model.cost?.input ?? 0) === 0 && (model.cost?.output ?? 0) === 0,
		)
		.map((model) => model.id);
	assert(
		bundledFreeIds.includes("mimo-v2.6-flash-free"),
		"bundled baseline contains the mimo regression case",
	);

	let registered: { id: string; config: RegisteredProvider } | undefined;
	const events: string[] = [];
	const pi = {
		on(event: string, _handler: () => void) {
			events.push(event);
		},
		registerProvider(id: string, config: RegisteredProvider) {
			registered = { id, config };
		},
	};

	const warnings: string[] = [];
	const originalWarn = console.warn;
	console.warn = (...args: unknown[]) => {
		warnings.push(args.map(String).join(" "));
	};

	const realFetch = globalThis.fetch;
	// Baseline dispatcher: the live gate gets an empty id list (allow-all via
	// the fallback rule), while pi.dev requests are counted separately.
	const GATE_URL = "https://opencode.ai/zen/v1/models";
	let liveIds: string[] | undefined;
	let remoteFetches = 0;
	let remoteJson: (() => Promise<unknown>) | undefined;
	let remoteStatus = 200;
	const dispatcher = (async (input: RequestInfo | URL) => {
		const url = String(input);
		if (url === GATE_URL) {
			return {
				ok: true,
				status: 200,
				json: async () => ({ data: (liveIds ?? []).map((id) => ({ id })) }),
			};
		}
		remoteFetches += 1;
		const handler = remoteJson;
		return {
			status: remoteStatus,
			ok: remoteStatus >= 200 && remoteStatus < 300,
			headers: new Headers({
				"last-modified": new Date().toUTCString(),
				etag: '"smoke-etag"',
			}),
			json: async () => (handler ? handler() : {}),
		};
	}) as unknown as typeof fetch;
	globalThis.fetch = dispatcher;
	// Boot source: pi.dev publishes space-bunny-free, which the bundled pi-ai
	// 0.87.1 catalog lacks — the exact "new free model" case the boot catalog
	// fetch must surface.
	remoteJson = async () => ({
		"space-bunny-free": { ...storedModel("space-bunny-free"), provider: "opencode" },
	});

	try {
		// Dynamic on purpose: pi.ts resolves the models-store path through
		// getAgentDir() at module load, so the PI_CODING_AGENT_DIR fixture
		// above must be in place before this import evaluates.
		const { default: extension } = await import("./pi.ts");
		await extension(pi as unknown as Parameters<typeof extension>[0]);

		assert.ok(registered, "provider registered");
		assert.equal(registered.id, "opencode");
		assert.ok(events.includes("session_start"), "session_start wired");
		assert.equal(remoteFetches, 1, "boot fetches the pi.dev catalog");

		// Boot: bundled free models plus the pi.dev-only free model, sorted
		// by id; the paid entry, the stale store cache and both malformed
		// entries are excluded.
		const expected = [...bundledFreeIds, "space-bunny-free"].sort();
		assert.deepEqual(
			registered.config.models.map((model) => model.id),
			expected,
			"boot models = bundled free + pi.dev free, sorted",
		);
		assert.ok(
			!registered.config.models.some((model) => model.id === "stale-store-free"),
			"fresh boot registry supersedes the stale store cache",
		);
		assert.equal(
			warnings.length,
			2,
			`both malformed entries warned exactly once: ${warnings.join(" | ")}`,
		);
		assert(
			registered.config.models.every(
				(model) =>
					(model.cost?.input ?? 1) === 0 && (model.cost?.output ?? 1) === 0,
			),
			"only free models surface",
		);
		const bunny = registered.config.models.find(
			(model) => model.id === "space-bunny-free",
		);
		assert.ok(bunny, "pi.dev-only model registered");
		assert.equal(bunny.name, "space-bunny-free");
		assert.ok(bunny.contextWindow > 0 && bunny.maxTokens > 0);

		const refresh = registered.config.refreshModels;
		assert.ok(refresh, "refreshModels registered");

		const published: { persist?: unknown; update?: unknown }[] = [];
		const offline = (stored?: unknown) => ({
			stored,
			publish: (publication: { persist?: unknown; update?: () => void }) => {
				published.push(publication);
				return true;
			},
		});

		// Live gate applies to the pi list: dropping one id from /models
		// removes that model from the refreshed registration.
		const bootIds = registered.config.models.map((model) => model.id);
		const droppedId = bootIds[bootIds.length - 1];
		liveIds = bootIds.filter((id) => id !== droppedId);
		const gated = await refresh(offline());
		assert.ok(
			!gated.some((model) => model.id === droppedId),
			"retired model gated out of the pi list",
		);
		assert.equal(gated.length, bootIds.length - 1, "only the retired id drops");
		liveIds = undefined;

		// Freshness gate: a Last-Modified older than the bundled generated-at
		// never overrides the bundled catalog (mirrors withRemoteCatalog); the
		// boot pi.dev overlay still applies on its own.
		await writeStore([storedModel("space-bunny-free")], 1);
		assert.deepEqual(
			(await refresh(offline())).map((model) => model.id),
			[...bundledFreeIds, "space-bunny-free"].sort(),
			"stale store overlay gated out, boot overlay kept",
		);

		// Re-read: a rewritten store is picked up without a restart.
		await writeStore([storedModel("space-bunny-free")], Date.now());
		assert.ok(
			(await refresh(offline())).some((model) => model.id === "space-bunny-free"),
			"refresh re-reads the store",
		);

		// Context restore: the host-managed entry wins without touching the file.
		await rm(storePath);
		const freshEntry = {
			models: [storedModel("space-bunny-free")],
			lastModified: Date.now(),
			checkedAt: Date.now(),
		};
		assert.ok(
			(await refresh(offline(freshEntry))).some(
				(model) => model.id === "space-bunny-free",
			),
			"refresh restores context.stored",
		);

		// Missing store: bundled catalog still works, ENOENT stays silent.
		// (Each refresh re-validates the store, so earlier malformed-entry
		// warnings re-fire on re-reads; the contract here is: no new ones.)
		const warningsBeforeMissingStore = warnings.length;
		assert.deepEqual(
			(await refresh(offline())).map((model) => model.id),
			[...bundledFreeIds, "space-bunny-free"].sort(),
			"missing store falls back to bundled models plus boot overlay",
		);
		assert.equal(
			warnings.length,
			warningsBeforeMissingStore,
			"missing store does not warn",
		);

		// Corrupt store: warned, not hidden, and the bundled catalog applies.
		const warningsBeforeCorrupt = warnings.length;
		await writeFile(storePath, "{{{");
		assert.deepEqual(
			(await refresh(offline())).map((model) => model.id),
			[...bundledFreeIds, "space-bunny-free"].sort(),
			"corrupt store falls back to bundled models plus boot overlay",
		);
		assert.equal(
			warnings.length,
			warningsBeforeCorrupt + 1,
			"corrupt store warns",
		);
		assert.match(warnings[warnings.length - 1], /not valid JSON/);
		await rm(storePath, { force: true });

		// Network revalidate: a stale checkedAt fetches the pi.dev catalog, the
		// new free model registers, and persistence carries checkedAt + etag.
		const remoteModels = {
			"glimmer-free": {
				...storedModel("glimmer-free"),
				provider: "opencode",
			},
		};
		remoteStatus = 200;
		remoteJson = async () => remoteModels;
		const staleEntry = {
			models: [storedModel("space-bunny-free")],
			// lastModified must beat the bundled generated-at to apply...
			lastModified: Date.now(),
			// ...while checkedAt stays old enough to force revalidation.
			checkedAt: 1,
		};
		remoteFetches = 0;
		const refreshed = await refresh({
			...offline(staleEntry),
			allowNetwork: true,
		});
		assert.equal(remoteFetches, 1, "stale checkedAt revalidates pi.dev");
		assert.ok(
			refreshed.some((model) => model.id === "glimmer-free"),
			"live free model registers",
		);
		assert.ok(
			!refreshed.some((model) => model.id === "space-bunny-free"),
			"bundled baseline still applies without the file overlay",
		);
		const persisted = published.filter((call) => call.persist !== undefined);
		assert.ok(persisted.length > 0, "refresh persists the store entry");
		const lastPersist = persisted[persisted.length - 1].persist as {
			checkedAt: number;
			etag: string;
			models: { id: string }[];
		};
		assert.ok(lastPersist.checkedAt > 1, "persist carries checkedAt");
		assert.equal(lastPersist.etag, '"smoke-etag"', "persist carries etag");
		assert.ok(
			lastPersist.models.some((model) => model.id === "glimmer-free"),
			"persist carries the live catalog",
		);

		// Throttle: a fresh checkedAt skips the network (mirrors the host 4h
		// window).
		remoteFetches = 0;
		const throttled = await refresh({
			...offline({ ...staleEntry, checkedAt: Date.now() }),
			allowNetwork: true,
		});
		assert.equal(remoteFetches, 0, "fresh checkedAt skips fetch");
		assert.ok(
			throttled.some((model) => model.id === "space-bunny-free"),
			"throttled refresh keeps the stored overlay",
		);

		// The file-read fallback carries the same freshness metadata as
		// context.stored, so a fresh checkedAt inside the store file
		// throttles the network instead of forcing a fetch every refresh.
		await writeStore([storedModel("space-bunny-free")], Date.now(), {
			checkedAt: Date.now(),
			etag: '"file-etag"',
		});
		remoteFetches = 0;
		const fileThrottled = await refresh({ ...offline(), allowNetwork: true });
		assert.equal(
			remoteFetches,
			0,
			"file-read fallback keeps the throttle metadata",
		);
		assert.ok(
			fileThrottled.some((model) => model.id === "space-bunny-free"),
			"file-read store serves the overlay",
		);
		await rm(storePath, { force: true });

		// 304: unchanged catalog only moves the freshness window.
		remoteStatus = 304;
		const notModified = await refresh({
			...offline(staleEntry),
			allowNetwork: true,
		});
		assert.ok(
			notModified.some((model) => model.id === "space-bunny-free"),
			"304 keeps serving the overlay",
		);

		// Transient failure: the overlay keeps serving, validator untouched.
		remoteStatus = 500;
		const persistsBefore = published.filter(
			(call) => call.persist !== undefined,
		).length;
		const offlineServed = await refresh({
			...offline(staleEntry),
			allowNetwork: true,
		});
		assert.ok(
			offlineServed.some((model) => model.id === "space-bunny-free"),
			"fetch failure keeps serving the overlay",
		);
		assert.equal(
			published.filter((call) => call.persist !== undefined).length,
			persistsBefore,
			"fetch failure persists nothing",
		);
	} finally {
		globalThis.fetch = realFetch;
		console.warn = originalWarn;
		await rm(agentDir, { recursive: true, force: true });
	}
} else {
	// ── omp entry (bun) ──────────────────────────────────────────────────
	// Dynamic on purpose: pi.ts/omp.ts are runtime-selected entries, and
	// omp.ts's JSON import only resolves under the host runtime (bun).
	const { default: extension, loadFreeEntries } = await import("./omp.ts");

	const liveIds = (ids: string[]) =>
		(async (input: RequestInfo | URL) =>
			String(input).endsWith("/models")
				? { ok: true, status: 200, json: async () => ({ data: ids.map((id) => ({ id })) }) }
				: { ok: false, status: 500, json: async () => ({}) }) as unknown as typeof fetch;

	// Gate through the omp wrapper: only free catalog entries present on the
	// live gateway survive; failures fall back to the full free catalog.
	const gated = await loadFreeEntries(
		liveIds(["big-pickle", "mimo-v2.6-flash-free", "not-in-catalog"]),
	);
	const gatedIds = gated.map((entry) => entry.id);
	assert.ok(gatedIds.includes("big-pickle"), "live free model kept");
	assert.ok(gatedIds.includes("mimo-v2.6-flash-free"), "live free model kept");
	assert.ok(!gatedIds.includes("hy3-free"), "retired model gated out");
	assert.ok(
		!gatedIds.includes("not-in-catalog"),
		"unknown live id does not inject models",
	);
	assert.ok(
		gated.every((entry) => entry.cost.input === 0 && entry.cost.output === 0),
		"only free models surface",
	);
	assert.ok(
		(await loadFreeEntries((() => Promise.reject(new Error("offline"))) as typeof fetch)).length >
			gated.length,
		"offline falls back to the full free catalog",
	);
	assert.ok(
		(await loadFreeEntries(liveIds([]))).length > gated.length,
		"empty live list falls back to the full free catalog",
	);

	// Offline: the bundled snapshot applies, but permanently-retired ids
	// drop there too (no registry is reachable, so only the chokepoint
	// gate can know), and the snapshot's per-model effort ladders survive.
	const offlineEntries = await loadFreeEntries(
		(() => Promise.reject(new Error("offline"))) as typeof fetch,
	);
	assert.ok(
		!offlineEntries.some((entry) => entry.id === "mimo-v2.5-free"),
		"offline snapshot drops the retired id",
	);
	assert.ok(
		!offlineEntries.some((entry) => entry.id === "deepseek-v4-flash-free"),
		"offline snapshot drops the dead id",
	);
	assert.ok(
		offlineEntries.find((entry) => entry.id === "big-pickle")?.thinking,
		"snapshot effort ladder intact offline",
	);

	// Registry: a reachable pi.dev catalog replaces the bundled snapshot —
	// newly published free models (space-bunny-free) surface, deprecated
	// snapshot ids (mimo-v2.5-free, deepseek-v4-flash-free) never do, and
	// paid registry entries stay filtered out.
	const registryModel = (id: string) => ({
		id,
		name: id,
		provider: "opencode",
		api: "openai-completions",
		baseUrl: "https://opencode.ai/zen/v1",
		reasoning: true,
		input: ["text"],
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: 200000,
		maxTokens: 32000,
	});
	const registryFetch = (async (input: RequestInfo | URL) =>
		String(input).includes("pi.dev")
			? {
					ok: true,
					status: 200,
					headers: new Headers(),
					json: async () => ({
						"space-bunny-free": {
							...registryModel("space-bunny-free"),
							// pi.dev's level -> wire-value map; "off" is not an
							// Effort, so the converted ladder is six real levels.
							thinkingLevelMap: {
								off: null,
								minimal: null,
								low: "low",
								medium: "medium",
								high: "high",
								xhigh: "xhigh",
								max: "max",
							},
						},
						"big-pickle": registryModel("big-pickle"),
						"claude-opus-5": {
							...registryModel("claude-opus-5"),
							cost: { input: 15, output: 75, cacheRead: 1.5, cacheWrite: 18.75 },
						},
					}),
				}
			: { ok: true, status: 200, json: async () => ({ data: [] }) }) as unknown as typeof fetch;
	const registryIds = (await loadFreeEntries(registryFetch)).map((entry) => entry.id);
	assert.deepEqual(
		[...registryIds].sort(),
		["big-pickle", "space-bunny-free"],
		"pi.dev registry replaces the snapshot",
	);
	assert.ok(
		!registryIds.includes("mimo-v2.5-free"),
		"deprecated snapshot id never surfaces",
	);
	assert.ok(
		!registryIds.includes("deepseek-v4-flash-free"),
		"dead snapshot id never surfaces",
	);

	// Registration: sorted free models on the single opencode provider, from
	// the live pi.dev registry (the gateway gate stays allow-all for
	// determinism), including the effort ladder converted from thinkingLevelMap.
	const realFetch = globalThis.fetch;
	globalThis.fetch = registryFetch;
	try {
		const registered: {
			id: string;
			config: {
				models: {
					id: string;
					thinking?: { mode: string; efforts: readonly string[] };
				}[];
			};
		}[] = [];
		const pi = {
			on() {},
			registerProvider(
				id: string,
				config: {
					models: {
						id: string;
						thinking?: { mode: string; efforts: readonly string[] };
					}[];
				},
			) {
				registered.push({ id, config });
			},
		};
		await extension(pi as never);
		assert.equal(registered.length, 1, "exactly one provider registered");
		assert.equal(registered[0].id, "opencode");
		const modelIds = registered[0].config.models.map((model) => model.id);
		assert.deepEqual(
			[...modelIds].sort(),
			["big-pickle", "space-bunny-free"],
			"registry free models registered, sorted by id",
		);
		const bunny = registered[0].config.models.find(
			(model) => model.id === "space-bunny-free",
		);
		assert.deepEqual(
			bunny?.thinking,
			{
				mode: "effort",
				efforts: ["minimal", "low", "medium", "high", "xhigh", "max"],
			},
			"registry thinkingLevelMap converts to the canonical effort ladder",
		);
	} finally {
		globalThis.fetch = realFetch;
	}
}

console.log(`pi-opencode smoke test passed (${isBun ? "bun" : "node"})`);
