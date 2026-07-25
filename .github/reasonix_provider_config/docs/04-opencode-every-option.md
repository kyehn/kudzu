# OpenCode 全部配置选项与 Reasonix 映射

> 本文档列出 OpenCode `LLMRequest` 的每个配置选项及其到 Reasonix 的映射状态。

---

## 1. 基础请求字段

| 选项 | 类型 | OpenCode 用法 | Reasonix 映射 | 状态 |
|---|---|---|---|---|
| `model` | `ModelID` | `model: "gpt-4"` | `model = "gpt-4"` | ✅ |
| `system` | `string` | `system: "You are..."` | 通过 `messages` 构建 | ✅ |
| `messages` | `Message[]` | `messages: [{role, content}]` | 自动构建 | ✅ |
| `tools` | `ToolDefinition[]` | `tools: [{type:"function",...}]` | 自动构建 | ✅ |
| `toolChoice` | `"auto"\|"none"\|"required"\|{type,function}` | `toolChoice: "auto"` | 自动构建 | ✅ |
| `responseFormat` | `JsonSchema \| Text` | `responseFormat: {type:"json_object"}` | `response_format` in extra_body | ⚠️ |

## 2. Generation 选项

| 选项 | Wire 字段 | OpenCode | Reasonix | 状态 |
|---|---|---|---|---|
| `maxTokens` | `max_tokens` | `generation: {maxTokens: 4096}` | `max_output = 4096` | ✅ |
| `temperature` | `temperature` | `generation: {temperature: 0.7}` | `temperature` in extra_body | ✅ |
| `topP` | `top_p` | `generation: {topP: 0.9}` | `top_p` in extra_body | ✅ |
| `topK` | `top_k` | `generation: {topK: 40}` | `top_k` in extra_body | ✅ |
| `frequencyPenalty` | `frequency_penalty` | `generation: {frequencyPenalty: 0.5}` | `frequency_penalty` in extra_body | ✅ |
| `presencePenalty` | `presence_penalty` | `generation: {presencePenalty: 0.5}` | `presence_penalty` in extra_body | ✅ |
| `seed` | `seed` | `generation: {seed: 42}` | `seed` in extra_body | ✅ |
| `stop` | `stop` | `generation: {stop: ["\n"]}` | `stop` in extra_body | ✅ |

## 3. HTTP 选项

| 选项 | 类型 | OpenCode | Reasonix | 状态 |
|---|---|---|---|---|
| `http.body` | `JsonSchema` | `http: {body: {user: "abc"}}` | `extra_body = {user = "abc"}` | ✅ |
| `http.headers` | `Record<string,string>` | `http: {headers: {"X-Custom": "val"}}` | `headers = {"X-Custom" = "val"}` | ✅ |
| `http.query` | `Record<string,string>` | `http: {query: {"ver": "1"}}` | ❌ 不支持（用 base_url 硬编码） | ⚠️ |

## 4. OpenAI Options

| 选项 | Wire 字段 | OpenCode | Reasonix | 状态 |
|---|---|---|---|---|
| `store` | `store` | `providerOptions: {openai: {store: false}}` | `store = false` | ✅ |
| `reasoningEffort` | `reasoning_effort` | `providerOptions: {openai: {reasoningEffort: "high"}}` | `effort = "high"` | ✅ |
| `reasoningSummary` | — | `reasoningSummary: "auto"` | ❌ 无 | ❌ |
| `include` | `include` | `include: ["..." ]` | ❌ 无 | ❌ |
| `textVerbosity` | — | `textVerbosity: true` | ❌ 无 | ❌ |
| `serviceTier` | `service_tier` | `serviceTier: "default"` | ❌ 可通过 extra_body | ⚠️ |

## 5. Cache 策略

| 选项 | 类型 | OpenCode | Reasonix | 状态 |
|---|---|---|---|---|
| `cache` | `"auto"\|"none"\|{...}` | `cache: "auto"` | `stream_options` 自动处理 | ✅ |

## 6. Auth 配置

| 方式 | 代码 | Reasonix 配置 | 状态 |
|---|---|---|---|
| Bearer token | `Auth.bearer(secret)` | `auth_header = "authorization"` + `api_key_env` | ✅ |
| Custom header | `Auth.header("x-api-key")(secret)` | `auth_header_name = "x-api-key"` + `api_key_env` | ✅ |
| 无认证 | `Auth.none` | `api_key_env = ""` | ✅ |
| Header preset | `Auth.headers({"X-Key": "val"})` | `headers = {"X-Key" = "val"}` | ✅ |
| 删除 header | `Auth.remove("authorization")` | ❌ 无 | ❌ |
| 串联 | `Auth.andThen(a, b)` | ❌ 无 | ❌ |
| 回退 | `Auth.orElse(a, b)` | ❌ 无 | ❌ |

## 7. Provider 配置

| OpenCode 概念 | Reasonix ProviderEntry 字段 |
|---|---|
| `providerID` | `name` (TOML key) |
| `baseURL` | `base_url` |
| `apiKey` | `api_key_env` + `auth_header` |
| `headers` (request) | `headers` |
| `http.headers` (per-request) | `headers` (provider-level) |
| `http.body` (per-request) | `extra_body` (provider-level) |
| `models` | `model_overrides` |
| `disabled` | ❌ 无 |

## 8. 模型能力

| 能力 | OpenCode 检测方式 | Reasonix 字段 | 状态 |
|---|---|---|---|
| 视觉 | `modalities.input` 含 "image" | `vision = true/false` | ✅ |
| 推理/努力 | `reasoning_options[].values` | `supported_efforts = ["high","low"]` | ✅ |
| 结构化输出 | `structured_output` | ❌ 自动检测 | ⚠️ |
| 温度支持 | `temperature` | ❌ 自动检测 | ⚠️ |
