from __future__ import annotations

import json
from pathlib import Path

import httpx

CACHE_DIR = Path("/tmp/reasonix-models")  # noqa: S108
ZEN_CACHE = CACHE_DIR / "opencode_zen_models.json"
MODELS_DEV_CACHE = CACHE_DIR / "models_dev_api.json"

ZEN_API = "https://opencode.ai/zen/v1/models"
MODELS_DEV_API = "https://models.dev/api.json"

# 与 opencode packages/core/src/models-dev.ts 一致: opencode/<channel>/<version>/<client>
# 发布版 channel 为 "prod" (源码 .github/workflows/publish.yml), client 默认 "cli".
#
# 版本必须与仓库内 opencode 模拟实现锁在同一 opencode CLI 版本:
#   - overlays/reasonix/alignment.patch 的 opencodeUserAgent 常量
#     (opencode/1.18.18 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14)
#   - overlays/reasonix/opencode/ 下的抓包基准 (_tls-fingerprint.json /
#     POST_zen_v1_*.json 记录的是同一版本的真实 ClientHello/请求)
# 三者版本漂移即为模拟失配, 对应测试 (test_fetcher.py) 会失败.
OPENCODE_VERSION = "1.18.18"
MODELS_DEV_USER_AGENT = f"opencode/prod/{OPENCODE_VERSION}/cli"


def fetch_zen_models() -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if ZEN_CACHE.exists():
        return json.loads(ZEN_CACHE.read_text())
    resp = httpx.get(ZEN_API, timeout=30, headers={"User-Agent": MODELS_DEV_USER_AGENT})
    resp.raise_for_status()
    data = resp.json()
    ZEN_CACHE.write_text(json.dumps(data, indent=2))
    return data


def fetch_models_dev() -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if MODELS_DEV_CACHE.exists():
        return json.loads(MODELS_DEV_CACHE.read_text())
    resp = httpx.get(MODELS_DEV_API, timeout=60, headers={"User-Agent": MODELS_DEV_USER_AGENT})
    resp.raise_for_status()
    data = resp.json()
    MODELS_DEV_CACHE.write_text(json.dumps(data, indent=2))
    return data