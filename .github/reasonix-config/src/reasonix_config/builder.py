from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from reasonix_config.fetcher import fetch_models_dev, fetch_zen_models
from reasonix_config.models import ModelOverride, Pricing, ProviderConfig

REASONIX_CONFIG = Path.home() / ".reasonix" / "config.toml"
NVIDIA_API = "https://integrate.api.nvidia.com/v1"
OPENCODE_ZEN_API = "https://opencode.ai/zen/v1"
MIN_CHAT_CONTEXT = 8000
CONFIG_VERSION = 5


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
    """从 models.dev 元数据构建 model_overrides 条目.

    输出字段名与 reasonix ProviderModelOverride 的 toml tag 严格一致:
    context_window / max_output_tokens / reasoning_protocol / supported_efforts /
    default_effort / vision. (thinking 仅存在于 ProviderEntry 级, 不放这里.)
    """
    override: dict[str, Any] = {}
    ctx = m.get("limit", {}).get("context", 0)
    if ctx:
        override["context_window"] = ctx
    max_output = m.get("limit", {}).get("output", 0)
    if max_output:
        override["max_output_tokens"] = max_output
    reasoning = m.get("reasoning", False)
    reasoning_options = m.get("reasoning_options", [])
    if reasoning:
        override["reasoning_protocol"] = "openai"
        for opt in reasoning_options:
            if isinstance(opt, dict) and opt.get("type") == "effort":
                values = [v for v in opt.get("values", []) if v is not None]
                if values:
                    override["supported_efforts"] = values
                    # 取最高级别: 最后一个非 "none" 的值
                    non_none = [v for v in values if v != "none"]
                    override["default_effort"] = non_none[-1] if non_none else values[-1]
                    break
    modalities_input = m.get("modalities", {}).get("input", [])
    if m.get("attachment") or ("image" in (modalities_input or [])):
        override["vision"] = True
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


def get_opencode_zen_free_providers() -> list[ProviderConfig]:
    zen_data = fetch_zen_models()
    md_data = fetch_models_dev()

    free_ids = get_free_zen_model_ids(zen_data)
    oc_provider = md_data.get("opencode", {})
    oc_models_raw: dict[str, Any] = oc_provider.get("models", {})

    models_list: list[str] = []
    model_prices: dict[str, Pricing] = {}
    model_overrides: dict[str, ModelOverride] = {}
    max_context = 0

    for mid in sorted(free_ids):
        lookup = _lookup_model(oc_models_raw, mid)
        if lookup is None:
            models_list.append(mid)
            continue

        _resolved_id, m = lookup

        status = m.get("status", "")
        if status == "deprecated":
            continue

        models_list.append(mid)

        ctx = m.get("limit", {}).get("context", 0)
        max_context = max(max_context, ctx)

        cost = m.get("cost", {})
        price = Pricing(
            input=float(cost.get("input", 0)),
            output=float(cost.get("output", 0)),
            cache_hit=(float(cost["cache_read"]) if cost.get("cache_read") is not None else None),
        )
        if price.input or price.output or price.cache_hit:
            model_prices[mid] = price

        override = _build_override(m)
        if override:
            model_overrides[mid] = ModelOverride(**override)

    if not models_list:
        msg = "No free OpenCode Zen models found"
        raise SystemExit(msg)

    cfg = ProviderConfig(
        name="opencode-zen",
        kind="openai",
        base_url=OPENCODE_ZEN_API,
        models=models_list,
        default=models_list[0],
        # api_key_env="OPENCODE_API_KEY" → reasonix 从 .env 读 key 并发送
        # Authorization: Bearer public (匹配 opencode 客户端默认行为).
        # 每次 reasonix-config 运行自动确保 ~/.reasonix/.env 中有该条目.
        api_key_env="OPENCODE_API_KEY",
        context_window=max_context or 200000,
        prices=model_prices or None,
        model_overrides=model_overrides or None,
        # 与 opencode 客户端 (packages/opencode/src/session/llm/request.ts) 高度一致:
        #   - 打包补丁 overlays/reasonix/alignment.patch 在检测到 provider 名
        #     "opencode-zen" (internal/provider/openai/host.go IsOpenCode) 时自动
        #     打上 opencode 头部 (User-Agent=opencode/1.18.18 ai-sdk/provider-utils/
        #     4.0.23 runtime/bun/1.3.14, Accept: */*, Accept-Encoding: gzip, deflate,
        #     br, zstd, 小写 x-opencode-*), 并用 utls 复刻 CLI 的 BoringSSL TLS
        #     指纹 (JA3=7a2901f41c5282e5fbacb8cb667f626f / JA4=i11ss_08687474702f_...,
        #     internal/netclient/opencode_tls.go), 因此这里不再写静态 headers.
        #   - X-Opencode-Session (ses_<descending 编码>) 由 reasonix 每个客户端
        #     实例动态生成, X-Opencode-Request (msg_<ascending 编码>) 每请求生成 —
        #     与 opencode src/id/id.ts 的 create() 逐字节一致 (opencode_id.go),
        #     静态配置无法表达.
        #   - 基准与抓包数据在 overlays/reasonix/opencode/ (_tls-fingerprint.json
        #     为真实 Bun ClientHello, POST_zen_v1_*.json 为真实请求/响应记录);
        #     版本漂移由 .github/reasonix-config/tests 的一致性测试拦截.
        # 注意: 不要在此设置 opencode 头部, 会与补丁生成的小写 x-opencode-* 重复.
        headers=None,
    )
    return [cfg]


