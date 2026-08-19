/**
 * NVIDIA NIM adapter for the DeepSeek Harness LLM seam.
 *
 * Registers the `nvidia-nim` provider route against NVIDIA's OpenAI-compatible
 * endpoint. The model catalog (chat models and their context/output limits) is
 * resolved at runtime from models.dev — the same source and the same chat-model
 * filter as `.github/reasonix-config`'s `_is_chat_model` — so no model data is
 * hard-coded. Request-body serialization and SSE decoding are reused from
 * `@deepseek-ai/dsh-llm-deepseek` (patched to export them).
 *
 * @module dsh-llm-nvidia-nim
 */

import type { Context } from "@deepseek-ai/cordis";
import type { CredentialRef } from "@deepseek-ai/dsh-credentials";
import {
  attributionHeaders,
  type GenerateOptions,
  isContextWindowExceededError,
  isQuotaExceededError,
  LlmAdapter,
  LlmError,
  type LlmModelInfo,
  type LlmProviderInfo,
  type LlmResolvedModelInfo,
  QUOTA_EXCEEDED_CODE,
  ReasoningEffortId,
  type StreamChunk,
} from "@deepseek-ai/dsh-llm";
import {
  parseSse,
  type RequestDefaults,
  serializeRequest,
  translate,
} from "@deepseek-ai/dsh-llm-deepseek";
import { idleWatchdog, timeoutOf } from "@deepseek-ai/dsh-timeout";
import z from "@deepseek-ai/schemastery";

export const name = "llm-nvidia-nim";
export const inject = ["llm"];

const PROVIDER = "nvidia-nim";
const PUBLIC_BASE_URL = "https://integrate.api.nvidia.com/v1";
const DEFAULT_API_KEY_ENV = "NVIDIA_API_KEY";
const DEFAULT_MODEL = "deepseek-v4-flash";
const DEFAULT_CONTEXT_WINDOW = 128_000;
const DEFAULT_MAX_TOKENS = 256_000;
const DEFAULT_STREAM_IDLE_TIMEOUT_MS = 300_000;
const STREAM_IDLE_TIMEOUT_CODE = "LLM_STREAM_IDLE_TIMEOUT";
const REQUEST_TIMEOUT_MS = 30_000;
/** Smallest context a chat model may advertise, mirroring reasonix-config. */
const MIN_CHAT_CONTEXT = 8_000;
/** Non-chat model id substrings, mirroring reasonix-config's `_is_chat_model`. */
const SKIP_PATTERNS = [
  "embed",
  "guard",
  "safety",
  "tts",
  "voice",
  "audio",
  "cosmos-predict",
  "cosmos-transfer",
  "flux",
  "image",
  "edit",
  "rerank",
  "esm",
  "detection",
  "synthetic",
  "validate",
  "whisper",
  "bevformer",
  "streampetr",
  "studiovoice",
  "sparsedrive",
  "usd",
  "riva",
  "magpie",
  "active-speaker",
  "gliner",
];

const MODELS_DEV_URL = "https://models.dev/api.json";
const MODELS_DEV_USER_AGENT = "opencode/prod/1.18.14/cli";

/** models.dev data subset used for the NVIDIA catalog. */
interface ModelsDevEntry {
  limit?: { context?: number; output?: number };
  status?: string;
}
interface ModelsDev {
  nvidia?: { models?: Record<string, ModelsDevEntry> };
}

let modelsDevCache: Promise<ModelsDev> | undefined;

function fetchModelsDev(): Promise<ModelsDev> {
  modelsDevCache ??= fetch(MODELS_DEV_URL, {
    headers: { "user-agent": MODELS_DEV_USER_AGENT },
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  }).then((response) => {
    if (!response.ok) {
      throw new LlmError(
        `models.dev request failed (HTTP ${response.status})`,
        "TRANSPORT",
      );
    }
    return response.json() as Promise<ModelsDev>;
  });
  return modelsDevCache;
}

function isChatModel(id: string, entry: ModelsDevEntry): boolean {
  const context = entry.limit?.context ?? 0;
  if (context < MIN_CHAT_CONTEXT) return false;
  const lowered = id.toLowerCase();
  return SKIP_PATTERNS.every((pattern) => !lowered.includes(pattern));
}

// -- Config -----------------------------------------------------------------

/** Plugin config. No model data lives here: the catalog comes from models.dev. */
export interface Config {
  /** Credential reference resolved per request; defaults to `NVIDIA_API_KEY`. */
  apiKeyEnv?: string;
  /** Endpoint base, defaults to the public NVIDIA NIM endpoint. */
  baseURL?: string;
  /** Default model for agents that do not pin one. */
  defaultModel?: string;
  /** Combined context capacity when the model has no exact metadata. */
  defaultContextWindow?: number;
  /** Default per-request output cap. */
  maxTokens?: number;
  /** Deployment thinking policy. */
  thinking?: "enabled" | "disabled";
  /** Default reasoning effort. */
  reasoningEffort?: "off" | "low" | "high" | "max";
  /** Maximum provider idle time while one stream read is outstanding. */
  streamIdleTimeoutMs?: number;
}

