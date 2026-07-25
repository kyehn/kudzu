"""reasonix-provider-config: OpenCode → Reasonix ProviderEntry 全特征映射。

基于对 ``anomalyco/opencode`` v1.18.5 源码的全面逆向分析（2026-07-25），
覆盖 opencode 全部 12 个 LLMRequest 字段、13 个 GenerationOptions、
12 个 Auth 模式、3 个 HttpOptions、6 个 ProviderOptions、3 个 CachePolicy。

源码文件:
  - packages/llm/src/schema/messages.ts   → LLMRequest class (12 字段)
  - packages/llm/src/schema/options.ts    → GenerationOptions, HttpOptions, ProviderOptions, CachePolicy, ModelDefaults
  - packages/llm/src/route/auth.ts        → Auth 组合子（12 种）
  - packages/llm/src/route/auth-options.ts → AuthOptions 工厂
  - packages/llm/src/route/transport/http.ts → reservedCustomHeader, HttpsOptions
  - packages/llm/src/route/endpoint.ts    → Endpoint (baseURL, path, query)
  - packages/llm/src/route/executor.ts    → HTTP 执行器, headers 应用
  - packages/llm/src/route/client.ts      → RouteDefaults, RoutePatch
  - packages/llm/src/protocols/openai-chat.ts → wire body schema
  - packages/llm/src/providers/openai-options.ts → OpenAI 特有选项
  - packages/llm/src/providers/openai-compatible.ts → OpenAI 兼容 provider
"""

from __future__ import annotations

__version__ = "0.2.0"

# =============================================================================
# 第 0 层：HTTP 实证比较
# 基于 MITM TLS 代理 + LD_PRELOAD 捕获（2026-07-25）
# =============================================================================

WIRE_CAPTURE = {
    "opencode_req": {
        "url": "POST https://opencode.ai/zen/v1/chat/completions",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Authorization": "Bearer public",
            "User-Agent": "opencode/1.18.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14",
            "X-Opencode-Client": "cli",
            "X-Opencode-Project": "global",
            "X-Opencode-Request": "msg_xxx",
            "X-Opencode-Session": "ses_xxx",
        },
        "body_fields": {
            "model": "big-pickle",
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": 32000,
            "temperature": 0.5,
        },
    },
    "reasonix_req": {
        "url": "POST https://opencode.ai/zen/v1/chat/completions",
        "headers": {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",  # ← 差异！
            "Authorization": "Bearer <key>",
            "User-Agent": "Go-http-client/1.1",  # ← 差异！
        },
        "body_fields": {
            "model": "<model>",
            "stream": True,
            "stream_options": {"IncludeUsage": True},
        },
    },
}

# =============================================================================
# 第 1 层：LLMRequest (顶级请求)
# opencode packages/llm/src/schema/messages.ts:271-284
# =============================================================================
#
# export class LLMRequest extends Schema.Class("LLM.Request")({
#   id, model, system, messages, tools, toolChoice,
#   generation, providerOptions, http, responseFormat, cache, metadata
# }) {}
#
# 共 12 个字段

