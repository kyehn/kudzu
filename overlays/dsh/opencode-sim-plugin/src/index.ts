// OpenCode 模拟 + 模型配置装配插件 v2（TypeScript 源码）。
//
// 职责（运行时装配，nix 配置零 provider/model 数据硬编码，与 reasonix
// 配置同效果且同语义）：
//   1. 动态抓取 opencode Zen free 模型与 models.dev 元数据（UA 与 reasonix
//      fetcher.py 一致：opencode/prod/1.18.14/cli），缓存到 DSH_HOME；
//   2. 按 reasonix-config builder.py 的映射语义装配两个 llm-pi-ai provider：
//        - opencode-zen：zen free 模型（-free 或 big-pickle），models.dev
//          元数据（contextWindow/maxTokens/vision/reasoningEfforts），
//          baseURL=https://opencode.ai/zen/v1（抓包/基准裸域名），并声明
//          x-opencode-client/x-opencode-project trigger headers —— 注入层
//          （opencode-sim.mjs）检测到即装配完整 opencode 客户端特征；
//        - nvidia-nim：models.dev nvidia chat 模型（ctx≥8000 + 28 个 skip
//          模式），baseURL=https://integrate.api.nvidia.com/v1；
//   3. 默认模型 = opencode-zen 第一个 free 模型；OPENCODE_API_KEY=public
//      兜底（等价 reasonix _ensure_opencode_public_key 的保证）。
//
// 构建：nix 构建期 esbuild 编译为 ESM 产物注入 DSH_HOME/plugins（见
// overlays/dsh-config.nix），运行环境为 dsh（Node 24，有全局 fetch）。
//
// 与基准抓包的差异如实记录：输入价格（models.dev cost）在 llm-pi-ai profile
// 无对应字段（pi-ai 不消费价格），与 reasonix 的 prices 同源但无法表达，
// 仅保留 model id/能力字段，不作伪价格。
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

export const name = "opencode-sim";
export const inject = ["settings"];

const ZEN_API = "https://opencode.ai/zen/v1/models";
const MODELS_DEV_API = "https://models.dev/api.json";
// 与 reasonix fetcher.py 一致：opencode/<channel>/<version>/<client>
const MODELS_DEV_USER_AGENT = "opencode/prod/1.18.14/cli";
const MIN_CHAT_CONTEXT = 8000;
const FETCH_TIMEOUT_MS = 60_000;

const ZEN_CACHE_FILE = "opencode_zen_models.json";
const MODELS_DEV_CACHE_FILE = "models_dev_api.json";

// 与 builder.py _is_chat_model 的 skip_patterns 逐项一致
const SKIP_PATTERNS = [
  "embed", "guard", "safety", "tts", "voice", "audio", "cosmos-predict",
  "cosmos-transfer", "flux", "image", "edit", "rerank", "esm", "detection",
  "synthetic", "validate", "whisper", "bevformer", "streampetr", "studiovoice",
  "sparsedrive", "usd", "riva", "magpie", "active-speaker", "gliner",
];

// 基准（读 protected overlays/reasonix/opencode 之外的运行时事实）：
// llm-pi-ai THINKING_LEVELS = off/minimal/low/medium/high/xhigh/max
const THINKING_LEVELS = new Set([
  "off", "minimal", "low", "medium", "high", "xhigh", "max",
]);
// 崩溃兜底默认模型名（唯一允许出现在插件源码里的模型名，非 provider 数据）
const FALLBACK_MODEL = "deepseek-v4-flash-free";

export function apply(ctx: AppContext): void {
  void assemble(ctx).catch((error: unknown) =>
    ctx.logger?.error("opencode-sim: %s", String(error)),
  );
}

interface AppContext {
  settings: SettingsService;
  get<T>(key: string): Promise<T | undefined>;
  logger?: { error(format: string, ...args: unknown[]): void };
}

interface SettingsService {
  registrations: { has(ns: string): boolean };
  update(ns: string, patch: unknown): Promise<unknown>;
}

// -- 抓取（缓存优先，与 fetch_zen_models/fetch_models_dev 同语义）--

function cacheDir(): string {
  return join(process.env.DSH_HOME ?? join(homedir(), ".dsh"), "models-cache");
}