def get_nvidia_providers() -> list[ProviderConfig]:
    md_data = fetch_models_dev()
    nv_provider = md_data.get("nvidia", {})
    nv_models_raw: dict[str, Any] = nv_provider.get("models", {})

    models_list: list[str] = []
    model_prices: dict[str, Pricing] = {}
    model_overrides: dict[str, ModelOverride] = {}
    max_context = 0

    for mid, m in sorted(nv_models_raw.items()):
        status = m.get("status", "")
        if status == "deprecated":
            continue
        if not _is_chat_model(mid, m):
            continue

        ctx = m.get("limit", {}).get("context", 0)
        if ctx < MIN_CHAT_CONTEXT:
            continue

        models_list.append(mid)
        max_context = max(max_context, ctx)

        cost = m.get("cost", {})
        price = Pricing(
            input=float(cost.get("input", 0)),
            output=float(cost.get("output", 0)),
            cache_hit=(float(cost["cache_read"]) if cost.get("cache_read") is not None else None),
        )
        if price.input or price.output or price.cache_hit:
            model_prices[mid] = price

        override = _build_override(m)
        if override:
            model_overrides[mid] = ModelOverride(**override)

    if not models_list:
        msg = "No NVIDIA NIM chat models found"
        raise SystemExit(msg)

    cfg = ProviderConfig(
        name="nvidia-nim",
        kind="openai",
        base_url=NVIDIA_API,
        models=models_list,
        default=models_list[0],
        api_key_env="NVIDIA_API_KEY",
        context_window=max_context or 128000,
        prices=model_prices or None,
        model_overrides=model_overrides or None,
    )
    return [cfg]


def build_all(providers_filter: list[str] | None = None) -> list[ProviderConfig]:
    providers: list[ProviderConfig] = []
    if providers_filter is None or "opencode-zen" in providers_filter:
        providers.extend(get_opencode_zen_free_providers())
    if providers_filter is None or "nvidia-nim" in providers_filter:
        providers.extend(get_nvidia_providers())
    return providers


def _ensure_opencode_public_key() -> None:
    """Ensure ``OPENCODE_API_KEY=public`` is in ``~/.reasonix/.env``.

    opencode Zen 默认使用 Bearer public 作为凭据. reasonix 从 Home 目录
    的 .env 文件读取凭证. 这个函数在已有 .env 中添加/更新该行,
    保留该文件中其他所有现有凭证.
    """
    env_path = REASONIX_CONFIG.parent / ".env"
    key = "OPENCODE_API_KEY"
    value = "public"
    line = f"{key}={value}"

    if env_path.exists():
        existing_lines = env_path.read_text().splitlines()
        seen = False
        new_lines: list[str] = []
        for old_line in existing_lines:
            stripped = old_line.strip()
            if stripped == "" or stripped.startswith("#"):
                new_lines.append(old_line)
            elif stripped.startswith(f"{key}="):
                if not seen:  # 只保留第一个匹配行, 后续重复行丢弃
                    new_lines.append(line)
                    seen = True
            else:
                new_lines.append(old_line)
        if not seen:
            new_lines.append(line)
            new_lines.append("")
        env_path.write_text("\n".join(new_lines) + "\n")
        # .env 含 API 密钥, 统一收紧为仅属主可读写 (新建与更新一致)
        env_path.chmod(0o600)
    else:
        env_path.write_text(f"{line}\n")
        env_path.chmod(0o600)


