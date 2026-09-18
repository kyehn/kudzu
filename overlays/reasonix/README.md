# reasonix

- 可靠 极致 优雅 先进 激进的实现，不故意复杂，最低兜底，不隐藏错误，代码重复率低
- `patches = [ ./fix.patch ];` 只有一个 patch 文件，无 postPatch，patch 使用 git 命令生成
- 对 `https://opencode.ai/zen/v1` 或对所有 providers 修改模拟成 opencode 发送的请求
  （根据修改的复杂度/可靠性判断某个步骤的修改是应该针对 opencode provider 还是对所有
  providers，避免重复代码，以低复杂高可靠为目标，其他 providers 如
  `https://opencode.ai/zen/go/v1` 不是 opencode provider，不需要过于针对性考虑），
  目的是使用 `https://opencode.ai/zen/v1` 提供的免费模型，
  参考 `https://github.com/anomalyco/opencode`，不进行不必要的修改。
  参考 overlays/reasonix/opencode/ 数据
  - 针对 openai/responses/anthropic 三种 kind 都要修改
  - 根据 opencode 源代码判断是否应该发送 api key 或者不发，
    api key 为 空 或 `public`，没有付费情况
  - `User-Agent` 为 `opencode/1.18.31 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`
  - `x-opencode-client` 为 `cli`
  - `x-opencode-project` `x-opencode-request` `x-opencode-session`
    必须和 opencode 一致的算法生成
  - 服务器可能检查 `tools` 等数据
  - 修改尽量在数据格式而不是随意修改 prompt 等实际内容，
    修改不能影响正常使用，不能导致模型调用不存在的工具
  - 必须和 opencode 基本一致的 tls 指纹，指纹和 bun 的类似
  - 对于 git rev 或其他类似数据，如果服务器无法判断真实性则应当使用 fake 数据
- 移除 max-steps 限制
- 移除预算限制
- 默认 ToolApprovalYolo 包括 ACP
- 彻底移除 `justification is required when sandbox_permissions is set` 限制
- 正确处理 `encrypted_content` 参数
- `context_window` 以 `config.toml` 为准
- overlays/reasonix/opencode/ 只保存 `npm i -g opencode-ai@latest` 发送到
  `https://opencode.ai/zen/v1` 的真实原始数据，不得添加 `note` 等信息，不得加工数据，
  保存足够的数据即可，不得故意重复，使用 JSON / JSONL 格式，
  对于需要自定义命名的属性根据 “OpenTelemetry 的字段命名习惯 + RFC 定义的原始 HTTP/TLS 字段”
  进行合理命名
