# maki (nix packaging + zen wire identity)

`maki` 0.5.5 (https://github.com/tontinton/maki)：Rust TUI coding agent，
OpenCode Zen 是其内置 provider（`OPENCODE_API_KEY`，免费模型走 `public`
fallback）。本目录只做“适合的”最小改动，与 reasonix 覆盖层对齐：

- `default.nix`：`rustPlatform.buildRustPackage` 打包，`patches = [ ./fix.patch ]`
  单 patch 文件（与 reasonix 约定一致：只有一个 patch、无 postPatch）。
- `fix.patch`（git 生成）：只动 provider 传输层通用代码，**不动**
  `maki-providers/src/providers/opencode.rs`（内置流程完全不用）。内容：
  - `providers/mod.rs`：`ResolvedAuth.opencode_wire` 标记 +
    `OPENCODE_TLS12_CIPHERS`（捕获的 14 个 TLS 1.2 套件）+
    `opencode_tls()`（按请求 pin 套件顺序）+ `is_zen_base_url()`
    （base-URL 判定，`/zen/go` 排除）+ `apply_zen_wire_identity()`
    （client/request/session 三 header，原子幂等）。
  - `providers/catalog.rs`：内置 zen choke 点复用同一 helper；
    `msg_` 生成器提为 `pub(crate)` 供复用。
  - `providers/custom.rs`：`create()` 对 zen 指向的自定义 slug 置标记；
    `stream_message()` 每次调用盖新鲜 `msg_` + 会话 session。
  - `providers/openai_compat.rs`（chat 三处）与
    `providers/openai/responses.rs`（responses 一处）：发送路径包一层
    `opencode_tls()`。非 zen 请求零变化。
  - `User-Agent` 不在 patch 里：两条 wire 各自的捕获 UA
    （chat `…/4.0.23…` / responses `…/4.0.40…`）由配置侧
    `[<slug>.headers]` 下发（auth/config header 后置覆盖 builder
    默认值，已实证），静态 header 不值得进代码。
  - `x-opencode-project` 故意省略（provider 层无 repo 上下文，网关缺它
    照常服务，有指名拒绝时再加）。
- `maki-config.py`：`reasonix-config.py` 的变种。同样的免费模型发现逻辑
  （官方 `/models` ∩ models.dev：非 deprecated、可输出 text、tool_call 未
  禁用、input/output 费用为 0；zen 按 npm 再分 responses/chat），写
  `~/.config/maki/providers.toml` 的三个**自定义**表（保留其它表，
  不写 `[opencode]` 内置表）：`zen-chat`（openai）、`zen-responses`
  （openai-responses，均用 `public` key + 各自 UA + 免费模型声明 +
  `discover_models`）、`nvidia`（openai 直连、自有 key env）。不碰任何
  Rust 源码，幂等可重跑。
- `overlays/maki-config.nix`：只渲染 `init.lua` 选择策略（nix 自带 Lua
  函数 `lib.generators.toLua` 序列化参数 + `writeText` 包
  `maki.setup()` 调用，签名见 noogle），含 reasonix 全局项中 init.lua
  层面可映射的 `default_model`/`allowed_models`。**不渲染
  `providers.toml`**：provider 与模型数据是实时数据，只能由
  `maki-config.py` 生成。与 `maki-config.py` 二选一（前者给策略，
  后者给数据）。

## 用法

```sh
# 构建 / 本地安装测试
nix build .#maki && ./result/bin/maki --version
# 模型配置（二选一；均只写自定义表，不碰内置流程）
python3 overlays/maki/maki-config.py
# 或 nix 声明式（只出 init.lua 策略文件，链入 ~/.config/maki/；
# providers.toml 与模型数据一律由 maki-config.py 生成）
nix build .#maki-config && cat result
# 使用模型：zen-chat/big-pickle zen-responses/muse-spark-1.3-contributor-free
```

## TLS 实测（本地 ClientHello 探针，非声明）

方法：裸 TCP 服务端直读 ClientHello 明文字节（无 TLS 栈、无证书），
同一 isahc 1.8.3 分别以默认与 pin 后配置各发一次，对照
`overlays/reasonix/opencode/tls-fingerprint.json` 的 17 套件顺序
（`1301 1302 1303 c02b c02f c02c c030 cca9 cca8 c009 c013 c00a c014
009c 009d 002f 0035`）：

- 默认：`1302 1303 1301 c02c c030 …`（TLS 1.2 顺序完全是 OpenSSL 自家的）。
- pin 后：`1302 1303 1301 c02b c02f c02c c030 cca9 cca8 c009 c013
  c00a c014 009c 009d 002f 0035 00ff`——14 个 TLS 1.2 套件与捕获**逐字节
  全等**；残留差为本栈 TLS 1.3 头部内部顺序 + 尾部 SCSV，curl API 无
  TLS 1.3 套件旋钮（isahc 1.8.3 仅暴露 `ssl_ciphers`），属实测边界。
- ALPN：`http/1.1` pin（既有）与捕获一致。

bun 源码对照（`/tmp/bun`，oven-sh/bun depth-1）：fetch 链路无自定义
cipher 列表（仅 `node:tls` 兼容层有常量），即捕获套件顺序就是
BoringSSL 默认输出——pin 复制的正是这一段；bun 显式启用 SCT/OCSP
（`configure_http_client_with_alpn`，对应捕获 ext 18/5），isahc 无
对应开关；groups/sigalgs/扩展顺序/GREASE 均为 BoringSSL 形状，curl
无 API 可调。结论：套件段全等、其余诚实声明差距，不做 JA3 全等宣称。
注：curl 连接复用下握手只发生一次，pin 在握手时生效；同一 client 内
zen 请求间的复用是一致的（同 pin），不存在指纹串扰。

## 缺口论证：JA3 全等与 x-opencode-project（结论：不做，有证据）

以下两项经完整可行性论证后判定为“十分复杂”，按任务条件句不实施；
论证留档，触发条件明确，任一触发即开工。

### 1. JA3 全等（扩展/groups/sigalgs 差）

残留差清单（探针实测 + isahc 1.8.3 源码逐项确认无 API）：TLS 1.3 头部
内部顺序（无 TLS 1.3 套件旋钮）、尾部 SCSV（无 SCSV 开关）、扩展集合与
顺序（含 bun 显式启用的 SCT ext 18 / OCSP ext 5，isahc 无 verify-status
开关）、groups 顺序、sigalgs 集合与顺序、GREASE/padding（BoringSSL
形状）。curl 能动的只有 TLS 1.2 套件表——已用尽。

全等的唯一路径是换 TLS 栈（`boring` crate）：boring-sys 在构建时从源码
编译整个 BoringSSL（docs.rs 5.2.0 原话 "builds the BoringSSL
library"，需 CMake/Go/Perl 工具链进 nix `nativeBuildInputs` +
`cargoHash`  churn + 长编译），且 isahc 的 curl 句柄自带 TLS、无法外挂
第三方握手——必须另写 HTTPS 传输（hyper/tokio 或手写），连带 SSE 解析、
代理、证书校验行为全部重写并重测，还要与 smol 运行时互操作。这是新传输
层，不是 patch。免费层历来以 HTTP 身份为准（全部捕获与 400 样本无一指名
TLS），投入产出比为负。触发条件：出现指名 JA3/指纹类的 403/400 拒绝。

### 2. x-opencode-project 双 wire 省略

候选方案逐个否决：(a) provider 层读 `current_dir()` 推导——maki 有多
root/daemon/子代理场景，推导会错，错的归因比缺失更坏（网关会把请求记到
错误的 project 下）；(b) 恒发 `"global"`——CLI 只在非 git 目录发
`"global"`，git 仓库下恒发等于伪造信号，违反“不伪造可验证字段”原则；
(c) 省略——网关无此头照常服务（maki 上游长期无任何 x-opencode 头即可
工作；全部观测到的拒绝都指名其它字段）。正确 Plumbing 需要把 cwd 从
agent 层穿过 provider curstom/catalog 两条链路（改 `RequestOptions` +
多文件），复杂度中等、收益为零。触发条件：出现指名 project 的拒绝，届
时按 CLI 真算法（remote→cached→root→global）实现。

## 已知限制（诚实记录）

1. TLS 止于“套件段全等 + ALPN 一致”（上见实测）。JA3 全等需要换 TLS
   栈，见上节论证；当前停止点是测量驱动的，不是偷懒。
2. chat 与 responses 双 wire 均已支持（`zen-chat`/`zen-responses` 自定义
   slug，各自捕获 UA）；若上游新增 wire 类型，按同样模式加 slug 即可。
3. maki 推理以明文保存/回放，不回放 issuer 绑定的 `encrypted_content`，
   天然免疫 pi-opencode 遇到的
   “reasoning `encrypted_content` was not issued to this caller” 400，
   此覆盖层无需重试逻辑。
