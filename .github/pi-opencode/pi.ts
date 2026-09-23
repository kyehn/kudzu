import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { type Api, type Model, streamSimple } from "@earendil-works/pi-ai/compat";
// Baseline catalog and its freshness gate must come from the same module:
// the host aliases providers/all to its bundled copy, so baseline models and
// generated-at always resolve to the same copy and cannot drift apart.
import {
	getBuiltinModelDataGeneratedAt,
	getBuiltinModels,
} from "@earendil-works/pi-ai/providers/all";
import {
	type ExtensionAPI,
	getAgentDir,
	type ProviderConfig,
	type ProviderModelConfig,
} from "@earendil-works/pi-coding-agent";
import {
	API_KEY,
	BASE_URL,
	REMOTE_CATALOG_ATTEMPT_TIMEOUT_MS,
	endpoints,
	fetchRemoteCatalog,
	gateByLive,
	initProject,
	isEndpointApi,
	isFreeModel,
	makeZenStreamer,
	normalizeZenModel,
	rotateSession,
} from "./shared.ts";

// The pi host entry: bundled pi-ai catalog overlaid by the pi.dev registry
// (fetched at boot and by the host's refresh protocol, whose last success
// persists in models-store.json), gated by the live gateway list. Wire
// behavior lives in shared.ts and is identical to the omp host entry.

// Host refresh cadence: the same 4h window withRemoteCatalog uses. The boot
// fetch itself always runs, because headless `pi -p` sessions never trigger
// the host's network refresh (allowModelNetwork stays false there).
const REMOTE_CATALOG_REFRESH_INTERVAL_MS = 4 * 60 * 60 * 1000;

// FileModelsStore's default path; getAgentDir honors PI_CODING_AGENT_DIR.
const MODELS_STORE_PATH = path.join(getAgentDir(), "models-store.json");

interface StoreEntry {
	models: Model<Api>[];
	lastModified?: number;
	checkedAt?: number;
	etag?: string;
}

// Freshness gate: mirror the host's withRemoteCatalog/remoteModels — the
// stored overlay only wins when its Last-Modified beats the bundled data's
// generated-at, so a stale cache can never override newer bundled models.
function overlayIsFresh(lastModified: number | undefined): boolean {
	const generatedAt = getBuiltinModelDataGeneratedAt();
	return (
		generatedAt === undefined ||
		(lastModified !== undefined && lastModified > generatedAt)
	);
}

function parseStoreEntry(value: unknown): StoreEntry | undefined {
	if (typeof value !== "object" || value === null) return undefined;
	const entry = value as Record<string, unknown>;
	const lastModified =
		typeof entry.lastModified === "number" ? entry.lastModified : undefined;
	if (!overlayIsFresh(lastModified)) return undefined;
	if (!Array.isArray(entry.models)) return undefined;
	return {
		models: entry.models
			.map((model) => normalizeZenModel(model, "models-store entry"))
			.filter((model): model is Model<Api> => model !== undefined),
		lastModified,
		checkedAt:
			typeof entry.checkedAt === "number" ? entry.checkedAt : undefined,
		etag: typeof entry.etag === "string" ? entry.etag : undefined,
	};
}

// The pi.dev catalog cache the host persists through FileModelsStore. The
// host never refreshes the store for "opencode" while this extension shadows
// the built-in provider, so this extension owns the entry: it restores
// context.stored, revalidates against pi.dev, and publishes persistence
// itself. Undefined means there is no usable overlay: the bundled catalog
// applies. The full entry (models + freshness metadata) is returned so the
// refresh path keeps its throttle/etag state on this fallback too.
async function readStoredEntry(): Promise<StoreEntry | undefined> {
	let raw: string;
	try {
		raw = await readFile(MODELS_STORE_PATH, "utf8");
	} catch {
		// First run without a cache is normal and needs no warning.
		return undefined;
	}
	let stored: unknown;
	try {
		const parsed: unknown = JSON.parse(raw);
		stored =
			typeof parsed === "object" && parsed !== null && "opencode" in parsed
				? parsed.opencode
				: undefined;
	} catch {
		console.warn(
			`pi-opencode: ${MODELS_STORE_PATH} is not valid JSON; using the bundled catalog`,
		);
		return undefined;
	}
	const entry = parseStoreEntry(stored);
	if (entry === undefined) {
		if (
			typeof stored === "object" &&
			stored !== null &&
			!Array.isArray((stored as { models?: unknown }).models)
		) {
			console.warn(
				`pi-opencode: ${MODELS_STORE_PATH} has no models array; using the bundled catalog`,
			);
		}
		return undefined;
	}
	return entry;
}

function buildModelConfig(model: Model<Api>): ProviderModelConfig {
	// Both guards are loud on purpose: the bundled catalog is our own build
	// data, so drift there is a bug to surface, while stored entries were
	// already validated (and skipped) in normalizeZenModel.
	if (model.baseUrl !== BASE_URL) {
		throw new Error(
			`opencode model ${model.id} baseUrl drifted to ${model.baseUrl}; update BASE_URL routing`,
		);
	}
	if (!isEndpointApi(model.api)) {
		throw new Error(
			`opencode model ${model.id} api drifted to ${model.api}; update EndpointApi routing`,
		);
	}

	endpoints.set(model.id, {
		api: model.api,
		baseUrl: model.baseUrl,
		compat: model.compat,
	});
	return {
		id: model.id,
		name: model.name,
		reasoning: model.reasoning,
		input: model.input,
		cost: model.cost,
		contextWindow: model.contextWindow,
		maxTokens: model.maxTokens,
		...(model.compat ? { compat: model.compat } : {}),
		...(model.thinkingLevelMap
			? { thinkingLevelMap: model.thinkingLevelMap }
			: {}),
	};
}