def _run_reasonix_doctor() -> None:
    """Validate config by running ``reasonix doctor``. Exit on failure."""
    doctor = shutil.which("reasonix")
    if doctor is None:
        sys.stderr.write("warning: 'reasonix' not found on PATH; skipping doctor validation\n")
        return
    try:
        result = subprocess.run(  # noqa: S603 — resolved by shutil.which()
            [doctor, "doctor"],
            timeout=30,
            check=False,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        msg = "'reasonix doctor' timed out after 30s"
        raise SystemExit(msg) from None
    except OSError as exc:
        msg = f"failed to run 'reasonix doctor': {exc}"
        raise SystemExit(msg) from None
    if result.returncode != 0:
        msg = f"'reasonix doctor' exited with code {result.returncode}"
        if result.stderr:
            msg += f"\n{result.stderr.decode(errors='replace').strip()}"
        raise SystemExit(msg)


def write_config(providers: list[ProviderConfig]) -> Path:
    """Read existing config, replace matching providers, and write back.

    - Removes old provider entries whose name matches a new provider.
    - Appends new providers.
    - If ``default_model`` existed but is no longer valid, picks the first
      model of the first provider as replacement.
    - Validates via ``reasonix doctor``.
    - Ensures ``OPENCODE_API_KEY=public`` in reasonix ``.env``.
    """
    config_path = REASONIX_CONFIG
    if not config_path.exists():
        msg = f"config file {config_path} does not exist; run `reasonix setup` first"
        raise SystemExit(msg)

    with config_path.open("rb") as f:
        existing = tomllib.load(f)

    existing["config_version"] = CONFIG_VERSION

    # 删除与新增 provider 同名的旧条目
    new_names = {p.name for p in providers}
    old_providers = existing.get("providers", [])
    existing["providers"] = [p for p in old_providers if p.get("name") not in new_names]
    existing["providers"].extend(p.to_toml() for p in providers)

    # 检查现有的 default_model 是否合法, 不合法则自动修正
    _repair_default_model(existing, providers)

    config_path.write_text(tomli_w.dumps(existing))

    _ensure_opencode_public_key()
    _run_reasonix_doctor()

    return config_path


def _repair_default_model(
    existing: dict[str, Any],
    providers: list[ProviderConfig],
) -> None:
    """If ``default_model`` exists but isn't valid, reset to first available model.

    有效引用集合 = 新 provider 的模型/名字 + 保留的旧 provider 的模型/名字
    (default_model 可能指向未参与本次更新的其他 provider, 不能误判为无效).
    """
    ref = existing.get("default_model")
    if ref is None:
        return

    valid_bare: set[str] = set()
    valid_names: set[str] = set()
    for p in providers:
        valid_names.add(p.name)
        valid_bare.update(p.models)

    new_names = {p.name for p in providers}
    for p in existing.get("providers", []):
        name = p.get("name")
        if name in new_names:
            continue  # 该 provider 即将被本次更新替换, 其模型不再有效
        if name:
            valid_names.add(name)
        if p.get("models"):
            valid_bare.update(p["models"])
        elif p.get("model"):
            valid_bare.add(p["model"])

    if not valid_bare:
        return

    # 检查 ref 是否是有效的 model ID 或 provider name
    if ref in valid_bare or ref in valid_names:
        return

    # 检查 provider/model 格式
    if "/" in ref:
        prov_name, model_id = ref.split("/", 1)
        if prov_name in valid_names and model_id in valid_bare:
            return

    # 不合法 → 自动修正为第一个可用的模型 (优先新 provider)
    first = next(iter(p.models for p in providers if p.models))[0]
    sys.stderr.write(f"warning: default_model {ref!r} no longer valid; resetting to {first!r}\n")
    existing["default_model"] = first
