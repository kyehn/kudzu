# 差距分析与变通方案

> 本文档列出 OpenCode 支持但 Reasonix 目前缺失的功能，
> 以及现有的变通方案（无需修改 Go 源码）。

---

## 差距 1: User-Agent Header

**问题**: Reasonix 使用 Go 的 `net/http` 库，自动添加 `Go-http-client/1.1` User-Agent。  
OpenCode 使用 `opencode/1.18.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`。

**影响**: 目标服务器可以通过 User-Agent 区分 Reasonix 和 OpenCode 访问。

**变通方案**: Reasonix `headers` 配置可以覆盖 User-Agent：

```toml
[provider.my-provider]
headers = { "User-Agent" = "opencode/1.18.5" }
```

但 Go 底层仍会发送 `Go-http-client/1.1` 作为 `User-Agent` 的一部分。  
要完全移除 Go 的默认 User-Agent，需要修改 `openai.go`：

```go
// 在 buildRequest() 中添加
req.Header.Set("User-Agent", "")
// 或使用自定义 http.Transport 的 DialTLSContext 修改
```

---

## 差距 2: Accept Header

**问题**: Reasonix 硬编码 `Accept: text/event-stream`。  
OpenCode 发送 `Accept: */*`（Bun fetch 默认）。

**影响**: 部分代理/网关可能根据 Accept header 做不同的处理。

**变通方案**: 在 `headers` 中设置覆盖：

```toml
headers = { "Accept" = "*/*" }
```

但 `openai.go:386` 在 `buildRequest()` 中强制设置：

```go
httpReq.Header.Set("Accept", "text/event-stream")
```

所以 `headers` 配置的 `Accept` 会被覆盖。**需要修改 Go 源码**。

修复方式 (`openai.go`):

```go
// 第 386 行附近，改为有条件设置
if req.Header.Get("Accept") == "" {
    httpReq.Header.Set("Accept", "text/event-stream")
}
```

---

## 差距 3: 自定义 Auth 组合

**问题**: OpenCode 支持 `Auth.andThen()`（串联）、`Auth.orElse()`（回退）。  
Reasonix 只支持单个 `api_key_env` + `auth_header`/`auth_header_name`。

**变通方案**: 对于简单场景（如多 env var 回退），没有变通方案。  
如果需要 Azure 风格（删除 Authorization + 添加 api-key），当前无法实现。

---

## 差距 4: Query 参数 (http.query)

**问题**: OpenCode 支持在请求 URL 上添加 query 参数。  
Reasonix 不支持通过配置添加 query 参数。

**变通方案**: 将 query 参数硬编码到 `base_url` 中：

```toml
# OpenCode: http.query = { "api-version" = "2024-10-21" }
# Reasonix:
base_url = "https://example.com/v1?api-version=2024-10-21"
```

---

## 差距 5: 动态 URL 路径

**问题**: OpenCode 支持 `Endpoint.path` 作为函数（如 Bedrock 的模型 ID 嵌入 URL）。  
Reasonix 只支持静态路径。

**变通方案**: 无。需要修改 Go 源码。

---

## 差距 6: AWS SigV4 认证

**问题**: OpenCode 支持 AWS Bedrock 的 Signature V4 认证。  
Reasonix 不支持。

**变通方案**: 在 `extra_body` 或 `headers` 中无法实现 SigV4。  
需要单独的 provider 实现。

---

## 差距 7: WebSocket 传输

**问题**: OpenCode 支持 OpenAI Responses 的 WebSocket 传输。  
Reasonix 只支持 HTTP。

**变通方案**: 无。

---

## 差距 8: 自定义 SSE/分块传输

**问题**: OpenCode 使用 `stream_options: { include_usage: true }` 和 SSE 分块解码。  
Reasonix 支持 SSE，但分块逻辑不同。

**变通方案**: Reasonix 支持 `stream: true` 的 SSE 响应解析。功能等效。

---

## 差距 9: X-Opencode-* 自定义 Header

**问题**: OpenCode 发送 `X-Opencode-Client`, `X-Opencode-Project`, `X-Opencode-Request`, `X-Opencode-Session`。

**变通方案**: 不是必需的。目标服务器通常不检查这些 header。

---

## 差距总结

| 差距 | 严重性 | 变通方案 | 需要 Go 修改 |
|---|---|---|---|
| User-Agent | 中 | 部分（headers 覆盖不彻底） | ✅ 是 |
| Accept header | 中 | ❌ (被 Go 覆盖) | ✅ 是 |
| 自定义 Auth 组合 | 低 | ❌ | ✅ 是 |
| Query 参数 | 低 | ✅ base_url 硬编码 | ❌ 否 |
| 动态路径 | 低 | ❌ | ✅ 是 |
| AWS SigV4 | 低 | ❌ | ✅ 是 |
| WebSocket | 低 | ❌ | ✅ 是 |
| SSE 分块 | 无 | ✅ 等效 | ❌ 否 |
| X-Opencode-* header | 无 | 不必要 | ❌ 否 |