// Last successful pi.dev fetch (boot or refresh): a fresh refresh fetch
// supersedes it, transient failures keep serving it, so headless sessions
// still see the live registry between host refreshes.
let piDevOverlay: readonly Model<Api>[] = [];

// Free models: bundled snapshot, then the freshness-gated pi.dev store
// cache, then the last pi.dev fetch, all gated by the live gateway list so
// a model retired from /models never surfaces, sorted by id — so free
// models published after the last pi release register without an extension
// update.
function mergeCatalogs(
	stored: readonly Model<Api>[] | undefined,
	overlay: readonly Model<Api>[] = piDevOverlay,
): Map<string, Model<Api>> {
	const catalog = new Map<string, Model<Api>>();
	for (const model of getBuiltinModels("opencode")) {
		catalog.set(model.id, model);
	}
	for (const model of stored ?? []) {
		catalog.set(model.id, model);
	}
	for (const model of overlay) {
		catalog.set(model.id, model);
	}
	return catalog;
}

async function buildFreeConfigs(
	catalog: Map<string, Model<Api>>,
): Promise<ProviderModelConfig[]> {
	const free = [...catalog.values()].filter(isFreeModel);
	const live = await gateByLive(free);
	return live
		.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
		.map(buildModelConfig);
}

// Boot: the store cache and the pi.dev registry fetch run in parallel, so
// headless sessions (which never trigger the host's refresh protocol) see
// the live registry: a fresh boot fetch supersedes the store cache — the
// store is the same pi.dev payload, only older — while a failed boot fetch
// keeps serving it, and either way the result crosses the live gate.
async function loadFreeModelConfigs(): Promise<ProviderModelConfig[]> {
	const [stored, boot] = await Promise.all([
		readStoredEntry(),
		fetchRemoteCatalog(
			undefined,
			AbortSignal.timeout(REMOTE_CATALOG_ATTEMPT_TIMEOUT_MS),
		),
	]);
	const bootFresh = boot?.status === "fresh";
	if (bootFresh) piDevOverlay = boot.models;
	return buildFreeConfigs(
		mergeCatalogs(bootFresh ? undefined : stored?.models),
	);
}

interface RefreshModelsContext {
	stored?: unknown;
	publish: (publication: {
		persist?: unknown;
		update?: () => void;
	}) => Promise<boolean> | boolean;
	allowNetwork?: boolean;
	force?: boolean;
	signal?: AbortSignal;
}

// Host refresh protocol, mirrored from withRemoteCatalog: restore the stored
// overlay, then revalidate against pi.dev at most every 4h. The returned
// configs become the synchronous list; the explicit persist write owns the
// store entry (the host never persists for a shadowed provider).
async function refreshFreeModels(
	context: RefreshModelsContext,
): Promise<ProviderModelConfig[]> {
	// context.stored is the host-managed entry; the file is this
	// extension's own fallback. Both keep freshness metadata, so the 4h
	// throttle and etag revalidation behave identically on either path.
	const stored =
		parseStoreEntry(context.stored) ?? (await readStoredEntry());
	const configs = () => buildFreeConfigs(mergeCatalogs(stored?.models));
	if (
		!context.allowNetwork ||
		(!context.force &&
			stored?.checkedAt !== undefined &&
			stored.lastModified !== undefined &&
			Date.now() - stored.checkedAt < REMOTE_CATALOG_REFRESH_INTERVAL_MS)
	) {
		return configs();
	}
	const signals = [AbortSignal.timeout(REMOTE_CATALOG_ATTEMPT_TIMEOUT_MS)];
	if (context.signal) signals.push(context.signal);
	const fetched = await fetchRemoteCatalog(
		stored?.etag,
		AbortSignal.any(signals),
	);
	const checkedAt = Date.now();
	if (fetched === undefined) {
		// Transient failure: keep serving the overlay, leave the validator.
		return configs();
	}
	if (fetched.status === "revalidated" && stored) {
		await context.publish({
			persist: {
				models: stored.models,
				lastModified: stored.lastModified,
				checkedAt,
				etag: stored.etag,
			},
		});
		return configs();
	}
	if (fetched.status === "fresh") {
		piDevOverlay = fetched.models;
		await context.publish({
			persist: {
				models: fetched.models,
				checkedAt,
				lastModified: fetched.lastModified,
				etag: fetched.etag,
			},
		});
		return buildFreeConfigs(mergeCatalogs(undefined, fetched.models));
	}
	return configs();
}

export default async function (pi: ExtensionAPI): Promise<void> {
	const initialModels = await loadFreeModelConfigs();
	if (initialModels.length === 0) return;
	await initProject(process.cwd());
	pi.on("session_start", rotateSession);

	pi.registerProvider("opencode", {
		baseUrl: BASE_URL,
		apiKey: API_KEY,
		api: "openai-completions",
		streamSimple:
			makeZenStreamer(streamSimple) as unknown as ProviderConfig["streamSimple"],
		models: initialModels,
		// The host swaps in whatever this callback returns as the synchronous
		// list; persistence is owned here via context.publish because the
		// host never refreshes the store for a shadowed provider.
		refreshModels: refreshFreeModels as ProviderConfig["refreshModels"],
	});
}
