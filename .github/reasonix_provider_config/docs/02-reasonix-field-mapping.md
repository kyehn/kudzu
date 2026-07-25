# OpenCode → Reasonix ProviderEntry 字段映射

> 本文档列出 OpenCode LLMRequest 的每个选项，给出对应的 Reasonix `ProviderEntry` TOML 配置项，
> 以及映射是否完整。

---

## 符号说明

| 符号 | 含义 |
|---|---|
| ✅ **完整** | Reasonix 有等价 TOML 字段，直接映射 |
| ⚠️ **部分** | Reasonix 有功能，但需要变通或配置方式不同 |
| ❌ **缺失** | Reasonix 没有等价功能，需要修改 Go 源码 |

---

## LLMRequest 顶层字段

| OpenCode 字段 | Wire 位置 | Reasonix `ProviderEntry` 字段 | 状态 |
|---|---|---|---|
| `model` | body.model | `model` | ✅ 直接 |
| `system` | body.messages[role=system] | `system_prompt` (extra_body) | ✅ |
| `messages` | body.messages | — (由 reasonix 构建) | ✅ |
| `tools` | body.tools | — (由 reasonix 构建) | ✅ |
| `toolChoice` | body.tool_choice | — | ✅ |
| `generation` | body.{maxTokens,temperature,...} | — | ✅ |
| `providerOptions` | body.{reasoning_effort,...} | `reasoning_protocol`, `effort`, `thinking` | ✅ |
| `http` | headers/body/query | `headers`, `extra_body` | ⚠️ |
| `responseFormat` | body.response_format | — | ✅ |
| `cache` | body.stream_options.include_usage | — | ✅ |
| `metadata` | body.metadata | — | ✅ |

---

## HttpOptions

| OpenCode 字段 | 类型 | Reasonix 字段 | 状态 |
|---|---|---|---|
| `http.body` | `JsonSchema` | `extra_body` | ✅ |
| `http.headers` | `Record<string, string>` | `headers` | ✅ |
| `http.query` | `Record<string, string>` | ❌ 无 | ⚠️ 可通过 base_url 硬编码 |

### 已屏蔽的 Header

通过 `http.headers` **不能**覆盖以下 header（opencode 传输层阻止）：

```
accept, authorization, content-type, host, user-agent
```

Reasonix 的 `headers` 没有此限制——可以用 `headers` 覆盖任何 header，
包括 `User-Agent` 和 `Accept`。但需要修改 Go 源码才能真正移除 `Go-http-client/1.1`。

---

## GenerationOptions

| OpenCode 字段 | Wire 字段 | Reasonix 字段 | 状态 |
|---|---|---|---|
| `generation.maxTokens` | body.max_tokens | `max_output` | ✅ |
| `generation.temperature` | body.temperature | `temperature` (extra_body) | ✅ |
| `generation.topP` | body.top_p | `top_p` (extra_body) | ✅ |
| `generation.topK` | body.top_k | `top_k` (extra_body) | ✅ |
| `generation.frequencyPenalty` | body.frequency_penalty | `frequency_penalty` (extra_body) | ✅ |
| `generation.presencePenalty` | body.presence_penalty | `presence_penalty` (extra_body) | ✅ |
| `generation.seed` | body.seed | `seed` (extra_body) | ✅ |
| `generation.stop` | body.stop | `stop` (extra_body) | ✅ |

---

## OpenAI ProviderOptions

| OpenCode 字段 | Wire 字段 | Reasonix 字段 | 状态 |
|---|---|---|---|
| `providerOptions.openai.store` | body.store | ❌ | ⚠️ 可通过 extra_body |
| `providerOptions.openai.reasoningEffort` | body.reasoning_effort | `effort` | ✅ |
| `providerOptions.openai.reasoningSummary` | header/prompt | ❌ | ❌ |
| `providerOptions.openai.include` | body.include | ❌ | ❌ |
| `providerOptions.openai.textVerbosity` | header/prompt | ❌ | ❌ |
| `providerOptions.openai.serviceTier` | body.service_tier | ❌ | ⚠️ 可通过 extra_body |

---

## Auth 配置

| OpenCode 方式 | 对应的 Reasonix ProviderEntry 字段 |
|---|---|
| `Auth.bearer(secret)` | `auth_header = "authorization"` + `api_key_env = "ENV_VAR"` |
| `Auth.header("x-api-key")(secret)` | `auth_header_name = "x-api-key"` + `api_key_env = "ENV_VAR"` |
| `Auth.none` | `api_key_env = ""` |
| `Auth.remove("authorization")` | 不支持 |
| `Auth.andThen(a, b)` | 不支持 |
| `Auth.orElse(a, b)` | 不支持（仅单个 env var） |

---

## ProviderEntry 完整字段清单

Reasonix `ProviderEntry` 支持的 TOML 字段（来自 `config.go:1139-1155`）：

| 字段 | 类型 | 用途 | 对应 OpenCode 概念 |
|---|---|---|---|
| `name` | string | 显示名 | provider name |
| `kind` | string | provider 类型（openai） | — |
| `base_url` | string | API 基础 URL | endpoint.baseURL |
| `chat_url` | string | 聊天 URL（覆盖 base_url） | — |
| `model` | string | 默认模型 | model |
| `api_key_env` | string | API key 环境变量 | Auth |
| `auth_header` | string | Auth header 名称 | Auth 的 header 名 |
| `auth_header_name` | string | 自定义 Auth header 名 | Auth.header() |
| `auth_key_tmpl` | string | Auth key 模板 | — |
| `headers` | dict | 额外 HTTP header | http.headers |
| `extra_body` | dict | 额外请求 body 字段 | http.body |
| `context_window` | int | 上下文窗口 | — |
| `max_output` | int | 最大输出 token | generation.maxTokens |
| `vision` | bool | 支持图片输入 | providerOptions / 模型能力 |
| `vision_detail` | string | 图片详细程度 | — |
| `thinking` | string | thinking 模式 | — |
| `effort` | string | reasoning 努力级别 | providerOptions.reasoningEffort |
| `reasoning_protocol` | string | 推理协议 | — |
| `supported_efforts` | list | 支持的 effort 级别 | — |
| `default_effort` | string | 默认 effort | — |
| `store` | bool | 是否存储请求 | providerOptions.store |
| `price` | dict | 价格 | — |
| `prices` | dict | 多模型价格 | — |
| `model_overrides` | dict | 模型级覆盖 | — |
| `no_proxy` | bool | 跳过代理 | — |

---

## 不支持的 OpenCode 功能（需要 Go 源码修改）

| 功能 | OpenCode 位置 | Reasonix 状态 |
|---|---|---|
| 自定义 User-Agent | AI SDK 自动设置 | Go 强制添加 `Go-http-client/1.1` |
| Accept: */* | 原生 fetch 默认 | Go 强制 `Accept: text/event-stream` |
| 自定义 Auth 组合（andThen/orElse） | auth.ts | **不支持** |
| Query 参数（http.query） | endpoint.ts | **不支持**（需 base_url 硬编码） |
| AWS SigV4 | bedrock-auth.ts | **不支持** |
| WebSocket | openai-responses.ts | **不支持** |
| 动态路径（{model} in URL） | endpoint.ts | **不支持** |
| SSE 分块传输 | openai-chat.ts | ✅ 支持 |