export const Config: z<Config> = z.object({
  apiKeyEnv: z.string().role("credential-ref").default(DEFAULT_API_KEY_ENV),
  baseURL: z.string().default(PUBLIC_BASE_URL),
  defaultModel: z.string().default(DEFAULT_MODEL),
  defaultContextWindow: z
    .number()
    .step(1)
    .min(1)
    .default(DEFAULT_CONTEXT_WINDOW),
  maxTokens: z.number().step(1).min(1).default(DEFAULT_MAX_TOKENS),
  thinking: z.union(["enabled", "disabled"]),
  reasoningEffort: z.union(["off", "low", "high", "max"]),
  streamIdleTimeoutMs: z
    .number()
    .min(1)
    .default(DEFAULT_STREAM_IDLE_TIMEOUT_MS),
});

/** Resolved, validated connection facts for one operation. */
export interface ResolvedNvidiaOptions {
  apiKeyEnv: CredentialRef;
  baseURL: string;
  defaults: RequestDefaults;
  defaultModel: string;
  defaultContextWindow: number;
  maxTokens: number;
  streamIdleTimeoutMs: number;
}

export function resolveAdapterOptions(config: Config): ResolvedNvidiaOptions {
  return {
    apiKeyEnv: config.apiKeyEnv as CredentialRef,
    baseURL: config.baseURL ?? PUBLIC_BASE_URL,
    defaults: {
      thinking: config.thinking,
      reasoningEffort: config.reasoningEffort,
    },
    defaultModel: config.defaultModel ?? DEFAULT_MODEL,
    defaultContextWindow: config.defaultContextWindow ?? DEFAULT_CONTEXT_WINDOW,
    maxTokens: config.maxTokens ?? DEFAULT_MAX_TOKENS,
    streamIdleTimeoutMs:
      config.streamIdleTimeoutMs ?? DEFAULT_STREAM_IDLE_TIMEOUT_MS,
  };
}

// -- Adapter ----------------------------------------------------------------

const OFF = ReasoningEffortId("off");
const LOW = ReasoningEffortId("low");
const HIGH = ReasoningEffortId("high");
const MAX = ReasoningEffortId("max");
const EFFORTS = [
  { id: OFF, name: "Off" },
  { id: LOW, name: "Low" },
  { id: HIGH, name: "High" },
  { id: MAX, name: "Max" },
] as const;

const OFF_ONLY_EFFORTS = [{ id: OFF, name: "Off" }] as const;

function modelInfo(provider: string, model: string): LlmModelInfo {
  return { provider, id: model, name: model, inputModalities: ["text"] };
}

function httpErrorCode(status: number, message: string): string {
  if (status === 401 || status === 403) return "AUTH";
  const detail = [message, String(status)].join(" ");
  if (isQuotaExceededError(detail) || status === 429)
    return QUOTA_EXCEEDED_CODE;
  if (status === 400 && isContextWindowExceededError(detail))
    return "CONTEXT_WINDOW_EXCEEDED";
  if (status >= 500) return "SERVER";
  return `HTTP_${status}`;
}

/** One instance serves every model; only `stream` is required by the base class. */
export class NvidiaNimAdapter extends LlmAdapter {
  constructor(
    private readonly hooks: {
      options: () => ResolvedNvidiaOptions;
      resolveApiKey: (connection: ResolvedNvidiaOptions) => Promise<string>;
    },
  ) {
    super();
  }

  override providerInfo(provider: string): LlmProviderInfo {
    return { id: provider, name: "NVIDIA NIM" };
  }

  override async listModels(
    provider: string,
  ): Promise<readonly LlmModelInfo[]> {
    const dev = await fetchModelsDev();
    const models = dev.nvidia?.models ?? {};
    return Object.entries(models)
      .filter(
        ([id, entry]) =>
          entry.status !== "deprecated" && isChatModel(id, entry),
      )
      .map(([id]) => modelInfo(provider, id))
      .toSorted((left, right) => left.id.localeCompare(right.id));
  }