async function fetchCachedJson(
  url: string,
  cacheFile: string,
  timeoutMs: number,
): Promise<Record<string, unknown>> {
  const cachePath = join(cacheDir(), cacheFile);
  if (existsSync(cachePath)) {
    return JSON.parse(readFileSync(cachePath, "utf8")) as Record<string, unknown>;
  }
  const res = await fetch(url, {
    headers: { "User-Agent": MODELS_DEV_USER_AGENT },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) {
    throw new Error(`fetch ${url}: HTTP ${res.status}`);
  }
  const data = (await res.json()) as Record<string, unknown>;
  const dir = dirname(cachePath);
  mkdirSync(dir, { recursive: true });
  const tmp = `${cachePath}.tmp`;
  writeFileSync(tmp, JSON.stringify(data, null, 2));
  renameSync(tmp, cachePath);
  return data;
}

// -- 映射（与 reasonix builder.py 逐条对应）--

interface ZenModel {
  id: string;
}

interface ModelsDevModel {
  status?: string;
  limit?: { context?: number; output?: number };
  reasoning?: boolean;
  reasoning_options?: unknown[];
  attachment?: boolean;
  modalities?: { input?: string[] };
}

interface ModelProfile {
  id: string;
  contextWindow?: number;
  maxTokens?: number;
  input?: string[];
  reasoningEfforts?: Record<string, string | null>;
  compat?: { thinkingFormat: string; supportsReasoningEffort: boolean };
}

/** _lookup_model：id 或 id.replace(".", "_") */
export function lookupModel(
  models: Record<string, ModelsDevModel>,
  modelId: string,
): [string, ModelsDevModel] | undefined {
  const direct = models[modelId];
  if (direct) return [modelId, direct];
  const normalised = modelId.replaceAll(".", "_");
  const alt = models[normalised];
  return alt ? [normalised, alt] : undefined;
}

export function isChatModel(mid: string, m: ModelsDevModel): boolean {
  const ctx = m.limit?.context ?? 0;
  if (ctx < MIN_CHAT_CONTEXT) return false;
  const lower = mid.toLowerCase();
  return SKIP_PATTERNS.every((pat) => !lower.includes(pat));
}

/** _build_override 的 llm-pi-ai profile 形态（能力字段映射）。 */
export function buildModelProfile(mid: string, m: ModelsDevModel): ModelProfile {
  const profile: ModelProfile = { id: mid };
  const ctx = m.limit?.context ?? 0;
  if (ctx) profile.contextWindow = ctx;
  const maxOut = m.limit?.output ?? 0;
  if (maxOut) profile.maxTokens = maxOut;
  if (m.reasoning && Array.isArray(m.reasoning_options)) {
    for (const opt of m.reasoning_options) {
      if (typeof opt === "object" && opt !== null && opt.type === "effort") {
        const values: unknown[] = Array.isArray(opt.values)
          ? opt.values.filter((v) => v !== null && v !== undefined)
          : [];
        if (values.length > 0) {
          // supported_efforts → reasoningEfforts：none→off(null)，其余层级
          // 原样作 wire 拼写（仅保留 llm-pi-ai THINKING_LEVELS 内的层级，
          // 未知层级会令 pi-ai 校验失败）
          const efforts: Record<string, string | null> = {};
          for (const v of values) {
            const level = String(v);
            if (level === "none") {
              efforts.off = null;
            } else if (THINKING_LEVELS.has(level)) {
              efforts[level] = level;
            }
          }
          // 至少一个非 off 层级，否则 pi-ai 拒绝空 effort 表
          if (Object.keys(efforts).some((l) => l !== "off")) {
            profile.reasoningEfforts = efforts;
            profile.compat = {
              thinkingFormat: "openai",
              supportsReasoningEffort: true,
            };
          }
        }
        break;
      }
    }
  }
  const input = m.modalities?.input ?? [];
  if (m.attachment || input.includes("image")) {
    profile.input = ["text", "image"];
  }
  return profile;
}

/** get_free_zen_model_ids：id 含 "-free" 或 == "big-pickle" */
export function getFreeZenModelIds(zenData: Record<string, unknown>): string[] {
  const data = Array.isArray(zenData.data) ? zenData.data : [];
  const ids = new Set<string>();
  for (const entry of data) {
    if (typeof entry !== "object" || entry === null) continue;
    const mid = (entry as ZenModel).id;
    if (typeof mid === "string" && (mid.includes("-free") || mid === "big-pickle")) {
      ids.add(mid);
    }
  }
  return [...ids].sort();
}

interface ProviderPatch {
  apiKeyEnv: string;
  api: string;
  baseURL: string;
  models: ModelProfile[];
  defaultContextWindow: number;
  defaultMaxTokens: number;
  defaultInput: string[];
  headers?: Record<string, string>;
}

// -- provider 构建（与 get_opencode_zen_free_providers / get_nvidia_providers
//    同语义；prices 在 pi-ai profile 无字段，如实不表达）--

export function buildOpenCodeZen(
  zenData: Record<string, unknown>,
  mdData: Record<string, unknown>,
): ProviderPatch {
  const oc = (mdData.opencode ?? {}) as Record<string, unknown>;
  const ocModels = (oc.models ?? {}) as Record<string, ModelsDevModel>;
  const models: ModelProfile[] = [];
  let maxContext = 0;

  for (const mid of getFreeZenModelIds(zenData)) {
    const lookup = lookupModel(ocModels, mid);
    if (!lookup) {
      models.push({ id: mid });
      continue;
    }
    const [, m] = lookup;
    if (m.status === "deprecated") continue;
    maxContext = Math.max(maxContext, m.limit?.context ?? 0);
    models.push(buildModelProfile(mid, m));
  }

  if (models.length === 0) {
    throw new Error("No free OpenCode Zen models found");
  }

  return {
    apiKeyEnv: "OPENCODE_API_KEY",
    api: "openai-completions",
    baseURL: "https://opencode.ai/zen/v1",
    models,
    defaultContextWindow: maxContext || 200000,
    defaultMaxTokens: 16_384,
    defaultInput: ["text"],
    // trigger headers：注入层据此装配完整 opencode 客户端特征；http 头最终
    // 由注入层生成（与 reasonix 同语义，此处仅声明触发）
    headers: { "x-opencode-client": "cli", "x-opencode-project": "global" },
  };
}

export function buildNvidia(mdData: Record<string, unknown>): ProviderPatch {
  const nv = (mdData.nvidia ?? {}) as Record<string, unknown>;
  const nvModels = (nv.models ?? {}) as Record<string, ModelsDevModel>;
  const models: ModelProfile[] = [];
  let maxContext = 0;

  for (const [mid, m] of Object.entries(nvModels).sort(([a], [b]) => a.localeCompare(b))) {
    if (m.status === "deprecated") continue;
    if (!isChatModel(mid, m)) continue;
    maxContext = Math.max(maxContext, m.limit?.context ?? 0);
    models.push(buildModelProfile(mid, m));
  }

  if (models.length === 0) {
    throw new Error("No NVIDIA NIM chat models found");
  }

  return {
    apiKeyEnv: "NVIDIA_API_KEY",
    api: "openai-completions",
    baseURL: "https://integrate.api.nvidia.com/v1",
    models,
    defaultContextWindow: maxContext || 128000,
    defaultMaxTokens: 16_384,
    defaultInput: ["text"],
  };
}

export function toSettingsProvider(patch: ProviderPatch): Record<string, unknown> {
  return {
    apiKeyEnv: patch.apiKeyEnv,
    api: patch.api,
    baseURL: patch.baseURL,
    ...(patch.headers ? { headers: patch.headers } : {}),
    models: patch.models,
    defaultContextWindow: patch.defaultContextWindow,
    defaultMaxTokens: patch.defaultMaxTokens,
    defaultInput: patch.defaultInput,
  };
}

// -- 装配 --

async function assemble(ctx: AppContext): Promise<void> {
  await waitForNamespaces(ctx.settings, ["llm-pi-ai", "agent-default-model"]);

  // OPENCODE_API_KEY=public 兜底：与 reasonix _ensure_opencode_public_key
  // 相同的保证（opencode Zen 默认 Bearer public 凭据）
  process.env.OPENCODE_API_KEY ??= "public";

  let opencodePatch: ProviderPatch | undefined;
  let nvidiaPatch: ProviderPatch | undefined;
  try {
    const [zenData, mdData] = await Promise.all([
      fetchCachedJson(ZEN_API, ZEN_CACHE_FILE, FETCH_TIMEOUT_MS),
      fetchCachedJson(MODELS_DEV_API, MODELS_DEV_CACHE_FILE, FETCH_TIMEOUT_MS),
    ]);
    opencodePatch = buildOpenCodeZen(zenData, mdData);
    nvidiaPatch = buildNvidia(mdData);
  } catch (error) {
    // 诚实降级：抓取失败且无缓存 → 记录错误并保留崩溃兜底默认模型，
    // 不静默假装成功（nix 内无任何 provider/model 数据）
    ctx.logger?.error("opencode-sim: model fetch failed (%s); falling back to default model", String(error));
  }

  const providers: Record<string, unknown> = {};
  if (opencodePatch) providers["opencode-zen"] = toSettingsProvider(opencodePatch);
  if (nvidiaPatch) providers["nvidia-nim"] = toSettingsProvider(nvidiaPatch);

  const defaultModel =
    opencodePatch?.models[0]?.id ?? FALLBACK_MODEL;

  if (Object.keys(providers).length > 0) {
    await ctx.settings.update("llm-pi-ai", { providers });
  }

  const defaultModelService = await ctx.get("agentDefaultModel");
  if (defaultModelService && typeof defaultModelService === "object") {
    const save = (defaultModelService as { saveSelection?: unknown }).saveSelection;
    if (typeof save === "function") {
      await (save as (sel: { provider: string; model: string }) => Promise<unknown>).call(
        defaultModelService,
        { provider: "opencode-zen", model: defaultModel },
      );
    }
  }
}

/**
 * 轮询等待 settings namespace 注册（llm-pi-ai 的 installSettingsSection 在
 * `llm` 服务激活后异步注册）。
 */
function waitForNamespaces(
  settings: SettingsService,
  namespaces: string[],
): Promise<void[]> {
  return Promise.all(
    namespaces.map(
      (ns) =>
        new Promise<void>((resolve) => {
          const poll = (): void => {
            if (settings.registrations.has(ns)) return resolve(void 0);
            setTimeout(poll, 25);
          };
          poll();
        }),
    ),
  );
}