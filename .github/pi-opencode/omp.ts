import process from "node:process";
import { type Api, streamSimple } from "@oh-my-pi/pi-ai";
import catalog from "@oh-my-pi/pi-catalog/models.json";
import { THINKING_EFFORTS } from "@oh-my-pi/pi-catalog/effort";
import type {
	ExtensionAPI,
	ProviderConfig,
	ProviderModelConfig,
} from "@oh-my-pi/pi-coding-agent";
import {
	API_KEY,
	BASE_URL,
	REMOTE_CATALOG_ATTEMPT_TIMEOUT_MS,
	ZEN_ORIGIN,
	type EndpointApi,
	endpoints,
	fetchRemoteCatalog,
	gateByLive,
	initProject,
	isFreeModel,
	makeZenStreamer,
	rotateSession,
} from "./shared.ts";

// The omp host entry: the live pi.dev registry is authoritative (new free
// models surface, deprecated ids never do); the bundled host catalog
// (@oh-my-pi/pi-catalog) only applies while pi.dev is unreachable. Either
// source is gated by the live gateway list, and wire behavior lives in
// shared.ts and is identical to the pi host entry.

interface ZenCatalogEntry {
	id: string;
	name: string;
	api: EndpointApi;
	baseUrl: string;
	reasoning: boolean;
	thinking?: ProviderModelConfig["thinking"];
	// pi.dev registry shape; the bundled snapshot carries `thinking` instead.
	thinkingLevelMap?: Record<string, string | null>;
	input: Array<"text" | "image">;
	cost: {
		input: number;
		output: number;
		cacheRead: number;
		cacheWrite: number;
	};
	contextWindow: number;
	maxTokens: number;
	compat?: ProviderModelConfig["compat"];
}

const ZEN_CATALOG = (
	catalog as unknown as Record<string, Record<string, ZenCatalogEntry>>
)["opencode-zen"];

function buildModelConfig(entry: ZenCatalogEntry): ProviderModelConfig {
	if (!entry.baseUrl.startsWith(ZEN_ORIGIN)) {
		throw new Error(
			`opencode model ${entry.id} baseUrl left ${ZEN_ORIGIN}: ${entry.baseUrl}`,
		);
	}

	endpoints.set(entry.id, {
		api: entry.api,
		baseUrl: entry.baseUrl,
		compat: entry.compat,
	});
	// Effort ladder per source: the bundled snapshot carries `thinking`
	// directly, while pi.dev publishes thinkingLevelMap (level -> wire
	// value, incl. "off"), which maps onto omp's canonical effort order.
	// A registry entry with neither falls back to omp's default ladder.
	const levelMap = entry.thinkingLevelMap;
	const efforts = levelMap
		? THINKING_EFFORTS.filter((level) => level in levelMap)
		: [];
	return {
		id: entry.id,
		name: entry.name,
		reasoning: entry.reasoning,
		...(entry.thinking
			? { thinking: entry.thinking }
			: efforts.length > 0
				? { thinking: { mode: "effort", efforts } }
				: {}),
		input: entry.input,
		cost: entry.cost,
		contextWindow: entry.contextWindow,
		maxTokens: entry.maxTokens,
		...(entry.compat ? { compat: entry.compat } : {}),
	};
}

// The live pi.dev registry is authoritative when reachable (fresh, non-
// empty response); the bundled @oh-my-pi/pi-catalog snapshot only applies
// while pi.dev fetches nothing usable, so boot never depends on the
// network. Registry entries differ from snapshot entries only in the
// thinking metadata (thinkingLevelMap vs thinking — converted in
// buildModelConfig), so the array cast is the single catalog-shape seam;
// either source then crosses gateByLive with the pi host entry.
export async function loadFreeEntries(
	fetchImpl: typeof globalThis.fetch = globalThis.fetch,
): Promise<ZenCatalogEntry[]> {
	const registry = await fetchRemoteCatalog(
		undefined,
		AbortSignal.timeout(REMOTE_CATALOG_ATTEMPT_TIMEOUT_MS),
		fetchImpl,
	);
	const models = registry?.status === "fresh" ? registry.models : undefined;
	const catalog: readonly ZenCatalogEntry[] =
		models && models.length > 0
			? (models as unknown as ZenCatalogEntry[])
			: Object.values(ZEN_CATALOG);
	return gateByLive(catalog.filter(isFreeModel), fetchImpl);
}

export default async function (pi: ExtensionAPI): Promise<void> {
	const entries = await loadFreeEntries();
	if (entries.length === 0) return;
	await initProject(process.cwd());
	pi.on("session_start", rotateSession);

	// Custom api name: omp reserves the built-in api names for its own
	// handlers, so a custom streamSimple must register under a new one; the
	// real per-model endpoint is restored inside the shared streamer.
	pi.registerProvider("opencode", {
		baseUrl: BASE_URL,
		apiKey: API_KEY,
		api: "opencode" as Api,
		streamSimple: makeZenStreamer(
			streamSimple as unknown as Parameters<typeof makeZenStreamer>[0],
		) as unknown as ProviderConfig["streamSimple"],
		models: entries
			.slice()
			.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
			.map((entry) => buildModelConfig(entry)),
	});
}