  override async resolveModel(
    provider: string,
    model: string,
  ): Promise<LlmResolvedModelInfo> {
    const connection = this.hooks.options();
    let contextWindow = connection.defaultContextWindow;
    let maxTokens = connection.maxTokens;
    try {
      const dev = await fetchModelsDev();
      const entry = dev.nvidia?.models?.[model];
      const context = entry?.limit?.context;
      const output = entry?.limit?.output;
      if (entry?.status !== "deprecated") {
        if (context !== undefined && context > 0) contextWindow = context;
        if (output !== undefined && output > 0) maxTokens = output;
      }
    } catch {
      // Metadata is advisory; capacity falls back to configured defaults.
    }
    return {
      ...modelInfo(provider, model),
      context: { contextWindow },
      defaultMaxTokens: maxTokens,
      reasoning: {
        efforts:
          connection.defaults.thinking === "disabled"
            ? OFF_ONLY_EFFORTS
            : EFFORTS,
        defaultEffort:
          connection.defaults.reasoningEffort === "off"
            ? OFF
            : connection.defaults.reasoningEffort === "low"
              ? LOW
              : connection.defaults.reasoningEffort === "max"
                ? MAX
                : HIGH,
      },
    };
  }

  override async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const connection = this.hooks.options();
    const apiKey = await this.hooks.resolveApiKey(connection);
    const consumer = new AbortController();
    const upstream =
      options.signal === undefined
        ? consumer.signal
        : AbortSignal.any([options.signal, consumer.signal]);
    using watchdog = idleWatchdog(
      upstream,
      connection.streamIdleTimeoutMs,
      STREAM_IDLE_TIMEOUT_CODE,
    );
    const payload = JSON.stringify(
      serializeRequest(options, connection.defaults),
    );
    let response: Response;
    try {
      response = await fetch(`${connection.baseURL}/chat/completions`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${apiKey}`,
          "content-type": "application/json",
          accept: "text/event-stream",
          ...attributionHeaders(),
        },
        body: payload,
        signal: upstream,
      });
    } catch (error) {
      if (upstream.aborted) throw error;
      throw new LlmError(
        `NVIDIA NIM request to ${connection.baseURL} failed`,
        "TRANSPORT",
        { cause: error },
      );
    }

    if (!response.ok) {
      let message = `NVIDIA NIM API error (HTTP ${response.status})`;
      try {
        const parsed = (await response.json()) as {
          error?: { message?: string };
        };
        const detail = parsed.error?.message;
        if (detail !== undefined && detail.length > 0) message = detail;
      } catch {
        // The HTTP status still identifies the failure.
      }
      throw new LlmError(message, httpErrorCode(response.status, message), {
        status: response.status,
      });
    }
    if (response.body === null) {
      throw new LlmError(
        "NVIDIA NIM returned no response body",
        "EMPTY_RESPONSE",
      );
    }

    const iterator = translate(parseSse(response.body, () => watchdog.pulse()))[
      Symbol.asyncIterator
    ]();
    let exhausted = false;
    try {
      while (true) {
        const result = await watchdog.next(iterator);
        if (result.done) {
          exhausted = true;
          return;
        }
        yield result.value;
      }
    } catch (error: unknown) {
      if (timeoutOf(upstream, STREAM_IDLE_TIMEOUT_CODE) !== undefined) {
        throw new LlmError(
          `NVIDIA NIM stream idle timeout after ${connection.streamIdleTimeoutMs}ms`,
          "TIMEOUT",
          { cause: error },
        );
      }
      if (options.signal?.aborted) {
        throw new LlmError("NVIDIA NIM request aborted by caller", "ABORTED", {
          cause: error,
        });
      }
      if (error instanceof LlmError) throw error;
      throw new LlmError(
        `NVIDIA NIM stream from ${connection.baseURL} failed`,
        "TRANSPORT",
        { cause: error },
      );
    } finally {
      consumer.abort("NVIDIA NIM stream consumer stopped");
      if (!exhausted && iterator.return !== undefined) {
        try {
          await iterator.return(undefined);
        } catch {
          // The consumer controller already owns termination.
        }
      }
    }
  }
}

// -- Plugin -----------------------------------------------------------------

export function apply(ctx: Context, config: Config): void {
  const options = (): ResolvedNvidiaOptions => resolveAdapterOptions(config);

  const resolveApiKey = async (
    connection: ResolvedNvidiaOptions,
  ): Promise<string> => {
    const ref = connection.apiKeyEnv;
    const credentials = ctx.get("credentials");
    if (credentials !== undefined) {
      const hit = await credentials.resolve(ref);
      if (hit !== undefined) return hit.value;
    }
    const ambient = process.env[ref];
    if (ambient !== undefined && ambient.length > 0) return ambient;
    throw new LlmError(
      `nvidia-nim: no API key for provider route "${PROVIDER}"; store ${ref} through the credentials` +
        ` service or export ${ref} in the launching environment`,
      "MISSING_CREDENTIAL",
    );
  };

  const adapter = new NvidiaNimAdapter({ options, resolveApiKey });
  ctx.llm.registerAdapter([PROVIDER], adapter);
  ctx.llm.registerConfigurableProviders([
    {
      provider: PROVIDER,
      displayName: "NVIDIA NIM",
      settingsNs: name,
      settingsPath: [],
    },
  ]);
}
