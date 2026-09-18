/**
 * Wire-sim for OpenCode Zen: match real CLI (1.18.31) on headers.
 * Route: host-based (any opencode.ai/zen), not a free-model subset.
 * Live A/B proved: headers-only -> 200; no body patching needed.
 * Server only checks: model name + API key + headers. No tools/system.
 */
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

const BASE_URL = "https://opencode.ai/zen/v1";
const OPENCODE_VERSION = "1.18.31";
const USER_AGENT = `opencode/${OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`;
const apiKey = process.env.OPENCODE_API_KEY?.trim() || "public";

type EndpointApi =
	| "anthropic-messages"
	| "google-generative-ai"
	| "openai-completions"
	| "openai-responses";

const isZenUrl = (url: string): boolean =>
	url.includes("opencode.ai/zen") || url.includes("zenmux.ai");

const RANDOM_CHARS =
	"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
let lastTimestamp = 0;
let counter = 0;
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
	return (
		time + Array.from(randomBytes(14), (b) => RANDOM_CHARS[b % 62]).join("")
	);
}
const SESSION_ID = `ses_${identifier(true)}`;

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
const compareStrings = (a: string, b: string): number =>
	a === b ? 0 : a < b ? -1 : 1;
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
		if (scp?.[2] && scp?.[3]) return parts(scp[2], scp[3]);
		return undefined;
	}
}
async function resolveProjectId(cwd: string): Promise<string> {
	const commonDirRaw = await gitOut(cwd, ["rev-parse", "--git-common-dir"]);
	if (!commonDirRaw) return "global";
	const commonDir = path.isAbsolute(commonDirRaw)
		? commonDirRaw
		: path.resolve(cwd, commonDirRaw);
	const origin = await gitOut(cwd, ["remote", "get-url", "origin"]);
	const normalized = origin ? normalizeRemote(origin) : undefined;
	if (normalized)
		return createHash("sha1").update(`git-remote:${normalized}`).digest("hex");
	try {
		const cached = (
			await readFile(path.join(commonDir, "opencode"), "utf8")
		).trim();
		if (cached) return cached;
	} catch {}
	const roots = await gitOut(cwd, ["rev-list", "--max-parents=0", "HEAD"]);
	return (
		roots
			?.split("\n")
			.map((l) => l.trim())
			.filter(Boolean)
			.sort(compareStrings)[0] ?? "global"
	);
}
let projectId: string | undefined;
const getProjectId = (): string => projectId ?? "global";
const opencodeHeaders = (): Record<string, string> => ({
	"User-Agent": USER_AGENT,
	"x-opencode-client": "cli",
	"x-opencode-project": getProjectId(),
	"x-opencode-session": SESSION_ID,
	"x-opencode-request": `msg_${identifier(false)}`,
});

function sanitizeHeaders(headers: Headers): void {
	for (const key of Array.from(headers.keys())) {
		const lower = key.toLowerCase();
		if (lower.startsWith("x-stainless-")) headers.delete(key);
		else if (lower === "authorization" && headers.get(key)?.includes("public"))
			headers.delete(key);
	}
}
function createOpencodeFetch(sessionId: string): typeof fetch {
	const baseFetch = globalThis.fetch.bind(globalThis);
	return (async (
		input: RequestInfo | URL,
		init?: RequestInit,
	): Promise<Response> => {
		let url: string;
		let headers: Headers;
		let bodyText: string | undefined;
		if (input instanceof Request) {
			url = input.url;
			headers = new Headers(input.headers);
			if (input.body) {
				try {
					bodyText = await input.clone().text();
				} catch {}
			}
			if (init?.headers)
				new Headers(init.headers as HeadersInit).forEach((v, k) => {
					headers.set(k, v);
				});
			if (typeof init?.body === "string") bodyText = init.body;
		} else {
			url = typeof input === "string" ? input : input.toString();
			headers = new Headers((init?.headers as HeadersInit) ?? undefined);
			if (typeof init?.body === "string") bodyText = init.body;
		}
		if (isZenUrl(url)) {
			headers.set("Content-Type", "application/json");
			headers.set("Accept", "*/*");
			headers.set("Accept-Encoding", "gzip, deflate, br, zstd");
			headers.set("x-opencode-client", "cli");
			headers.set("x-opencode-project", getProjectId());
			headers.set("x-opencode-session", sessionId);
			headers.set("x-opencode-request", `msg_${identifier(false)}`);
			headers.set("User-Agent", USER_AGENT);
		}
		sanitizeHeaders(headers);
		return baseFetch(url, {
			...init,
			headers,
			...(bodyText !== undefined ? { body: bodyText } : {}),
		} as RequestInit);
	}) as unknown as typeof fetch;
}

