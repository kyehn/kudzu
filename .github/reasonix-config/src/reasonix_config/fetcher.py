from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

CACHE_DIR = Path("/tmp/reasonix-models")  # noqa: S108
MODELS_DEV_CACHE = CACHE_DIR / "models_dev_api.json"
OFFICIAL_LIST_CACHE = CACHE_DIR / "official_{pid}_models.json"

# models.dev / 各官方名单会变 (如下架 → status=deprecated, 免费推广结束);
# 过期后必须重新拉取, 否则 deprecated 过滤会一直用旧快照.
CACHE_TTL_SECONDS = 3600

MODELS_DEV_API = "https://models.dev/api.json"

# 与 opencode packages/core/src/models-dev.ts 一致: opencode/<channel>/<version>/<client>
# 发布版 channel 为 "prod" (源码 .github/workflows/publish.yml), client 默认 "cli".
MODELS_DEV_USER_AGENT = "opencode/prod/1.18.26/cli"

OFFICIAL_LIST_TIMEOUT = 30.0
HTTP_NOT_FOUND = 404


def _load_fresh_cache(path: Path) -> dict | None:
    """返回 TTL 内的缓存快照; 文件消失或内容损坏视为未命中, 走网络重新拉取."""
    try:
        age = time.time() - path.stat().st_mtime
        if age >= CACHE_TTL_SECONDS:
            return None
        return json.loads(path.read_text())
    except (OSError, ValueError):
        # 缓存不可用不能让工具崩溃, 真正的网络错误由请求路径原样抛出.
        return None


def fetch_models_dev() -> dict:
    cached = _load_fresh_cache(MODELS_DEV_CACHE)
    if cached is not None:
        return cached
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    resp = httpx.get(MODELS_DEV_API, timeout=60, headers={"User-Agent": MODELS_DEV_USER_AGENT})
    resp.raise_for_status()
    data = resp.json()
    MODELS_DEV_CACHE.write_text(json.dumps(data, indent=2))
    return data


def fetch_official_models(
    provider_entry: dict, pid: str, api_key: str = "", use_cache: bool = True
) -> dict:
    """官方在售名单: models.dev provider 条目 api 派生的 ``{api}/models``.

    pid 是调用方传入的 models.dev 顶层 key, 只做缓存文件名
    (``official_{pid}_models.json``); 条目内没有可信 id 字段, 用
    ``entry.get("id")`` 会恒为 unknown 导致多家共享同一缓存文件.

    opencode zen 无需认证; NIM 需 ``Authorization: Bearer <key>`` (无 key
    直接 fail-closed, 不猜名单). 返回的 ``{"data": [{"id": ...}]}`` 形态
    两家一致 (OpenAI /v1/models 兼容); 形态不符 fail-closed.
    """
    try:
        base_url = provider_entry["api"].rstrip("/")
    except (KeyError, AttributeError) as exc:
        msg = f"models.dev provider entry has no usable 'api': {provider_entry!r}"
        raise SystemExit(msg) from exc
    url = f"{base_url}/models"
    headers = {"User-Agent": MODELS_DEV_USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    cache_path = OFFICIAL_LIST_CACHE.with_name(OFFICIAL_LIST_CACHE.name.format(pid=pid))
    cached = _load_fresh_cache(cache_path) if use_cache else None
    if cached is not None:
        return cached
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        resp = httpx.get(url, timeout=OFFICIAL_LIST_TIMEOUT, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        msg = f"official model list unavailable at {url}: {exc}"
        raise SystemExit(msg) from exc
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        msg = f"official model list at {url} has unexpected shape (want {{'data': [...]}})"
        raise SystemExit(msg)
    cache_path.write_text(json.dumps(data, indent=2))
    return data


def probe_nvidia_live(
    models: list[str],
    api_key: str,
    base_url: str,
    timeout: float = 45.0,
) -> set[str]:
    """NIM 探活: 返回确认不可用的模型 id 集合 (仅 HTTP 404).

    base_url 取自 models.dev provider 条目 (chat 端点为 ``{api}/chat/completions``).
    每个候选发一次最小请求 (max_tokens=8, 不流式). 只有网关明确报
    404 (Function not found) 才算证伪; 超时/5xx/限流等含混结果一律
    保留 (宁可误收可用模型, 不可在网络抖动时误删). 调用方无 key 或
    全网失败时应跳过探活而非清空名单 (见 __main__ 的 fail-open 处理).
    """
    dead: set[str] = set()
    url = f"{base_url.rstrip('/')}/chat/completions"
    with httpx.Client(timeout=timeout) as client:
        for mid in models:
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                resp = client.post(
                    url,
                    headers=headers,
                    json={
                        "model": mid,
                        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                        "max_tokens": 8,
                        "stream": False,
                    },
                )
            except httpx.HTTPError:
                continue  # 含混: 超时/断连, 保留
            if resp.status_code == HTTP_NOT_FOUND:
                dead.add(mid)
    return dead
