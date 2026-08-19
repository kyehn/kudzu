# dsh overlay

[`deepseek-harness`](https://github.com/deepseek-ai/deepseek-harness)（dsh）的
nix 打包，并移植 opencode 模拟（`dsh-llm-opencode-zen` 插件）与
[reasonix 配置模型](../dsh-config.nix)（配合 `.github/dsh-config` 生成器）。

## 结构

- `default.nix` — `buildNpmPackage` 打包 `@deepseek-ai/dsh@0.1.0-rc.7` +
  `dsh-llm` + `dsh-llm-deepseek` + 两个 `file:` 本地插件 + `deepseek-acp`；
  `buildPhase` 里 `patch-llm-deepseek.sh` 补导出复用 dsh 的请求序列化/SSE
  解析；`postInstall` 生成 `dsh` wrapper（home patch 引导、profiles 预热、
  插件 symlink、`--expose-internals`、TLS openssl 配置）与 `deepseek-acp`
  wrapper（DSH_HOME 约定 + TLS openssl 配置）。
- `opencode-zen/` — `llm-opencode-zen` 插件，逐字节移植 opencode 的
  id 生成、`x-opencode-*` headers 与 UA，请求体直接复用 dsh 的
  `serializeRequest`，不自行构建请求体。
- `nvidia-nim/` — `llm-nvidia-nim` 插件，models.dev 的 NVIDIA chat 模型过滤。
- `dsh-home/cordis.patch.yml` — 默认 home patch：激活两个插件、默认模型
  `deepseek-v4-flash-free`（`provider: opencode-zen`）、sandbox
  `danger-full-access`、approval `never`。运行时模型数据由
  `dsh-config` 动态维护，nix 内不硬编码。
- `openssl.cnf` — TLS 指纹尽力对齐配置。
- `deepseek-acp` — [`xintaofei/deepseek-acp`](https://github.com/xintaofei/deepseek-acp)
  0.5.0（npm 包）：面向编辑器的 ACP 适配器。与 dsh 同树安装，产物
  `$out/bin/deepseek-acp` 通过 stdio 说 ACP（newline JSON 帧）；会话日志与
  凭据遵循同一 `$DSH_HOME` 约定（`--setup` 写入 `.credentials.yaml`，
  sessions 在 `$DSH_HOME/sessions`）。供 Zed/codeg 等编辑器以子进程拉起。
  wrapper 默认路由到**零密钥的 zen 免费通道**
  （`DEEPSEEK_ACP_PROVIDER=opencode-zen` +
  `DEEPSEEK_ACP_MODEL=deepseek-v4-flash-free`，可用同名环境变量覆盖），
  因此不需要 DeepSeek 官方 API key；`patch-deepseek-acp.sh` 在 buildPhase
  把两个捆绑 LLM 适配器插件注入其 cordis app（`composeAgent` 装配循环），
  使 provider 路由可选 `opencode-zen` / `nvidia-nim`。

## TLS 指纹的诚实说明

目标（opencode）是 Bun 运行时 + BoringSSL：JA3/JA4 由 cipher 顺序、
TLS 扩展顺序、ALPN 等共同构成。dsh 无法运行在 Bun 上（`dsh` 依赖
`node:module.stripTypeScriptTypes`，Bun 未实现），因此只能运行在 Node
的 OpenSSL 之上，**逐字节复刻整条 TLS 指纹不可能**。我们做到的程度：

- **cipher 顺序（JA3 的 cipher 部分）**：`openssl.cnf` 把 TLS1.2 cipher
  字符串按 BoringSSL 的默认顺序（CHACHA20 优先）配置，TLS1.3
  `Ciphersuites` 也按 BoringSSL 顺序排列。OpenSSL 支持这一配置，
  JA3 的 cipher 列表能对齐。
- **TLS 扩展顺序**：OpenSSL 不提供配置扩展顺序的接口（由实现固定，
  且与 BoringSSL 不同，如 `supported_groups`、`ec_point_formats`、
  `signature_algorithms` 的相对顺序）。**无法通过 OpenSSL 配置对齐**，
  这一部分与目标指纹不同。
- **UA 与 `x-opencode-*` headers**：与 TLS 无关的 HTTP 层特征，已
  在插件中完全复刻（含 id 生成逻辑与 header 大小写）。

结论：HTTP 层特征（UA、headers、id 生成）逐字节一致；TLS ClientHello
的 cipher 列表对齐，但扩展顺序与 QUIC（若启用 HTTP/3）无法复刻。
如需完全一致的 TLS 指纹，需在 Bun/BoringSSL 运行时上运行 opencode
本体，或改写 dsh 使其可运行于 Bun。