const endpoints = new Map<string, EndpointApi>();
export function resolveEndpoint(modelId: string): EndpointApi {
	const api = endpoints.get(modelId);
	if (!api) throw new Error(`opencode model ${modelId} was never registered`);
	return api;
}
const ZEN_BASE_URLS = [BASE_URL, "https://opencode.ai/zen"];
export function isKnownZenBaseUrl(url: string): boolean {
	return ZEN_BASE_URLS.includes(url);
}
export function buildModelConfig(id: string): ProviderModelConfig {
	const model = OPENCODE_MODELS[id as keyof typeof OPENCODE_MODELS];
	if (
		model &&
		"baseUrl" in model &&
		typeof (model as { baseUrl?: unknown }).baseUrl === "string" &&
		!isKnownZenBaseUrl((model as { baseUrl: string }).baseUrl)
	)
		throw new Error(
			`opencode model ${id} baseUrl drifted; update BASE_URL routing`,
		);
	if (!model) {
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

function streamOpencodeZen(
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
): AssistantMessageEventStream {
	const api = resolveEndpoint(model.id);
	const wrappedOptions: SimpleStreamOptions = {
		...options,
		headers: { ...options?.headers, ...opencodeHeaders() },
		fetch: createOpencodeFetch(SESSION_ID) as unknown as typeof fetch,
	};
	const catalogBaseUrl =
		"baseUrl" in model && typeof model.baseUrl === "string"
			? model.baseUrl
			: BASE_URL;
	return streamSimple(
		{
			...model,
			api,
			baseUrl: isKnownZenBaseUrl(catalogBaseUrl) ? catalogBaseUrl : BASE_URL,
		} as Model<Api>,
		context,
		wrappedOptions,
	);
}

export default async function (pi: ExtensionAPI): Promise<void> {
	const modelIds = Object.keys(OPENCODE_MODELS).sort(compareStrings);
	if (modelIds.length === 0) return;
	projectId = await resolveProjectId(process.cwd());
	try {
		(
			pi as unknown as { unregisterProvider?: (id: string) => void }
		).unregisterProvider?.("opencode");
	} catch {}
	const models = modelIds.map((id) => buildModelConfig(id));
	for (const providerId of ["opencode", "opencode-patched"]) {
		pi.registerProvider(providerId, {
			baseUrl: BASE_URL,
			apiKey,
			api: "openai-completions",
			streamSimple:
				streamOpencodeZen as unknown as ProviderConfig["streamSimple"],
			models,
		});
	}
	pi.on("before_provider_headers", (event) => {
		try {
			const headers = event.headers as Record<string, string>;
			for (const key of Object.keys(headers)) {
				const lower = key.toLowerCase();
				if (lower.startsWith("x-stainless-")) delete headers[key];
				if (lower === "authorization" && headers[key]?.includes("public"))
					delete headers[key];
			}
			if (
				!Object.keys(headers).some(
					(k) => k.toLowerCase() === "x-opencode-session",
				)
			)
				Object.assign(headers, {
					...opencodeHeaders(),
					Accept: "*/*",
					"Accept-Encoding": "gzip, deflate, br, zstd",
				});
		} catch {}
	});
}
