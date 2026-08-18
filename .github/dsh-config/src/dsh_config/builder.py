from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dsh_config.fetcher import fetch_models_dev, fetch_zen_models
from dsh_config.models import ModelEntry, ProviderProfile

NVIDIA_API = "https://integrate.api.nvidia.com/v1"
OPENCODE_ZEN_API = "https://opencode.ai/zen/v1"
MIN_CHAT_CONTEXT = 8000


def _lookup_model(models_raw: dict[str, Any], model_id: str) -> tuple[str, dict[str, Any]] | None:
    result = models_raw.get(model_id)
    if result is not None:
        return model_id, result
    normalised = model_id.replace(".", "_")
    result = models_raw.get(normalised)
    if result is not None:
        return normalised, result
    return None


def _build_override(m: dict[str, Any]) -> dict[str, Any]:
    """From models.dev metadata build the llm-pi-ai model entry fields.

    Maps to pi-ai's modelProfile: contextWindow / maxTokens / reasoningEfforts.
    """
    override: dict[str, Any] = {}
    ctx = m.get("limit", {}).get("context", 0)
    if ctx:
        override["context_window"] = ctx
    max_output = m.get("limit", {}).get("output", 0)
    if max_output:
        override["max_tokens"] = max_output
    reasoning = m.get("reasoning", False)
    reasoning_options = m.get("reasoning_options", [])
    if reasoning:
        for opt in reasoning_options:
            if isinstance(opt, dict) and opt.get("type") == "effort":
                values = [v for v in opt.get("values", []) if v is not None]
                if values:
                    override["reasoning_efforts"] = values
                    break
    return override


def _is_chat_model(mid: str, mdata: dict[str, Any]) -> bool:
    limit = mdata.get("limit", {})
    ctx = limit.get("context", 0)
    if ctx < MIN_CHAT_CONTEXT:
        return False
    name_lower = mid.lower()
    skip_patterns = [
        "embed",
        "guard",
        "safety",
        "tts",
        "voice",
        "audio",
        "cosmos-predict",
        "cosmos-transfer",
        "flux",
        "image",
        "edit",
        "rerank",
        "esm",
        "detection",
        "synthetic",
        "validate",
        "whisper",
        "bevformer",
        "streampetr",
        "studiovoice",
        "sparsedrive",
        "usd",
        "riva",
        "magpie",
        "active-speaker",
        "gliner",
    ]
    return all(pat not in name_lower for pat in skip_patterns)


def get_free_zen_model_ids(zen_data: dict) -> set[str]:
    ids: set[str] = set()
    for m in zen_data.get("data", []):
        mid = m["id"]
        if "-free" in mid or mid == "big-pickle":
            ids.add(mid)
    return ids


def get_opencode_zen_free_providers() -> list[ProviderProfile]:
    zen_data = fetch_zen_models()
    md_data = fetch_models_dev()

    free_ids = get_free_zen_model_ids(zen_data)
    oc_provider = md_data.get("opencode", {})
    oc_models_raw: dict[str, Any] = oc_provider.get("models", {})

    entries: list[ModelEntry] = []
    for mid in sorted(free_ids):
        lookup = _lookup_model(oc_models_raw, mid)
        if lookup is None:
            entries.append(ModelEntry(id=mid))
            continue
        _resolved_id, m = lookup
        status = m.get("status", "")
        if status == "deprecated":
            continue
        entries.append(ModelEntry(id=mid, name=m.get("name"), **_build_override(m)))

    if not entries:
        msg = "No free OpenCode Zen models found"
        raise SystemExit(msg)

    cfg = ProviderProfile(
        name="opencode-zen",
        kind="openai",
        base_url=OPENCODE_ZEN_API,
        models=entries,
        default=entries[0].id,
        # api_key_env="OPENCODE_API_KEY" → dsh 从凭据服务解析该引用并发送
        # Authorization: Bearer public (匹配 opencode 客户端默认行为).
        # dsh-config 每次运行自动确保 ~/.dsh/.credentials.yaml 中有该条目.
        api_key_env="OPENCODE_API_KEY",
        # 与 opencode 客户端 (packages/opencode/src/session/llm/request.ts) 高度一致:
        #   - overlays/dsh 的 opencode-fetch 在 HTTP 层自动打上 opencode 头部
        #     (User-Agent=opencode/1.18.18 ..., Accept: */*,
        #     Accept-Encoding: gzip, deflate, br, zstd, x-opencode-*), 并用
        #     node-tls-client 复刻 CLI 的 BoringSSL TLS 指纹 (JA3), 因此这里
        #     不再写静态 headers.
        #   - X-Opencode-Session (ses_<descending 编码>) 由补丁每进程动态生成,
        #     X-Opencode-Request (msg_<ascending 编码>) 每请求生成 —
        #     与 opencode src/id/id.ts 的 create() 逐字节一致, 静态配置无法表达.
        headers=None,
    )
    return [cfg]


