// 模型配置插件 v2 单测：映射语义与 reasonix-config builder.py 基准对照。
// 运行：node --experimental-strip-types --test opencode-sim-plugin.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildModelProfile,
  buildNvidia,
  buildOpenCodeZen,
  getFreeZenModelIds,
  isChatModel,
  lookupModel,
  toSettingsProvider,
} from "./src/index.ts";

// 与 reasonix-config /tests/test_builder.py 的基准样例同构的 mocks
const ZEN_SAMPLE = {
  data: [{ id: "deepseek-v4-flash-free" }, { id: "deepseek-v4-pro" }, { id: "big-pickle" }],
};

const MD_SAMPLE = {
  opencode: {
    models: {
      "deepseek-v4-flash-free": {
        status: "active",
        limit: { context: 1000000, output: 65536 },
        reasoning: true,
        reasoning_options: [{ type: "effort", values: ["none", "low", "high"] }],
        modalities: { input: ["text", "image"] },
        attachment: true,
        cost: { input: 0, output: 0 },
      },
      "big-pickle": { status: "deprecated", limit: { context: 1000000, output: 32768 } },
      "deepseek-v4-pro": { status: "active", limit: { context: 200000, output: 16384 } },
    },
  },
  nvidia: {
    models: {
      "meta/llama-3.3-70b-instruct": {
        status: "active",
        limit: { context: 131072, output: 8192 },
        reasoning: true,
        reasoning_options: [{ type: "effort", values: [null, "high"] }],
      },
      "nvidia/embedding-ada-002": {
        status: "active",
        limit: { context: 100000, output: 1000 },
      },
      "meta/llama-3.1-8b-instruct": {
        status: "active",
        limit: { context: 4096, output: 4096 },
      },
      "nvidia/stylegan2-image": {
        status: "active",
        limit: { context: 100000, output: 1024 },
      },
    },
  },
};

const ZEN = ZEN_SAMPLE;
const MD = MD_SAMPLE;

test("getFreeZenModelIds：-free 与 big-pickle，排序", () => {
  assert.deepEqual(getFreeZenModelIds(ZEN), ["big-pickle", "deepseek-v4-flash-free"]);
});

test("lookupModel：原 id 与 . → _ 归一化", () => {
  assert.equal(lookupModel(MD.opencode.models, "deepseek-v4-flash-free")?.[0], "deepseek-v4-flash-free");
  assert.equal(lookupModel(MD.opencode.models, "deepseek.v4.flash_free")?.[0], undefined);
  const alt = lookupModel({ "meta/llama-3.3-70b-instruct": MD.nvidia.models["meta/llama-3.3-70b-instruct"] }, "meta/llama-3.3-70b-instruct");
  assert.equal(alt?.[0], "meta/llama-3.3-70b-instruct");
});

test("isChatModel：ctx≥8000 + skip 模式过滤", () => {
  assert.equal(isChatModel("meta/llama-3.3-70b-instruct", MD.nvidia.models["meta/llama-3.3-70b-instruct"]), true);
  assert.equal(isChatModel("nvidia/embedding-ada-002", MD.nvidia.models["nvidia/embedding-ada-002"]), false);
  assert.equal(isChatModel("meta/llama-3.1-8b-instruct", MD.nvidia.models["meta/llama-3.1-8b-instruct"]), false);
  assert.equal(isChatModel("nvidia/stylegan2-image", MD.nvidia.models["nvidia/stylegan2-image"]), false);
});

test("buildModelProfile：contextWindow/maxTokens/reasoningEfforts/vision", () => {
  const p = buildModelProfile("deepseek-v4-flash-free", MD.opencode.models["deepseek-v4-flash-free"]);
  assert.equal(p.contextWindow, 1000000);
  assert.equal(p.maxTokens, 65536);
  assert.deepEqual(p.reasoningEfforts, { off: null, low: "low", high: "high" });
  assert.deepEqual(p.compat, { thinkingFormat: "openai", supportsReasoningEffort: true });
  assert.deepEqual(p.input, ["text", "image"]);
});

test("buildOpenCodeZen：跳过 deprecated，free 列表有序，defaultContextWindow", () => {
  const p = buildOpenCodeZen(ZEN, MD);
  assert.deepEqual(p.models.map((m) => m.id), ["deepseek-v4-flash-free"]);
  assert.equal(p.baseURL, "https://opencode.ai/zen/v1");
  assert.equal(p.apiKeyEnv, "OPENCODE_API_KEY");
  assert.equal(p.defaultContextWindow, 1000000);
  assert.deepEqual(p.headers, { "x-opencode-client": "cli", "x-opencode-project": "global" });
});

test("buildOpenCodeZen：未知模型直接入列（_lookup_model 失败不走 models.dev）", () => {
  const zen = { data: [{ id: "unknown-model-free" }] };
  const p = buildOpenCodeZen(zen, { opencode: { models: {} } });
  assert.deepEqual(p.models.map((m) => m.id), ["unknown-model-free"]);
});

test("buildNvidia：chat 模型过滤 + default 顺序", () => {
  const p = buildNvidia(MD);
  assert.deepEqual(p.models.map((m) => m.id), ["meta/llama-3.3-70b-instruct"]);
  assert.equal(p.baseURL, "https://integrate.api.nvidia.com/v1");
  assert.equal(p.apiKeyEnv, "NVIDIA_API_KEY");
  assert.equal(p.defaultContextWindow, 131072);
});

test("toSettingsProvider：llm-pi-ai settings 形状", () => {
  const p = buildOpenCodeZen(ZEN, MD);
  const s = toSettingsProvider(p);
  assert.equal(s.api, "openai-completions");
  assert.equal(s.baseURL, "https://opencode.ai/zen/v1");
  assert.deepEqual(s.headers, { "x-opencode-client": "cli", "x-opencode-project": "global" });
  assert.deepEqual(s.models, p.models);
  assert.equal(s.defaultInput[0], "text");
});