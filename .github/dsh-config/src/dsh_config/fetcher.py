from __future__ import annotations

import json
from pathlib import Path

import httpx

CACHE_DIR = Path("/tmp/dsh-models")  # noqa: S108
ZEN_CACHE = CACHE_DIR / "opencode_zen_models.json"
MODELS_DEV_CACHE = CACHE_DIR / "models_dev_api.json"

ZEN_API = "https://opencode.ai/zen/v1/models"
MODELS_DEV_API = "https://models.dev/api.json"

# 与 opencode packages/core/src/models-dev.ts 一致: opencode/<channel>/<version>/<client>
# 发布版 channel 为 "prod" (源码 .github/workflows/publish.yml), client 默认 "cli".
MODELS_DEV_USER_AGENT = "opencode/prod/1.18.14/cli"


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