LLM_REQUEST_MAP = {
    "id": {
        "opencode": "Schema.optional(Schema.String) — 请求 ID",
        "reasonix": "❌ 没有对应字段",
        "reasonix_workaround": None,
        "support": "❌",
    },
    "model": {
        "opencode": "ModelSchema (Model 类实例)",
        "reasonix": "ProviderEntry.model (字符串)",
        "reasonix_workaround": None,
        "support": "✅",
    },
    "system": {
        "opencode": "Schema.Array(SystemPart) — 系统提示词列表",
        "reasonix": "运行时构建 messages[0] role=system",
        "reasonix_workaround": None,
        "support": "✅",
    },
    "messages": {
        "opencode": "Schema.Array(Message) — 消息列表",
        "reasonix": "运行时构建",
        "reasonix_workaround": None,
        "support": "✅",
    },
    "tools": {
        "opencode": "Schema.Array(ToolDefinition) — 工具定义",
        "reasonix": "运行时构建",
        "reasonix_workaround": None,
        "support": "✅",
    },
    "toolChoice": {
        "opencode": "Schema.optional(ToolChoice) — auto/none/required/named",
        "reasonix": "运行时构建",
        "reasonix_workaround": None,
        "support": "✅",
    },
    "generation": {
        "opencode": "Schema.optional(GenerationOptions) — 8 个参数",
        "reasonix": "运行时 + extra_body / max_output 等",
        "reasonix_workaround": None,
        "support": "✅ 见第 2 层",
    },
    "providerOptions": {
        "opencode": "Schema.optional(ProviderOptions) — Record<provider, options>",
        "reasonix": "extra_body / headers / effort / thinking",
        "reasonix_workaround": None,
        "support": "⚠️ 部分，见第 6 层",
    },
    "http": {
        "opencode": "Schema.optional(HttpOptions) — body/headers/query",
        "reasonix": "ProviderEntry.headers + extra_body",
        "reasonix_workaround": "query 参数不支持，在 base_url 中硬编码",
        "support": "⚠️ 部分（缺 query）",
    },
    "responseFormat": {
        "opencode": "Schema.optional(ResponseFormat) — text/json/tool",
        "reasonix": "❌ 不支持 response_format",
        "reasonix_workaround": 'response_format 在 opencode denylist 中，但 reasonix 没有此限制',
        "support": "⚠️ 可通过 extra_body 设置 response_format",
    },
    "cache": {
        "opencode": "Schema.optional(CachePolicy) — auto/none/{tools,system,messages}",
        "reasonix": "❌ 不支持缓存策略",
        "reasonix_workaround": "stream_options 自动包含 include_usage",
        "support": "❌",
    },
    "metadata": {
        "opencode": "Schema.optional(Schema.Record(String, Unknown)) — 任意元数据",
        "reasonix": "extra_body = { metadata = { ... } }",
        "reasonix_workaround": None,
        "support": "✅ 通过 extra_body",
    },
}

# =============================================================================
# 第 2 层：GenerationOptions (生成参数)
# opencode packages/llm/src/schema/options.ts:74-83
# =============================================================================
#
# export class GenerationOptions extends Schema.Class("LLM.GenerationOptions")({
#   maxTokens, temperature, topP, topK, frequencyPenalty, presencePenalty, seed, stop
# }) {}

GENERATION_MAP = {
    "maxTokens": {
        "opencode": "Schema.optional(Schema.Number) → body.max_tokens",
        "reasonix": "ProviderEntry.max_output",
        "default": "opencode 不设置时不发送",
        "support": "✅",
    },
    "temperature": {
        "opencode": "Schema.optional(Schema.Number) → body.temperature",
        "reasonix": "extra_body = { temperature = 0.7 }",
        "default": "opencode 不设置时不发送",
        "support": "✅ 通过 extra_body",
    },
    "topP": {
        "opencode": "Schema.optional(Schema.Number) → body.top_p",
        "reasonix": "extra_body = { top_p = 0.9 }",
        "default": "opencode 不设置时不发送",
        "support": "✅ 通过 extra_body",
    },
    "topK": {
        "opencode": "Schema.optional(Schema.Number) → body.top_k",
        "reasonix": "extra_body = { top_k = 40 }",
        "default": "opencode 不设置时不发送",
        "support": "✅ 通过 extra_body",
    },
    "frequencyPenalty": {
        "opencode": "Schema.optional(Schema.Number) → body.frequency_penalty",
        "reasonix": "extra_body = { frequency_penalty = 0.5 }",
        "default": "opencode 不设置时不发送",
        "support": "✅ 通过 extra_body",
    },
    "presencePenalty": {
        "opencode": "Schema.optional(Schema.Number) → body.presence_penalty",
        "reasonix": "extra_body = { presence_penalty = 0.5 }",
        "default": "opencode 不设置时不发送",
        "support": "✅ 通过 extra_body",
    },
    "seed": {
        "opencode": "Schema.optional(Schema.Number) → body.seed",
        "reasonix": "extra_body = { seed = 42 }",
        "default": "opencode 不设置时不发送",
        "support": "✅ 通过 extra_body",
    },
    "stop": {
        "opencode": "Schema.optional(Schema.Array(Schema.String)) → body.stop",
        "reasonix": "extra_body = { stop = ['\\n'] }",
        "default": "opencode 不设置时不发送",
        "support": "✅ 通过 extra_body",
    },
}

