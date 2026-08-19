# dsh-config

将 [`.github/reasonix-config`](../reasonix-config/) 的配置模型移植到
[`deepseek-harness`](https://github.com/deepseek-ai/deepseek-harness)（dsh）的
配置生成工具。功能与原版等价，唯一差异是**输出格式**：生成 dsh 的
`cordis.patch.yml` 与 `.credentials.yaml`，而不是 reasonix 配置。

## 原则

- **配置内不硬编码模型/provider 数据**：模型列表运行时从
  `https://opencode.ai/zen/v1/models`（Bearer `public`）与
  `https://models.dev/api.json` 动态获取。nix 配置中最多只出现默认模型名称
  `deepseek-v4-flash-free`。
- **与原版相同的行为**：免费/聊天模型过滤、默认模型修复、缺失时写入
  `OPENCODE_API_KEY: public` 凭证、`dsh doctor` 验证，全部照搬 reasonix 逻辑。

## 功能

- 抓取并缓存模型列表（缓存目录 `$XDG_CACHE_HOME/dsh-config-models`，
  默认 `/tmp/dsh-config-models`，同原版）。
- 过滤：
  - 免费模型（`-free` 后缀 / `big-pickle`）
  - 聊天模型（`MIN_CHAT_CONTEXT = 8000` + `SKIP_PATTERNS`）
- 默认模型解析：保留现有有效默认 → `deepseek-v4-flash-free` → 第一个可用。
- 写 `$DSH_HOME/cordis.patch.yml`（行级更新 model 行，保留用户其他行）与
  `$DSH_HOME/.credentials.yaml`（`chmod 600`，保留已有 key）。
- 运行 `dsh --profile headless --dump-config` 验证配置（doctor）。

## 使用

```sh
python -m venv .venv && .venv/bin/pip install -e .
export PATH="$PWD/result/bin:$PATH"   # dsh 在 PATH 中，供 doctor 调用
DSH_HOME=~/.dsh .venv/bin/dsh-config
```

`--provider` 可过滤只处理某个 provider（`opencode-zen` / `nvidia-nim`）。

## 开发

```sh
.venv/bin/pip install -e '.[dev]'     # ruff + pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
```