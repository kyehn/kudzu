# dsh overlay

[`deepseek-harness`](https://github.com/deepseek-ai/deepseek-harness)（dsh）的
nix 打包：一个 `buildNpmPackage` 产物同时提供 **dsh CLI**（headless）与
**Paseo 的 ACP provider**（`dsh-acp-paseo-launch`），并移植 opencode 模拟
（`dsh-llm-opencode-zen` 插件）与 [reasonix 配置模型](../dsh-config.nix)。

## 结构（每个部件的作用）

| 文件 | 作用 |
| --- | --- |
| `default.nix` | `buildNpmPackage` 打包 `@deepseek-ai/dsh@0.1.0-rc.7` + `dsh-llm` + `dsh-llm-deepseek` + 两个 `file:` 本地插件 + `dsh-acp-paseo`；`buildPhase`（在 `npm ci` 之后）运行 `patch-llm-deepseek.sh` 并编译两个插件的 TS；`postInstall` 生成 wrapper |
| `opencode-zen/` | `llm-opencode-zen` 插件：opencode 的 UA、`x-opencode-*` headers、id 生成逐字节移植；请求体/响应体**不自行构建**，复用 `serializeRequest`/`parseSse`/`translate` |
| `nvidia-nim/` | `llm-nvidia-nim` 插件：NVIDIA NIM 通道，models.dev 聊天模型过滤 |
| `openssl.cnf` | Node TLS cipher 顺序对齐 BoringSSL（见下） |
| `patch-llm-deepseek.sh` | 构建期补 `dsh-llm-deepseek`：追加导出三个序列化函数，并让 `parseSse` 接受 zen 兼容层的 `delta.reasoning` 别名（思考块回传修复，见下） |
| `package.json` / `package-lock.json` | npm 依赖清单与锁定文件——`buildNpmPackage` 的标准输入（`npm ci` 用），不是额外发明 |
| `paseo-profile-package.json` | `dsh-acp-paseo` profile 的 manifest 模板（bundles 声明），nix 管理 |

**为什么既有插件又有 patch**：插件 = 新增 provider 能力（opencode-zen /
nvidia-nim 是 dsh 生态的标准 LLM 适配器形态）；patch = 修正官方 npm 包
的两个缺口（未导出可复用的序列化函数；`parseSse` 不认 zen 的 reasoning
字段）。职责不同，缺一不可。patch 目标是 `npm ci` 之后才落盘的
`node_modules` 文件，`applyPatches`（patchPhase）太早，所以是构建期脚本；
两个 patch 都保持幂等（grep 后追加/替换）。

**opencode-zen / nvidia-nim 为什么分开**：dsh 的插件约定是每个 provider
一个适配器包（官方 `dsh-llm-deepseek` 同样如此），两个插件各自注册
`opencode-zen` 与 `nvidia-nim` 路由，互不耦合。

## 运行时配置（全部 nix 管理）

- **无 `$DSH_HOME/cordis.patch.yml`**：`dsh` / `dsh-acp-paseo-launch`
  wrapper 从 `$out/share/dsh/`（只读 store）把 profile manifest 与
  `cordis.patch.yml` 落到 `$DSH_HOME/profiles/dsh-acp-paseo/`，每次运行
  重新 install（store 路径变更后不会残留旧配置）。
- 配置内容来源是 [`../dsh-config.nix`](../dsh-config.nix)：MCP servers
  （mcp-nixos、context7-mcp、mobile-mcp、open-websearch、grep-app，每个是
  一个 `dsh-mcp-client` 插件实例）、sandbox `danger-full-access`、
  approval `never`——**零 provider/模型数据**（最多允许默认模型名）。
- **默认 provider/model 是环境变量，不是配置文件**：
  `DSH_ACP_PASEO_PROVIDER=opencode-zen`、`DSH_ACP_PASEO_MODEL=deepseek-v4-flash-free`
  （wrapper 提供默认值，用户显式设置优先）。

## 为什么选择 dsh-acp-paseo（而非 deepseek-acp）

对比过 6 个社区 ACP 桥后选定
[`Pheobe-Southwood/dsh-acp-paseo`](https://github.com/Pheobe-Southwood/dsh-acp-paseo)：

- **专门为 Paseo 设计**：模型目录、plan/execute 模式、思考强度、斜杠命令
  全部从 dsh 侧自动发现，Paseo 端零配置。
- **标准 dsh profile bundle 机制**：桥以 `cordis.patch.yml` 挂载
  （bundles = `[dsh-base, dsh-acp-paseo]`），provider/model 通过
  `DSH_ACP_PASEO_PROVIDER/MODEL` 环境变量钉住——因此我们的两个 LLM
  插件走同一个 profile patch 注入，**不再需要 hack 其源码**
  （`patch-deepseek-acp.sh` 已删除）。
- `resolveDsh` 优先 `DSH_ACP_PASEO_DSH`，其次 PATH；profile 健康时
  `ensureProfile` 不联网自愈，nix 预置 profile 即可离线运行。
- launcher 处理 Paseo 的 `--version` 探针；stdout 只走 ACP 帧。

其余插件的取舍：xintaofei/deepseek-acp（此前所用）装配固定、需注入
patch；openma-ai 通用 ACP（面向 Zed/Backchat，能力最全但依赖 dsh web
凭据）；其余三个维护/功能/定位均不占优。

## reasoning_content 修复（thinking 模式回传）

`The reasoning_content in the thinking mode must be passed back to the
API` 的根因：zen 兼容层把 DeepSeek 思考流式输出为
`delta.reasoning`（+ `reasoning_details`），而官方
`dsh-llm-deepseek` 的 `parseSse` 只收集 `delta.reasoning_content` →
思考块被丢弃 → 会话历史无 reasoning → 下一轮 assistant tool-call 消息
不带 `reasoning_content` → Console 400。修复：`patch-llm-deepseek.sh`
把该行改为 `delta?.reasoning_content ?? delta?.reasoning`，用
`/tmp` 内的本地复现脚本验证了 FAIL→PASS（解析出思考块，且下一轮 wire
消息带 `reasoning_content`）。

## TLS 指纹的诚实说明

目标（opencode）是 Bun 运行时 + BoringSSL。dsh 依赖
`node:module.stripTypeScriptTypes`（Bun 未实现），只能跑在 Node/OpenSSL
上，**逐字节复刻整条 TLS 指纹不可能**：

- cipher 顺序通过 `openssl.cnf` 对齐 BoringSSL 默认偏好（TLS1.3 按
  1301/1302/1303，TLS1.2 按 AES-GCM 优先）；`--openssl-config` 对
  **macOS / Linux / Windows 上的 Node 通用**（Node 三平台都链 OpenSSL，
  配置语法一致），macOS 可以直接使用。
- TLS 扩展顺序 OpenSSL 无配置接口，与 BoringSSL 不同——文档诚实声明。
- HTTP 层特征（UA、`x-opencode-*` headers、id 生成逻辑）逐字节一致。

## 使用

```bash
nix build .#dsh
# dsh CLI（headless 测试/诊断）
result/bin/dsh --profile headless "hi"
# Paseo provider（命令注册进 ~/.paseo/config.json 的 command 数组）
result/bin/dsh-acp-paseo-launch --version
```

`paseo-config.json` 把 provider `dsh` 指向 `dsh-acp-paseo-launch`；
`.github/workflows/paseo.yml` 只做 `nix profile add .#dsh`，其余零配置。