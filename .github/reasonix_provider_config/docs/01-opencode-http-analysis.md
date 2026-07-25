# OpenCode HTTP 请求完整特征分析

> **版本**: opencode 1.18.5  
> **运行时**: Bun 1.3.14  
> **底层**: `effect/unstable/http` → `FetchHttpClient` → Bun 原生 fetch  
> **分析方式**: 源码分析 (`packages/llm/src/`) + **实证捕获**（MITM TLS 代理 + LD_PRELOAD 连接重定向）

---

## 0. 核心发现

### 实际到达网络的请求 (Empirical Capture)

```
POST /zen/v1/chat/completions HTTP/1.1
Host: opencode.ai
Content-Type: application/json
Authorization: Bearer public
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Connection: keep-alive
User-Agent: opencode/1.18.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14
X-Opencode-Client: cli
X-Opencode-Project: global
X-Opencode-Request: msg_f9a93282a001nElnmgoa1d8Bw6
X-Opencode-Session: ses_0656cd9ddffe1ifUlYafaexWcz
Content-Length: 2465
```

### 关键揭示

| Header | 实证结果 | 来源 |
|---|---|---|
| `User-Agent` | `opencode/1.18.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14` | **AI SDK 层** (`@ai-sdk/provider-utils`) 自动添加，非 opencode 自身代码 |
| `Authorization` | `Bearer public` | OpenCode Zen 免费模型使用 `public` 作为 API key |
| `Accept` | `*/*` | Bun 原生 fetch 默认值 |
| `Accept-Encoding` | `gzip, deflate, br, zstd` | Bun 原生 fetch 默认值 |
| `X-Opencode-*` | 4 个自定义 header | opencode 的 session/request tracking |
| `Connection` | `keep-alive` | HTTP 长连接 |

> ⚠️ **重要**: 这些 header 中只有 `X-Opencode-*` 是 opencode 特有的。
> `User-Agent` 来自 AI SDK，不是 opencode 故意添加的指纹。

---

## 1. 请求结构总览

### 1.1 URL

```
POST https://opencode.ai/zen/v1/chat/completions
```

- 通过 DNS 解析到 `172.65.90.20-23` 范围内的 IP
- 使用标准 TLS 1.3 连接

### 1.2 Body Schema (从源码 + 实证验证)

