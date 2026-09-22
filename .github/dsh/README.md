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

- `settings.yaml`：zen provider 模板，直连 `https://opencode.ai/zen/v1`，
  `apiKeyEnv: OPENCODE_PUBLIC`（值为 `public`），headers 为 opencode CLI wire，
  仅收录已验证模型
- `headers.patch` + `apply-headers-patch.sh`：允许 `settings.yaml` 的 `headers`
  覆盖 harness 归因头（默认 `User-Agent: deepseek-harness/...` 且不可覆盖，
  网关只认 `opencode/...`）。补丁把 `requestHeaders` 改为"部署头赢、归因补齐"，
  其他 provider（未配 UA 的）行为不变。插件机制做不到：归因是写死的合并顺序，
  不是可挂载服务；上游若接受 white-label identity 配置即可删除本补丁
- 凭证（不进仓库）：`~/.dsh/.credentials.yaml` 须为 `version: 1`，`refs` 全字符串，
  `OPENCODE_PUBLIC: public`，`DEEPSEEK_API_KEY` 占位（dsh 只做存在性校验，
  zen 路由不使用它）

## 已验证矩阵（`dsh-acp-interactive` 1.3.0，直连，无代理）

- `zen:big-pickle` → `end_turn`
- `zen:mimo-v2.5-free` → `end_turn`，`agent_message_chunk` 为 `HI`
- responses 路模型（如 muse-spark）暂不收录：dsh 只认 provider 级 `api`，
  模型级 `api` 被忽略，会走错 `/chat/completions` 路径

## 接入

```sh
npm install --global deepseekharness-acp-interactive@1.3.0
install -m 0644 .github/dsh/settings.yaml ~/.dsh/settings.yaml
./.github/dsh/apply-headers-patch.sh
```

paseo 侧 provider（见 `.github/paseo-config.json`）：

```json
"dsh": { "extends": "acp", "label": "DSH", "command": ["dsh-acp-interactive"] }
```
