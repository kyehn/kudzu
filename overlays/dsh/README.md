# dsh（DeepSeek Harness）nix 配置

- 本体 `default.nix`：`buildNpmPackage` + registry tarball（`@deepseek-ai/dsh@0.1.7-rc.2`），
  `del(.devDependencies)` + vendored `package-lock.json`，`dontNpmBuild`，
  `npmRebuildFlags = [ "node-pty" ]`，`autoPatchelfHook`（sharp/koffi/node-pty），
  `wrapProgram --prefix PATH {pnpm,ripgrep}`（`dsh plugin` 与搜索工具需要），
  `postInstall` 把 `dsh-terminal-bash` 内的 `"/bin/bash"` 换成 store bash（找不到即失败），
  `versionCheckHook`。参考 gaavin/nix-deepseek + y0usaf/dsh.nix。
  - Node 用官方 `22.23.2` 二进制（`nodejs-official.nix`），不用 nix 编译版：
    dsh 的 `node-addon-require-builtin` 做 V8 机器码探测，nix 编译的 Node
   （24 与 nix 版 22.23.3 均已验证在 host preparation 崩溃），官方二进制正常。
    `buildNpmPackage` 只需 `nodejs` 提供 PATH/`python`/`platforms`，官方包补齐三者。
- `dsh-config.nix`：nix 生成 `$DSH_HOME/cordis.patch.yml` 与 profile `package.json`，
  全部经 `formats.yaml` / `builtins.toJSON` 生成，无字符串拼接：
  - pi `pi-permission-system-config.json` → `sandbox-policy.mode = workspace-write`（等价默认）
    + `approval.policy = ask`。pi 的逐命令 bash 黑名单在 dsh 无对等物
    （sandbox 是 workspace 边界不是命令黑名单），不硬塞不存在的字段；
    `permission.presets` 沿用 `dsh-base` 自带三 preset，不重复声明。
  - pi `pi-agent-mcp.nix` 5 server → `dsh-mcp-client` 行（stdio/command+args+env 或
    streamable-http/url+headers；可执行路径全部 `lib.getExe`，无 secret 需要 `!!js` 惰值，
    纯字面 YAML）。
  - pi `pi-agent-settings.nix` → `agent-default-model {provider = opencode, model}`；
    pi 插件专属 env/packages 在 dsh 无对应物，packages 对应位置是 profile `bundles`。
  - profile bundles：`@deepseek-ai/dsh-base` + `dsh-acp-enhanced@0.9.1`（ACP，选型见下）
    + `billion-context-dsh@0.2.26`（上下文压缩插件）。
  - `sandbox-policy.workspaceRoot` 省略即上游默认 `process.cwd()`，不写 `!!js`。
- `providers-config.py`：模型列表生成（复 `maki/providers-config.py` 结构）：
  models.dev + 官方 `/models` 校验 + 免费/tool_call/text-output 过滤，
  输出 `llm-pi-ai.providers` patch（`yaml.safe_dump`，无拼接）。
  每 route 附静态 `headers`（`x-opencode-client: cli` / `x-opencode-project: global`，
  与 pi-opencode 同值的协议常量）。
- `wire-identity.py`：opencode `iC()` 算法的可执行移植（与 pi-opencode `identifier()`
  同构，输出形状已断言：`ses_`/`msg_` + 30 字符）。

## ACP 选型：grunmin/dsh-acp-enhanced@0.9.1

最新（2026-09-25）、唯一跟踪 dsh 0.1.7 线、真 `dsh.bundle` 插件（`dsh plugin add`
一行安装）、Zed 功能最全（流式/telemetry/diff/真终端/elicitation/presets/多 root/resume）。
`ClickPM/dsh-acp-interactive`（standalone ACP server，不经 dsh profile，
与本仓库的 nix 生成配置模型不合）和 `openma-ai`（需共享 `$DSH_HOME` 手工装配）落选。
`billion-context-dsh` 不是 ACP，是压缩插件，与 ACP 并存。

## 已知缺口（不隐藏）

1. `User-Agent` per-endpoint pin：`dsh-llm` 的 `requestHeaders()` 会用 harness
   attribution（`deepseek-harness/<ver> (+url)`）覆盖部署侧声明的 `User-Agent`
   （源码实证），静态透传无望，需请求级注入（dsh 无 pi 的 `before_provider_headers`
   对等 hook）。
2. `x-opencode-request` 每请求唯一 / `x-opencode-session` 每会话 CLI 形：
   静态值即硬编码，违反要求，故不声明；算法在 `wire-identity.py` 可执行备用，
   待上游 `dsh-llm-pi-ai` 开出请求级 headers 钩子后由薄 bundle 插件消费。
3. pi-opencode 的 transcript sanitize（`encrypted_content` / 空 tool-call-id 修补）：
   pi-ai 请求体层面，dsh 侧同一 pi-ai（0.87.1）承担，nix 配置层不仿写。
4. `dsh plugin add`（ACP/billion 进 profile `node_modules`）是用户态一步命令，
   见 workflow；nix 只备好 profile `package.json`（bundles 声明）。