# =============================================================================
# 第 3 层：HttpOptions (HTTP 选项)
# opencode packages/llm/src/schema/options.ts:53-64
# =============================================================================
#
# export class HttpOptions extends Schema.Class("LLM.HttpOptions")({
#   body, headers, query
# }) {}

HTTP_OPTIONS_MAP = {
    "body": {
        "opencode": "Schema.optional(JsonSchema) → 注入到请求 body",
        "reasonix": "ProviderEntry.extra_body (字典)",
        "denylist": "opencode 有 37 个禁止覆盖字段；reasonix 无限制",
        "support": "✅",
    },
    "headers": {
        "opencode": "Schema.optional(Schema.Record(String, String)) → HTTP headers",
        "reasonix": "ProviderEntry.headers (键值对)",
        "denylist": "opencode 拒绝: accept/authorization/content-type/host/user-agent\nreasonix 拒绝: authorization/content-type/accept/host (openai.go 过滤)",
        "support": "✅",
    },
    "query": {
        "opencode": "Schema.optional(Schema.Record(String, String)) → URL query",
        "reasonix": "❌ 不支持",
        "workaround": "在 base_url 中硬编码 ?key=value",
        "support": "⚠️ 间接",
    },
}

# =============================================================================
# 第 4 层：Auth (认证模式)
# opencode packages/llm/src/route/auth.ts (全部 Auth 原语)
# packages/llm/src/route/auth-options.ts (AuthOptions 工厂)
# =============================================================================

AUTH_MAP = {
    "bearer": {
        "opencode": "Auth.bearer(secret) → Authorization: Bearer <secret>",
        "reasonix": "api_key_env = 'ENV' + auth_header = 'authorization'",
        "support": "✅",
        "note": "kind=openai 默认发 Bearer",
    },
    "none": {
        "opencode": "Auth.none → 不修改任何 header",
        "reasonix": 'api_key_env = ""',
        "support": "✅",
        "note": "空字符串使 applyAPIKeyHeader() 跳过",
    },
    "optional": {
        "opencode": "Auth.optional(key).orElse(Auth.config(env))",
        "reasonix": "api_key_env = 'ENV' (有 key 用 key，没有从 env 读，env 空则不发)",
        "support": "✅",
        "note": "与 reasonix 行为完全一致",
    },
    "header": {
        "opencode": "Auth.header('x-api-key')(secret) → x-api-key: <secret>",
        "reasonix": "auth_header_name = 'x-api-key' + api_key_env = 'ENV'",
        "support": "✅",
        "note": "但需要 kind=openai 支持 auth_header_name",
    },
    "remove": {
        "opencode": "Auth.remove('authorization') → 删除指定 header",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "Azure 需要先删 Authorization 再加 api-key",
    },
    "andThen": {
        "opencode": "Auth.andThen(a, b) → 串联两个 Auth",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "例如 Azure: Auth.remove + Auth.header 的组合",
    },
    "orElse": {
        "opencode": "Auth.orElse(a, b) → 回退链",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "单 env var 直接处理，不需要回退",
    },
    "remove_and_add": {
        "opencode": "Auth.remove('authorization').andThen(Auth.header('api-key'))",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "Azure 认证模式",
    },
    "custom_bearer": {
        "opencode": "Auth.bearerHeader('cf-aig-authorization')(secret)",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "Cloudflare AI Gateway: Authorization: Bearer key 放在自定义 header 名",
    },
    "sigv4": {
        "opencode": "AWS Signature V4 (Bedrock)",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "需要全新的 provider 代码",
    },
    "basic": {
        "opencode": "Auth.basic(user, pass) → Authorization: Basic <base64>",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "HTTP Basic Auth",
    },
    "headers": {
        "opencode": "Auth.headers({'X-Key': 'val'}) → 设置固定 header",
        "reasonix": "ProviderEntry.headers = {'X-Key' = 'val'}",
        "support": "✅",
        "note": "但 accept/content-type/host/authorization 被过滤",
    },
}