```json
{
  "model": "big-pickle",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "hello"}
  ],
  "tools": [...],
  "tool_choice": "auto",
  "max_tokens": 32000,
  "temperature": 0.5,
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

---

## 2. 完整 Header 分析

### 2.1 Sources of Headers

| Header | 来源层 | 代码位置 | 能否通过 Reasonix 配置控制 |
|---|---|---|---|
| `Content-Type: application/json` | `jsonPost()` | `shared.ts:320-324` | ❌ Go 的 `openai.go` 硬编码 |
| `Authorization: Bearer <key>` | `Auth.bearer()` | `auth.ts:47` | ✅ `auth_header` + `api_key_env` |
| `Accept: */*` | Bun fetch 默认 | 运行时行为 | ❌ Go 硬编码 `text/event-stream` |
| `Accept-Encoding` | Bun fetch 默认 | 运行时行为 | ✅ Go 自动处理 |
| `Connection: keep-alive` | HTTP 协议自动 | — | ✅ Go 自动处理 |
| `User-Agent` | AI SDK 自动添加 | `@ai-sdk/provider-utils` | ❌ Go 自动添加 `Go-http-client/1.1` |
| `X-Opencode-*` | opencode 自定义 | session/request tracking | ✅ Reasonix 无等价物（不是问题） |

### 2.2 认证 (Auth) 机制

```
Credential (密钥来源) ───→ Auth (应用到 header)
```

| 方法 | 效果 | 用途 |
|---|---|---|
| `Auth.bearer(secret)` | `Authorization: Bearer <secret>` | OpenAI, OpenCode Zen, xAI |
| `Auth.header("x-api-key")(secret)` | `x-api-key: <secret>` | Anthropic |
| `Auth.header("api-key")(secret)` | `api-key: <secret>` | Azure |
| `Auth.header("x-goog-api-key")(secret)` | `x-goog-api-key: <secret>` | Google/Gemini |
| `Auth.none` | 不修改 header | OpenCode Zen (无 key) |
| `Auth.remove("authorization")` | 删除指定 header | Azure |
| `Auth.andThen(a, b)` | 串联两个 Auth | Azure (删除 + 添加) |
| `Auth.orElse(a, b)` | 回退链 | 多 env var 回退 |

### 2.3 OpenCode Zen 认证

```typescript
// packages/function/src/providers/opencode.ts
auth: AuthOptions.bearer(
  { apiKey: "public" },  // 硬编码 "public" 作为 key
  "OPENCODE_API_KEY"      // 也可以通过环境变量覆盖
)
```

- 默认使用 `Bearer public`
- 如果有 `OPENCODE_API_KEY` 环境变量，则使用该值
- 如果没有提供且没有 env var，**请求仍然发送**（`optional` mode）

---

## 3. Body Overlay 协议

`http.body` denylist（37 个不可覆盖的协议自有字段）：

```
content, contents, frequencyPenalty, frequency_penalty,
generationConfig, inferenceConfig, input, maxTokens, max_tokens,
messages, model, presencePenalty, presence_penalty,
responseFormat, response_format, seed, stop, stopSequences,
stop_sequences, stream, streamOptions, stream_options, system,
systemInstruction, system_instruction, temperature, thinking,
toolChoice, toolConfig, tool_choice, tool_config, tools, topK,
topP, top_k, top_p
```

**允许覆盖的字段示例**: `user`, `metadata`, `logit_bias`, `logprobs`, `top_logprobs`, `n`, 自定义字段

---

## 4. 各 Provider 的路由配置

| Provider | baseURL | path | 认证方式 |
|---|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `/chat/completions` | `Bearer <OPENAI_API_KEY>` |
| OpenCode Zen | `https://opencode.ai/zen/v1` | `/chat/completions` | `Bearer public` (或无 key) |
| DeepSeek | `https://api.deepseek.com/v1` | `/chat/completions` | `Bearer <DEEPSEEK_API_KEY>` |
| Anthropic | `https://api.anthropic.com` | `/v1/messages` | `x-api-key` + `anthropic-version: 2023-06-01` |
| Azure | 由调用者指定 | `/chat/completions` | 删除 `Authorization` → 添加 `api-key` |
| Gemini | `https://generativelanguage.googleapis.com` | `/v1beta/models/{model}:generateContent` | `x-goog-api-key` |
| AWS Bedrock | region-based | 动态 (包含模型 ID) | AWS SigV4 |

---

## 5. SSE 流式响应

```json
data: {"choices":[{"delta":{"content":"..."}}]}

data: [DONE]
```

### 响应事件结构

```json
{
  "choices": [{
    "delta": {
      "content": "...",
      "reasoning_content": "...",
      "tool_calls": [{
        "index": 0,
        "id": "call_...",
        "function": {"name": "tool_name", "arguments": "{}"}
      }]
    },
    "finish_reason": "stop"|"length"|"tool_calls"|null
  }],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150,
    "prompt_tokens_details": {"cached_tokens": 0},
    "completion_tokens_details": {"reasoning_tokens": 10}
  }
}
```

---

## 6. 重试与错误处理

| 参数 | 值 |
|---|---|
| 最大重试次数 | 2 |
| 基础延迟 | 500ms |
| 最大延迟 | 10s |
| 重试状态码 | 429, 503, 504, 529 |

Rate Limit headers:
```
x-ratelimit-limit-<scope>
x-ratelimit-remaining-<scope>
x-ratelimit-reset-<scope>
retry-after-ms
retry-after
```

Request ID 识别（优先级顺序）:
```
x-request-id > request-id > x-amzn-requestid >
x-amz-request-id > x-goog-request-id > cf-ray
```

---

## 7. OpenCode 与 Reasonix 的 HTTP 特征对比

| 特征 | OpenCode | Reasonix | 匹配度 |
|---|---|---|---|
| **User-Agent** | `opencode/1.18.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14` | `Go-http-client/1.1` | ❌ 不同 |
| **Accept** | `*/*` | `text/event-stream` | ❌ 不同 |
| **Content-Type** | `application/json` | `application/json` | ✅ 相同 |
| **Authorization** | `Bearer <key>` | 由 `auth_header` 控制 | ✅ 可配置 |
| **Stream** | 始终 `true` | 由配置控制 | ⚠️ 可配置 |
| **X-Opencode-*** | 4 个自定义 header | ❌ 无 | — (非必需) |
| **TLS** | TLS 1.3 | HTTPS | ✅ 相同 |
| **Keep-Alive** | ✅ | ✅ | ✅ 相同 |

> **结论**: OpenCode 和 Reasonix 的 HTTP 特征**不匹配**，主要差异在 `User-Agent` 和 `Accept` header。
> 这些差异由底层运行时（Bun vs Go）决定，无法通过 Reasonix 配置消除。
