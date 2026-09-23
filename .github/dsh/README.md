# dsh: DeepSeek Harness ACP provider for paseo (zen free models)

发行版：`deepseekharness-acp-interactive`（<https://github.com/ClickPM/dsh-acp-interactive>）

选型结论（对比 `xintaofei/deepseek-acp`、`openma-ai/deepseek-harness-acp`）：

- 自包含：单个可执行文件 + `config/cordis.yml`，不需要 DeepSeek Harness 源码 checkout，
  不需要 `dsh web` / profile 机器
- 配置驱动：直接读 `~/.dsh/settings.yaml` + `.credentials.yaml`，provider 路由、
  headers、模型目录都是声明式配置，正好承接 pi/maki 的 opencode 模拟
- 会话内可切换模型：`session/set_config_option`（`configId: model`，
  `value: provider:model`），paseo/编辑器侧可用
- 工程质量：MIT，多 OS CI，ACP registry 送审，版本化 release
- 本地已实证可用（见下）

## 文件

- `generate-settings.py`：动态生成 `~/.dsh/settings.yaml` — 以 zen 网关实时
  `/models`（带 opencode wire UA）∩ models.dev opencode 目录为准，只收
  free（cost 0）、**非 `deprecated`**、支持 tool call、text 输入、且
  provider 非 `@ai-sdk/openai`/`@ai-sdk/anthropic`（responses/anthropic 路
  dsh 走不了）的模型，context/output 限额取 models.dev；再对候逐个 POST
  探活，剔除上游已下线的 `Model is unavailable`（400）模型（403 FreeTier
  视为存活，仅是网关门禁）；空目录拒绝写入（`DSH_SETTINGS` 可覆盖输出路径）。
  当前产物 6 个模型：big-pickle、ling-3.0-flash-fin-free、
  mimo-v2.6-flash-free、nemotron-3-ultra-free、nemotron-3.5-lightning-free、
  space-bunny-free（与 models.dev 免费且未弃用的 8 个相比，少的正是两个
  responses 路 muse-spark；弃用的 mimo-v2.5-free、已死的
  deepseek-v4-flash-free 均被状态过滤剔除）
- `headers.patch` + `apply-headers-patch.sh`：允许 `settings.yaml` 的 `headers`
  覆盖 harness 归因头（默认 `User-Agent: deepseek-harness/...` 且不可覆盖，
  网关只认 `opencode/...`）。补丁把 `requestHeaders` 改为"部署头赢、归因补齐"，
  其他 provider（未配 UA 的）行为不变。插件机制做不到：归因是写死的合并顺序，
  不是可挂载服务；上游若接受 white-label identity 配置即可删除本补丁。
  **A/B 已证必要**：同一 dsh 1.3.2 会话，打补丁 → zen mimo PONG；
  逆向还原补丁 → `403 FreeTierError "OpenCode's free tier can only be used
  from within OpenCode"`（user-agent 退回 `deepseek-harness/...`）。补丁随
  npm 升级会被冲掉，升级后必须重跑 `apply-headers-patch.sh`
- 凭证（不进仓库）：`~/.dsh/.credentials.yaml` 须为 `version: 1`，`refs` 全字符串，
  `OPENCODE_PUBLIC: public`，`DEEPSEEK_API_KEY` 占位（dsh 只做存在性校验，
  zen 路由不使用它）

## 已验证矩阵（`dsh-acp-interactive` 1.3.2，直连，无代理）

- `zen:big-pickle` → `end_turn`，但该模型对"Reply with exactly: PONG"会
  退化成连发数百次 `PONG`（301 chunk），**不能**用作逐字回显断言的冒烟模型
- `zen:mimo-v2.6-flash-free` → `end_turn`，`agent_message_chunk` 拼合恰为
  `PONG`，稳定，作为 CI 冒烟模型
- `zen:deepseek-v4-flash-free` → 上游已下线（`Model is unavailable`，400），
  models.dev 同步标记 `deprecated`，状态过滤 + 探活双保险剔除
- `zen:mimo-v2.5-free` → 网关仍列出但 models.dev 已标 `deprecated`，
  状态过滤剔除（与 pi/omp/maki 各源一致；reasonix 不走状态过滤——它的
  列表由网关客户端画像门控收到只剩 `space-bunny-free`，见
  `.github/reasonix/config.toml` 注释）
- responses 路模型（如 muse-spark）不收录：dsh 只认 provider 级 `api`，
  模型级 `api` 被忽略，会走错 `/chat/completions` 路径
- 网关 `GET /models` 会列出已死/弃用 id，不能单独作为目录依据；
  目录 = 网关列表 ∩ models.dev（含状态） ∩ POST 探活

## 接入

```sh
npm install --global deepseekharness-acp-interactive@1.3.2
python3 .github/dsh/generate-settings.py
export OPENCODE_PUBLIC=public
./.github/dsh/apply-headers-patch.sh
```

- zen 路由的 `apiKeyEnv: OPENCODE_PUBLIC` 从**进程环境**取值（或凭据服务）；
  `.credentials.yaml` 的 `refs` 不参与该解析，不 export 会超时/鉴权失败。
  paseo 侧由 `paseo-config.json` 的 `providers.dsh.env` 注入，无需手工 export
- ACP 会话默认模型是 `deepseek-official`（走官方 key，非 zen）；zen 路由需
  `session/set_config_option`（`configId: model`，`value: zen:<id>`）切换，
  paseo 侧 `paseo run --provider dsh --model zen:<id>`

paseo 侧 provider（见 `.github/paseo-config.json`）：

```json
"dsh": { "extends": "acp", "label": "DSH", "command": ["dsh-acp-interactive"], "env": { "OPENCODE_PUBLIC": "public" } }
```