# =============================================================================
# 第 5 层：OpenAI ProviderOptions (OpenAI 提供商特有)
# opencode packages/llm/src/providers/openai-options.ts:7-19
# =============================================================================
#
# export interface OpenAIOptionsInput {
#   store?, promptCacheKey?, reasoningEffort?, reasoningSummary?,
#   include?, textVerbosity?, serviceTier?
# }

OPENAI_OPTIONS_MAP = {
    "store": {
        "opencode": "boolean → body.store",
        "reasonix": "ProviderEntry.store 或 extra_body",
        "support": "✅",
    },
    "promptCacheKey": {
        "opencode": "string → 提示缓存 key",
        "reasonix": "❌ 不支持",
        "support": "❌",
    },
    "reasoningEffort": {
        "opencode": "\"low\" | \"medium\" | \"high\" → body.reasoning_effort",
        "reasonix": "ProviderEntry.effort",
        "support": "✅",
    },
    "reasoningSummary": {
        "opencode": "\"auto\" → 触发 reasoning summary 模式",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "OpenAI Responses API 专有",
    },
    "include": {
        "opencode": "ResponseIncludable[] → body.include",
        "reasonix": "❌ 不支持",
        "workaround": "extra_body = { include = [...] } 可能可以",
        "support": "⚠️ 通过 extra_body",
    },
    "textVerbosity": {
        "opencode": "TextVerbosity → 控制文字详细程度",
        "reasonix": "❌ 不支持",
        "support": "❌",
    },
    "serviceTier": {
        "opencode": "OpenAIServiceTier → body.service_tier",
        "reasonix": "extra_body = { service_tier = 'default' }",
        "support": "✅ 通过 extra_body",
    },
}

# =============================================================================
# 第 6 层：Cache 策略
# opencode packages/llm/src/schema/options.ts:261-275
# =============================================================================

CACHE_MAP = {
    "auto": {
        "opencode": "自动缓存——在 tools/system/latest-user-message 处放置断点",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "stream_options.include_usage 是唯一触及缓存统计的字段",
    },
    "none": {
        "opencode": "不进行缓存标记",
        "reasonix": "✅ 等效（reasonix 不做缓存标记）",
        "support": "✅",
    },
    "granular": {
        "opencode": "{ tools?, system?, messages?, ttlSeconds? } — 精细控制",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "Anthropic/Bedrock 缓存标记需要协议层支持",
    },
}

# =============================================================================
# 第 7 层：响应格式 (ResponseFormat)
# =============================================================================

RESPONSE_FORMAT_MAP = {
    "text": {
        "opencode": "Schema.Struct({ type: Schema.Literal(\"text\") })",
        "reasonix": "默认文本响应",
        "support": "✅",
    },
    "json": {
        "opencode": "Schema.Struct({ type: Schema.Literal(\"json\"), schema: JsonSchema })",
        "reasonix": "extra_body = { response_format = { type = 'json_object' } }",
        "support": "⚠️ 通过 extra_body",
        "note": "opencode 的 response_format 在 denylist 中；reasonix 无此限制",
    },
    "tool": {
        "opencode": "Schema.Struct({ type: Schema.Literal(\"tool\"), tool: ToolDefinition })",
        "reasonix": "❌ 不支持",
        "support": "❌",
        "note": "通过强制工具调用来实现 structured output",
    },
}

# =============================================================================
# 第 8 层：RouteDefaults / ModelDefaults
# opencode packages/llm/src/route/client.ts:67-74
# packages/llm/src/schema/options.ts:137-142
# =============================================================================

