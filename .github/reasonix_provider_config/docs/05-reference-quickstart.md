# 快速参考配置示例

> 可以直接复制使用的 Reasonix ProviderEntry TOML 配置。

---

## OpenCode Zen Free 模型

```toml
# OpenCode Zen 免费模型 — 无需 API key
# 目标: 模仿 OpenCode 对 Zen 端点的访问
[[providers]]
name = "opencode-zen-free"
kind = "openai"
base_url = "https://opencode.ai/zen/v1"
api_key_env = ""                                      # 无 API key
model = "big-pickle"
context_window = 48000
max_output = 32000
vision = false

# 推理/努力级别
supported_efforts = ["low", "medium", "high"]
default_effort = "medium"

# Headers 与 OpenCode 对齐
[provider."opencode-zen-free".headers]
# ❌ 注意: 以下设置被 Go 的 openai.go 覆盖:
# Accept = "*/*"           # 实际发送: text/event-stream
# User-Agent = "..."       # 实际发送: Go-http-client/1.1
# Authorization = "Bearer public"  # 因为 api_key_env="" 而不发送
```

> **实际捕获的 OpenCode Zen 请求 header:**
> ```
> Accept: */*
> Authorization: Bearer public
> User-Agent: opencode/1.18.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14
> ```
> **Reasonix 实际发送的 header:**
> ```
> Accept: text/event-stream
> Authorization: (none — api_key_env="")
> User-Agent: Go-http-client/1.1
> ```

---

## NVIDIA NIM

```toml
# NVIDIA NIM API — 需要 NVIDIA_API_KEY
# 源: api.nvidia.com
[[providers]]
name = "nvidia-nim-free"
kind = "openai"
base_url = "https://api.nvidia.com/v1"
api_key_env = "NVIDIA_API_KEY"                        # 从环境变量读取
auth_header = "authorization"                         # Authorization: Bearer <key>

model = "nvidia/nemotron-3-ultra-550b-a55b"
context_window = 128000
max_output = 32000
vision = false

supported_efforts = ["low", "medium", "high"]
default_effort = "high"

# 添加价格信息（示例）
[provider."nvidia-nim-free".prices]
[provider."nvidia-nim-free".prices."nvidia/nemotron-3-ultra-550b-a55b"]
input = 2.5e-7
output = 2.5e-7
cache_hit = 2.5e-8
```

---

## DeepSeek (OpenCode 兼容)

```toml
[[providers]]
name = "deepseek-v4-flash-free"
kind = "openai"
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"
model = "deepseek-chat"
context_window = 64000
max_output = 8000

# DeepSeek 的推理内容支持
thinking = "enabled"
effort = "medium"

# 多模型价格
[provider."deepseek-v4-flash-free".prices]
[provider."deepseek-v4-flash-free".prices."deepseek-chat"]
input = 4.0e-7
output = 4.0e-7
cache_hit = 7.0e-8
```

---

## 自定义 OpenAI 兼容 (带额外 header)

```toml
[[providers]]
name = "my-custom"
kind = "openai"
base_url = "https://my-api.example.com/v1"
api_key_env = "MY_API_KEY"
model = "my-model-1"
context_window = 32000
max_output = 4096

# 额外 header
[provider."my-custom".headers]
"X-Custom-Header" = "my-value"
"X-Project" = "my-project"

# 额外 body 字段
[provider."my-custom".extra_body]
user = "my-user-id"
metadata = { session = "abc123" }
```

---

## 测试配置是否工作

```bash
# 使用特定 provider 对话
reasonix run "Hello" --model my-custom/my-model-1

# 检查 provider 配置
reasonix doctor

# 同步最新 provider 列表
reasonix-provider-config
```
