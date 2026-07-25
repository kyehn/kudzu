# reasonix-provider-config

> OpenCode-to-ReasonIX provider configuration sync and mapping tool.

## 功能

1. **Provider 同步** — 从 OpenCode Zen 和 NVIDIA NIM 抓取模型列表，与 models.dev 交叉引用，
   生成 ReasonIX `~/.reasonix/config.toml` provider 配置
2. **字段映射** — OpenCode `LLMRequest` 选项到 ReasonIX `ProviderEntry` TOML 字段的完整映射
3. **文档** — 基于源码分析 + 实证捕获的 OpenCode HTTP 请求特征分析

## 安装

```bash
pip install -e /home/runner/work/kudzu/kudzu/.github/reasonix_provider_config
```

## 使用

### Provider 同步

```bash
# 同步所有 provider（默认）
reasonix-provider-config

# 仅 OpenCode Zen
reasonix-provider-config --provider opencode-zen

# 仅 NVIDIA NIM
reasonix-provider-config --provider nvidia-nim

# 明确指定两者
reasonix-provider-config --provider opencode-zen nvidia-nim
```

### 查看字段映射

```bash
reasonix-provider-config show-mapping
```
or
```bash
reasonix-provider-config mapping
```

## OpenCode HTTP 特征

请参考 [docs/01-opencode-http-analysis.md](docs/01-opencode-http-analysis.md) 获取完整的
基于源码分析 + MITM 代理实证捕获的 HTTP 请求特征分析。

## 架构

```
reasonix_provider_config/
├── docs/
│   ├── 01-opencode-http-analysis.md     # HTTP 请求特征完整分析
│   ├── 02-reasonix-field-mapping.md     # 字段映射
│   ├── 03-gap-workarounds.md            # 差距与变通
│   ├── 04-opencode-every-option.md      # 全部选项映射
│   └── 05-reference-quickstart.md       # 快速参考
├── config-examples/
│   ├── zen-free.toml                    # OpenCode Zen 免费模型
│   └── nvidia-nim.toml                  # NVIDIA NIM
├── src/reasonix_provider_config/
│   ├── __main__.py                      # CLI 入口（sync）
│   ├── api.py                           # API 客户端
│   ├── cache.py                         # 缓存
│   ├── config.py                        # 配置读写
│   ├── models.py                        # 数据模型
│   ├── cli.py                           # CLI （mapping 子命令）
│   └── mapping.py                       # 字段映射逻辑
└── pyproject.toml
```