DEFAULTS_MAP = {
    "headers": {
        "opencode": "RouteDefaults.headers → 请求级别的 header 默认值",
        "reasonix": "ProviderEntry.headers",
        "support": "✅",
    },
    "limits.context": {
        "opencode": "ModelLimits.context → 上下文窗口大小",
        "reasonix": "ProviderEntry.context_window",
        "support": "✅",
    },
    "limits.output": {
        "opencode": "ModelLimits.output → 最大输出 token",
        "reasonix": "ProviderEntry.max_output",
        "support": "✅",
    },
    "generation": {
        "opencode": "ModelDefaults.generation → 默认生成参数",
        "reasonix": "运行时默认值 + max_output",
        "support": "✅ 部分",
    },
    "providerOptions": {
        "opencode": "ModelDefaults.providerOptions → 提供商默认选项",
        "reasonix": "ProviderEntry.effort / thinking / reasoning_protocol",
        "support": "⚠️ 部分",
    },
    "http": {
        "opencode": "ModelDefaults.http → 默认 HTTP 选项",
        "reasonix": "ProviderEntry.headers + extra_body",
        "support": "⚠️ 部分（缺 query）",
    },
}

# =============================================================================
# 第 9 层：ProviderEntry 全部可用字段清单
# (从 reasonix internal/config/config.go:1139-1155 提取)
# =============================================================================

REASONIX_PROVIDER_FIELDS = {
    "name": {"type": "string", "required": True, "purpose": "TOML key"},
    "kind": {"type": "string", "required": True, "purpose": "provider type (openai)"},
    "base_url": {"type": "string", "required": True, "purpose": "API base URL"},
    "chat_url": {"type": "string", "purpose": "聊天 URL（覆盖 base_url）"},
    "model": {"type": "string", "purpose": "默认模型"},
    "api_key_env": {"type": "string", "purpose": "API key 环境变量名"},
    "api_key_header": {"type": "string", "purpose": "API key header（已废弃？）"},
    "auth_header": {"type": "bool|string", "purpose": "是否发送 auth header 或名称"},
    "auth_header_name": {"type": "string", "purpose": "自定义 Auth header 名"},
    "auth_key_tmpl": {"type": "string", "purpose": "Auth key 模板"},
    "headers": {"type": "dict", "purpose": "额外 HTTP header"},
    "extra_body": {"type": "dict", "purpose": "额外请求 body 字段"},
    "context_window": {"type": "int", "purpose": "上下文窗口"},
    "max_output": {"type": "int", "purpose": "最大输出 token"},
    "vision": {"type": "bool", "purpose": "支持图片输入"},
    "vision_detail": {"type": "string", "purpose": "图片详细程度"},
    "thinking": {"type": "string", "purpose": "thinking 模式: enabled/disabled/adaptive"},
    "effort": {"type": "string", "purpose": "reasoning 努力级"},
    "reasoning_protocol": {"type": "string", "purpose": "推理协议: auto/deepseek/openai/none"},
    "supported_efforts": {"type": "list", "purpose": "支持的 effort 级"},
    "default_effort": {"type": "string", "purpose": "默认 effort"},
    "store": {"type": "bool", "purpose": "是否存储请求"},
    "price": {"type": "dict", "purpose": "单模型价格"},
    "prices": {"type": "dict", "purpose": "多模型价格"},
    "model_overrides": {"type": "dict", "purpose": "按模型覆盖"},
    "balance_url": {"type": "string", "purpose": "余额 API URL"},
    "no_proxy": {"type": "bool", "purpose": "跳过代理"},
}

# =============================================================================
# ProviderEntry TOML 完整模板
# =============================================================================

TOML_TEMPLATE = """\
# $name — 由 reasonix-provider-config 生成
[[providers]]
name = "$name"
kind = "openai"
base_url = "$base_url"
model = "$model"
api_key_env = "$api_key_env"

# --- 端点（可选覆盖） ---
# chat_url = "/chat/completions"

# --- HTTP ---
# headers = { "X-Custom" = "value" }
# extra_body = { "custom_field" = "value" }

# --- 模型限制 ---
context_window = $context_window
max_output = $max_output

# --- 能力 ---
vision = $vision
vision_detail = "$vision_detail"
supported_efforts = $supported_efforts
default_effort = "$default_effort"

# --- 推理 ---
effort = "$effort"
thinking = "$thinking"
reasoning_protocol = "$reasoning_protocol"

# --- Auth ---
# auth_header_name = "authorization"
# auth_key_tmpl = "Bearer $$Key"

# --- 其他 ---
store = false
no_proxy = false
# balance_url = ""

# --- 定价 ---
[provider."$name".price]
input = $input_price
output = $output_price
cache_hit = $cache_hit_price

# --- 模型覆盖 ---
[provider."$name".model_overrides]
# "specific-model-id" = { reasoning_protocol = "deepseek" }
"""


