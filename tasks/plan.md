# dsh（deepseek-harness）nix 打包 + reasonix-config 移植 + opencode 模拟 — 计划

## 目标

1. 为 https://github.com/deepseek-ai/deepseek-harness（`dsh`）创建 nix 打包（`overlays/dsh/`），被
   `flake.nix`/`overlays/default.nix` 已有的 `pkgs.dsh` 引用消费。
2. 移植 `.github/reasonix-config` 配置模型到新目录 `.github/dsh-config/`（Python，功能与原版相同：
   配置 opencode-zen + NVIDIA NIM；除输出格式外与原版相同）。
3. 移植 `overlays/reasonix-config.nix` → `overlays/dsh-config.nix`（权限不询问/不使用沙盒等；nix 配置
   内不硬编码模型/provider 数据，最多默认模型名）。
4. opencode 模拟：dsh 插件（首选），TLS 指纹尽力对齐 + 诚实说明，UA/headers/x-opencode-* id 按
   anomalyco/opencode 生成逻辑逐字节复刻；≤500 行/插件。
5. 不改动 `.github/reasonix-config`、`overlays/reasonix`；不查看 git 历史。

## 已确认决策（用户）

- **TLS 指纹**：Node 下用 `--openssl-config` 把 cipher suite 顺序对齐 BoringSSL（JA3 部分匹配），
  代码注释与文档明确说明 extension 顺序无法逐字节复刻（dsh 实测无法跑在 Bun 上）。
- **模型数据**：插件运行时动态获取（opencode.ai/zen/v1/models + models.dev/api.json），
  配置零模型数据（仅默认模型名）。
- **新目录**：`.github/dsh-config/`。
- **打包来源**：npm 包集（@deepseek-ai/dsh@0.1.0-rc.7，532 包已验证可运行）+ 提交 lockfile。

## 关键实现事实（来自源码研究）

- dsh 插件契约：`@deepseek-ai/cordis-plugin-loader` 从 node_modules 按包名加载；插件导出
  `name/inject/apply`，LLM 适配器 `extends LlmAdapter`（`providerInfo/providerRetryPolicy/listModels/
  resolveModel/stream`），经 `ctx.llm.registerAdapter(Routes, adapter)` 注册。
- opencode 特征（anomalyco/opencode dev，packages/opencode/src/session/llm/request.ts + id/id.ts）：
  - `User-Agent = opencode/1.18.18 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14`（捕捉值；
    runtime 由 experience AI SDK getRuntimeEnvironmentUserAgent 生成，模拟客户端固定该值）
  - `x-opencode-client: cli`、`x-opencode-project: global`、`Authorization: Bearer public`
  - `x-opencode-session = ses_` + id.ts `create('session','descending')`
  - `x-opencode-request = msg_` + id.ts `create('message','ascending')`
  - id.ts：`now = BigInt(Date.now())*0x1000+counter`（counter 同毫秒递增），descending = `~now`；
    6 字节 BE hex + 14 字符 base62（`randomBytes(26)`，`chars[i] = bytes[i] % 62`）
  - `Accept: */*`、`Accept-Encoding: gzip, deflate, br, zstd`
  - TLS：按键领域，整数捕捉 JA3/JA4 来自 Bun/BoringSSL，Node 不可复刻（见决策）。
- llm-deepseek npm 包 bundle（lib/index.js）顶层含 `serializeRequest/parseSse/translate`，
  patch 追加 `export {...}` 即可复用（不做请求体/响应解析重复实现）。
- dsh 配置 = cordis.patch.yml（`$DSH_HOME/cordis.patch.yml` 作用于所有 profile；profile 首次
  自动 init，bundles 来自 node_modules）。sandbox：`dsh-sandbox-policy` + `dsh-user-approval`
  + `dsh-permission-presets`（`danger-full-access` = 不限 + `never` = 不询问）。
- MCP 插件：`@deepseek-ai/dsh-mcp-client`（stdio/http 配置：serverName/command/args/env/url）。

## 任务与验证

1. `overlays/dsh/`：package.json（@deepseek-ai/dsh + 插件 file: 依赖）+ lockfile + default.nix
   （buildNpmPackage、dontNpmBuild、postPatch 注入 llm-deepseek 导出 patch、openssl.cnf、
   `NODE_OPTIONS=--openssl-config` 包装）+ 插件源码（opencode-zen / nvidia-nim）。
2. opencode-zen 插件 ≤500 行：UA/x-opencode headers/id 生成 + zen 动态模型（含 -free/big-pickle 筛选）。
3. nvidia-nim 插件 ≤500 行：models.dev 动态模型（chat 筛选：MIN_CHAT_CONTEXT=8000 + skip patterns）。
4. `overlays/dsh-config.nix`：生成 cordis.patch.yml（sandbox danger-full-access、approval never、
   agent-default-model=opencode-zen/deepseek-v4-flash-free、llm entries、mcp 客户端），零模型数据。
5. `.github/dsh-config/`：镜像 reasonix-config（fetcher/models/builder/__main__ + tests），输出
   dsh LLM 配置（provider 路由 + 可选模型快照），ruff+pytest。
6. 验证：`nix build .#dsh`、`.#dsh-config`；`dsh --version`；端到端 headless 请求 zen
   （真实 UA/header/TLS 抓包对比）；biome/ruff/nixfmt 全绿。
7. 文档：`.github/dsh-config/README.md` + adr（TLS 指纹诚实说明）。

## 风险

- zen 模型 API / models.dev 网络可达性（端到端测试需要网络）。
- npm registry 拉取慢（已实测一次 3 分钟；nix 构建用 cache/离线 lockfile）。
- Node 22.19+ engines：nixpkgs nodejs_24 满足。
## 实现状态（2025-08 完成）

- 全部任务完成并验证：`nix build .#dsh .#dsh-config` 双产物成功；最终形态
  （所有文件 git tracked，含 package-lock）端到端真实对话通过
  （默认 opencode-zen / deepseek-v4-flash-free）；`dsh-config` 真实网络
  抓取 71 模型 + doctor 通过，产物 home 引导 dsh 对话成功。
- lint/format 全绿：nixfmt-rs（.nix）、yamlfmt（cordis.patch.yml 含 !!js）、
  biome（TS 插件 + json，5 json No fixes）、tsc strict（构建内）、
  ruff check + format、pytest 21 passed。
- 文档：`.github/dsh-config/README.md`（移植说明）、`overlays/dsh/README.md`
  （打包结构与 TLS 指纹诚实说明）。
- 注意：`nix build .#formatter`/多产物构建会改写仓库内存量 json（biome 配置
  与基线不符，如 `.github/paseo-config.json`、`overlays/reasonix/opencode/*.json`），
  属存量问题，未纳入本次改动（已恢复）。