def get_nvidia_providers() -> list[ProviderProfile]:
    md_data = fetch_models_dev()
    nv_provider = md_data.get("nvidia", {})
    nv_models_raw: dict[str, Any] = nv_provider.get("models", {})

    entries: list[ModelEntry] = []
    for mid, m in sorted(nv_models_raw.items()):
        status = m.get("status", "")
        if status == "deprecated":
            continue
        if not _is_chat_model(mid, m):
            continue
        ctx = m.get("limit", {}).get("context", 0)
        if ctx < MIN_CHAT_CONTEXT:
            continue
        entries.append(ModelEntry(id=mid, name=m.get("name"), **_build_override(m)))

    if not entries:
        msg = "No NVIDIA NIM chat models found"
        raise SystemExit(msg)

    cfg = ProviderProfile(
        name="nvidia-nim",
        kind="openai",
        base_url=NVIDIA_API,
        models=entries,
        default=entries[0].id,
        api_key_env="NVIDIA_API_KEY",
    )
    return [cfg]


def build_all(providers_filter: list[str] | None = None) -> list[ProviderProfile]:
    providers: list[ProviderProfile] = []
    if providers_filter is None or "opencode-zen" in providers_filter:
        providers.extend(get_opencode_zen_free_providers())
    if providers_filter is None or "nvidia-nim" in providers_filter:
        providers.extend(get_nvidia_providers())
    return providers


@dataclass(frozen=True)
class WriteResult:
    settings: Path
    credentials: Path


def _resolve_dsh_home(dsh_home: str | None) -> Path:
    if dsh_home is not None:
        return Path(dsh_home).expanduser().resolve()
    env = os.environ.get("DSH_HOME", "")
    if env.strip():
        return Path(env).expanduser().resolve()
    return (Path.home() / ".dsh").resolve()


def _ensure_opencode_public_key(credentials_path: Path) -> None:
    """Ensure ``OPENCODE_API_KEY: public`` is in ``$DSH_HOME/.credentials.yaml``.

    opencode Zen 默认使用 Bearer public 作为凭据. dsh 从 Home 目录的
    .credentials.yaml 读取凭据 (CredentialRef → string 映射). 该函数在已有
    文档中添加/更新该条目, 保留其他所有现有凭据.
    """
    key = "OPENCODE_API_KEY"
    value = "public"
    if credentials_path.exists():
        existing = yaml.safe_load(credentials_path.read_text()) or {}
        if not isinstance(existing, dict):
            msg = f"credentials file {credentials_path} must be a mapping"
            raise SystemExit(msg)
        existing[key] = value
        credentials_path.write_text(yaml.safe_dump(existing, sort_keys=True))
    else:
        credentials_path.write_text(yaml.safe_dump({key: value}, sort_keys=True))
    credentials_path.chmod(0o600)


def write_config(
    providers: list[ProviderProfile],
    dsh_home: str | None = None,
) -> WriteResult:
    """Merge provider profiles into ``$DSH_HOME/settings.yaml``.

    - ``llm-pi-ai.providers``: dict keyed by provider name, replaced wholesale.
    - ``agent-default-model``: first provider's default model.
    - Ensures ``OPENCODE_API_KEY: public`` in ``.credentials.yaml``.
    """
    home = _resolve_dsh_home(dsh_home)
    settings_path = home / "settings.yaml"
    credentials_path = home / ".credentials.yaml"
    home.mkdir(parents=True, exist_ok=True)

    settings: dict[str, Any] = {}
    if settings_path.exists():
        loaded = yaml.safe_load(settings_path.read_text()) or {}
        if isinstance(loaded, dict):
            settings = loaded

    settings["llm-pi-ai"] = {
        "providers": {
            p.name: p.to_profile() for p in providers
        }
    }

    # 默认模型: 第一个 provider 的 default; 若旧值仍有效则保留 (与
    # reasonix-config 的 _repair_default_model 语义一致).
    default_provider = providers[0]
    old_selection = settings.get("agent-default-model")
    if old_selection is None or not _selection_still_valid(old_selection, providers):
        settings["agent-default-model"] = {
            "provider": default_provider.name,
            "model": default_provider.default or default_provider.models[0].id,
        }

    settings_path.write_text(yaml.safe_dump(settings, sort_keys=False))

    _ensure_opencode_public_key(credentials_path)
    return WriteResult(settings=settings_path, credentials=credentials_path)


def _selection_still_valid(
    selection: dict[str, Any],
    providers: list[ProviderProfile],
) -> bool:
    provider = selection.get("provider")
    model = selection.get("model")
    for p in providers:
        if p.name != provider:
            continue
        return any(m.id == model for m in p.models)
    return False