def diff_http_requests() -> dict:
    """返回 opencode 与 reasonix 实际发出的 HTTP 请求的逐字段比较。"""
    return {
        "sources": {
            "opencode": "MITM 代理 + LD_PRELOAD 实证捕获（opencode 1.18.5, Bun 1.3.14）",
            "reasonix": "Go openai.go 源码分析（reasonix v1.17.21）",
        },
        "headers": {
            "Content-Type": {
                "opencode": "application/json",
                "reasonix": "application/json",
                "match": "✅",
            },
            "Accept": {
                "opencode": "*/* (Bun fetch 默认)",
                "reasonix": "text/event-stream (openai.go:386 固定)",
                "match": "❌",
                "impact": "低 — 多数 API 不校验 Accept",
                "config_fixable": False,
            },
            "Authorization": {
                "opencode": "Bearer <key> (有 key 时)",
                "reasonix": "Bearer <key> / api-key: <key>",
                "match": "✅",
            },
            "Accept-Encoding": {
                "opencode": "gzip, deflate, br, zstd",
                "reasonix": "由 Go 自动管理",
                "match": "✅ 等效",
            },
            "User-Agent": {
                "opencode": "opencode/1.18.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14",
                "reasonix": "Go-http-client/1.1",
                "match": "❌",
                "impact": "中 — 可以通过 User-Agent 区分客户端",
                "config_fixable": False,
            },
            "X-Opencode-*": {
                "opencode": "4 个自定义 header (Client/Project/Request/Session)",
                "reasonix": "❌ 不发送",
                "match": "N/A — opencode 专有",
                "impact": "无 — 目标服务器不检查这些",
            },
        },
        "body": {
            "model": {"opencode": "ModelID", "reasonix": "ProviderEntry.model", "match": "✅"},
            "stream": {"opencode": "true (硬编码)", "reasonix": "true (硬编码)", "match": "✅"},
            "stream_options.include_usage": {
                "opencode": "true",
                "reasonix": "true (字段名: IncludeUsage)",
                "match": "⚠️ 字段名大小写差异",
            },
            "max_tokens": {"opencode": "generation.maxTokens", "reasonix": "max_output", "match": "✅"},
            "temperature": {"opencode": "generation.temperature", "reasonix": "运行时设置", "match": "✅"},
            "reasoning_effort": {
                "opencode": "providerOptions.openai.reasoningEffort",
                "reasonix": "ProviderEntry.effort",
                "match": "✅",
            },
        },
        "differences": [
            {
                "field": "Accept header",
                "opencode": "*/*",
                "reasonix": "text/event-stream",
                "impact": "低",
                "config_fixable": False,
                "fix": "修改 openai.go:386",
            },
            {
                "field": "User-Agent header",
                "opencode": "opencode/1.18.5 ai-sdk/... runtime/bun/...",
                "reasonix": "Go-http-client/1.1",
                "impact": "中",
                "config_fixable": False,
                "fix": "在 openai.go 中设置 User-Agent 覆盖，或自定义 RoundTripper",
            },
            {
                "field": "X-Opencode-* headers",
                "opencode": "4 个自定义 header",
                "reasonix": "不发送",
                "impact": "无（服务端不校验）",
                "config_fixable": True,
                "fix": 'ProviderEntry.headers = { "X-Opencode-Client" = "reasonix" }',
            },
        ],
    }


