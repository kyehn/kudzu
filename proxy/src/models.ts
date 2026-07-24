import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

const CACHE_DIR = join("/tmp", "opencode-zen-proxy");
const MODELS_DEV_CACHE = join(CACHE_DIR, "models-dev.json");
const UPSTREAM_MODELS_CACHE = join(CACHE_DIR, "upstream-models.json");
const CACHE_TTL = 60 * 60 * 1000;

export interface ModelsDevModelInfo {
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
    input?: string[] | null;
    output?: string[] | null;
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

export interface UpstreamModelListResponse {
  data?: Array<{ id?: string }>;
}

export interface BootstrapState {
  modelIds: string[];
  modelsDevInfo: Record<string, ModelsDevModelInfo>;
}

async function ensureCacheDir(): Promise<void> {
  await mkdir(CACHE_DIR, { recursive: true });
}

async function readCache<T>(path: string): Promise<T | null> {
  try {
    const content = await readFile(path, "utf8");
    return JSON.parse(content) as T;
  } catch {
    return null;
  }
}

async function writeCache<T>(path: string, data: T): Promise<void> {
  await ensureCacheDir();
  await writeFile(path, JSON.stringify(data, null, 2));
}

export async function fetchModelsDevInfo(): Promise<Record<string, ModelsDevModelInfo>> {
  const cached = await readCache<{ data: Record<string, ModelsDevModelInfo>; timestamp: number }>(
    MODELS_DEV_CACHE
  );
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data;
  }

  const response = await fetch("https://models.dev/api.json");
  if (!response.ok) {
    throw new Error(`Failed to fetch models.dev: ${response.status}`);
  }
  const json = (await response.json()) as { opencode?: { models?: Record<string, ModelsDevModelInfo> } };
  const data = json.opencode?.models ?? {};
  await writeCache(MODELS_DEV_CACHE, { data, timestamp: Date.now() });
  return data;
}

export async function fetchUpstreamModelIds(baseUrl: string): Promise<string[]> {
  const cached = await readCache<{ data: string[]; timestamp: number }>(UPSTREAM_MODELS_CACHE);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data;
  }

  const response = await fetch(`${baseUrl}/v1/models`, {
    headers: {
      "User-Agent": "opencode/1.17.15/cli",
    },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch upstream models: ${response.status}`);
  }
  const json = (await response.json()) as UpstreamModelListResponse;
  const data = (json.data ?? []).map((entry) => entry.id?.trim()).filter((id): id is string => Boolean(id));
  await writeCache(UPSTREAM_MODELS_CACHE, { data, timestamp: Date.now() });
  return data;
}

export function isFreeModelId(id: string): boolean {
  return id.endsWith("-free");
}

export function isDeprecated(model: ModelsDevModelInfo | undefined): boolean {
  return model?.status === "deprecated";
}

export async function loadBootstrapState(): Promise<BootstrapState> {
  const [upstreamModelIds, modelsDevInfo] = await Promise.all([
    fetchUpstreamModelIds("https://opencode.ai/zen"),
    fetchModelsDevInfo(),
  ]);

  const upstreamSet = new Set(upstreamModelIds);
  const modelIds = [...upstreamSet]
    .filter(isFreeModelId)
    .filter((id) => !isDeprecated(modelsDevInfo[id]));

  return { modelIds, modelsDevInfo };
}

export function buildThinkingLevelMap(info?: ModelsDevModelInfo): Record<string, string | null> | undefined {
  if (!info?.reasoning) return undefined;

  const EFFORT_ORDER = ["minimal", "low", "medium", "high", "xhigh", "max"] as const;
  const PI_THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"] as const;

  const supportedEffort = new Set<string>();
  let hasToggle = false;

  for (const opt of info.reasoning_options ?? []) {
    if (opt.type === "toggle") hasToggle = true;
    if (opt.type === "effort" && opt.values) {
      for (const v of opt.values) supportedEffort.add(v);
    }
  }

  if (supportedEffort.size === 0 && hasToggle) {
    supportedEffort.add("high");
  }

  if (supportedEffort.size === 0 && info.reasoning) {
    supportedEffort.add("low");
    supportedEffort.add("medium");
    supportedEffort.add("high");
  }

  const findNearest = (level: string): string | null => {
    if (supportedEffort.has(level)) return level;
    const levelIdx = EFFORT_ORDER.indexOf(level as any);
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

  const map: Record<string, string | null> = {};
  for (const level of PI_THINKING_LEVELS) {
    if (level === "off") {
      map[level] = null;
    } else {
      const mapped = findNearest(level);
      map[level] = mapped;
    }
  }

  const hasNonOff = PI_THINKING_LEVELS.some((l) => l !== "off" && map[l] !== null);
  return hasNonOff ? map : undefined;
}

export interface ModelRecord {
  id: string;
  name: string;
  reasoning: boolean;
  input: ("text" | "image")[];
  cost: { input: number; output: number; cacheRead: number; cacheWrite: number };
  contextWindow: number;
  maxTokens: number;
  thinkingLevelMap?: Record<string, string | null>;
}

export function buildModelRecord(id: string, info?: ModelsDevModelInfo): ModelRecord {
  const thinkingLevelMap = buildThinkingLevelMap(info);
  const input: ("text" | "image")[] = [];
  if (info?.modalities?.input) {
    for (const mod of info.modalities.input) {
      if (mod === "text" || mod === "image") input.push(mod);
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