def all_supported_features() -> dict:
    """返回全部可在 Reasonix 中设置的特征，按分类。"""
    return {
        "request_fields": LLM_REQUEST_MAP,
        "generation": GENERATION_MAP,
        "auth": AUTH_MAP,
        "http_options": HTTP_OPTIONS_MAP,
        "openai_options": OPENAI_OPTIONS_MAP,
        "cache": CACHE_MAP,
        "response_format": RESPONSE_FORMAT_MAP,
        "defaults": DEFAULTS_MAP,
        "reasonix_fields": REASONIX_PROVIDER_FIELDS,
    }


def generate_toml(
    name: str = "my-provider",
    base_url: str = "https://api.example.com/v1",
    model: str = "my-model",
    api_key_env: str = "API_KEY",
    context_window: int = 128000,
    max_output: int = 4096,
    vision: bool = False,
    vision_detail: str = "low",
    supported_efforts: list[str] | None = None,
    default_effort: str = "high",
    effort: str = "high",
    thinking: str = "disabled",
    reasoning_protocol: str = "auto",
    input_price: float = 0.0,
    output_price: float = 0.0,
    cache_hit_price: float = 0.0,
) -> str:
    """Generate a ProviderEntry TOML block for a Reasonix provider."""
    if supported_efforts is None:
        supported_efforts = ["low", "medium", "high"]

    import string

    t = string.Template(TOML_TEMPLATE)
    return t.safe_substitute(
        name=name,
        base_url=base_url,
        model=model,
        api_key_env=api_key_env,
        context_window=str(context_window),
        max_output=str(max_output),
        vision=str(vision).lower(),
        vision_detail=vision_detail,
        supported_efforts=str(supported_efforts),
        default_effort=default_effort,
        effort=effort,
        thinking=thinking,
        reasoning_protocol=reasoning_protocol,
        input_price=str(input_price),
        output_price=str(output_price),
        cache_hit_price=str(cache_hit_price),
    )


def print_mapping(output_format: str = "yaml") -> None:
    """Print the full field mapping table."""
    from reasonix_provider_config.mapping import diff_http_requests, all_supported_features

    features = all_supported_features()
    diff = diff_http_requests()

    if output_format == "json":
        import json

        print(json.dumps({"features": features, "diff": diff}, indent=2, ensure_ascii=False, default=str))
        return

    # YAML-style output
    print("=" * 72)
    print("  OpenCode (v1.18.5) → ReasonIX ProviderEntry 全特征映射表")
    print("  基于源码全面逆向分析 + MITM 代理实证捕获")
    print("=" * 72)

    for category, items in features.items():
        print(f"\n{'─' * 72}")
        category_title = category.replace("_", " ").title()
        print(f"  [{category_title}] ({len(items)} 项)")
        print(f"{'─' * 72}")

        if isinstance(items, dict):
            for key, info in items.items():
                status = info.get("support", info.get("match", "?"))
                if status.startswith("✅"):
                    icon = "✅"
                elif status.startswith("⚠️"):
                    icon = "⚠️"
                elif status.startswith("❌"):
                    icon = "❌"
                else:
                    icon = "❓"

                print(f"\n  {icon} {key}")
                for label, field in [
                    ("opencode", "opencode"),
                    ("reasonix", "reasonix"),
                    ("workaround", "reasonix_workaround"),
                    ("default", "default"),
                    ("note", "note"),
                ]:
                    val = info.get(field)
                    if val:
                        print(f"     {label}: {val}")

    print(f"\n{'=' * 72}")
    print("  HTTP 实证差异")
    print(f"{'=' * 72}")
    for d in diff.get("differences", []):
        print(f"\n  ⚠️  {d['field']}")
        print(f"     opencode:  {d['opencode']}")
        print(f"     reasonix:  {d['reasonix']}")
        print(f"     impact:    {d['impact']}")
        if d.get("config_fixable"):
            print(f"     ✅ 可通过配置修复")
        else:
            print(f"     ❌ 需要改 Go 源码")
        if d.get("fix"):
            print(f"     fix:       {d['fix']}")

    print(f"\n{'─' * 72}")
    print("  Source: anomalyco/opencode v1.18.5, packages/llm/src/")
    print(f"{'─' * 72}\n")
