"""Build and maintain dsh configuration from OpenCode Zen and models.dev.

Mirrors the original reasonix-config builder (fetch -> filter -> write config ->
ensure public key -> validate) with dsh's own configuration format: the model
catalog itself stays dynamic (the dsh-llm-opencode-zen and dsh-llm-nvidia-nim
plugins resolve it at runtime), so this tool owns the parts a Python tool can
own: the zen default model selection, the home-layer patch (provider plugins +
unrestricted sandbox + never-asking approval), the ``OPENCODE_API_KEY=public``
credential, and a doctor-style validation via ``dsh --dump-config``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from dsh_config.fetcher import fetch_models_dev, fetch_zen_models

CONFIG_VERSION = 5
MIN_CHAT_CONTEXT = 8000
OPENCODE_ZEN_PROVIDER = "opencode-zen"
NVIDIA_NIM_PROVIDER = "nvidia-nim"
DEFAULT_MODEL = "deepseek-v4-flash-free"
ZEN_API_KEY_ENV = "OPENCODE_API_KEY"
ZEN_API_KEY_VALUE = "public"

# 与 overlays/dsh/dsh-home/cordis.patch.yml 保留一致: 插件注册 + zen 默认模型
# + danger-full-access/never (reasonix 的 sandbox off + permissions allow),
# 及原版 reasonix-config.nix 的 mcp 服务器段由 overlays/dsh-config.nix 提供.
HOME_PATCH_TEMPLATE = """\
# Default user layer, maintained by dsh-config. It activates both provider
# plugins and reproduces the reasonix-config execution stance: unrestricted
# sandbox (danger-full-access) with never-asking approval, plus the zen
# default model selection.
- insert:
    - id: llm-opencode-zen
      name: '@deepseek-ai/dsh-llm-opencode-zen'
    - id: llm-nvidia-nim
      name: '@deepseek-ai/dsh-llm-nvidia-nim'

- id: agent-default-model
  config:
    provider: opencode-zen
    model: {model}

- id: sandbox-policy
  config:
    mode: danger-full-access
    workspaceRoot: !!js process.cwd()

- id: approval
  config:
    policy: never
"""

SKIP_PATTERNS = [
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


def get_free_zen_model_ids(zen_data: dict) -> set[str]:
    """Free OpenCode Zen models: ids ending in ``-free`` plus ``big-pickle``."""
    ids: set[str] = set()
    for m in zen_data.get("data", []):
        mid = m["id"]
        if "-free" in mid or mid == "big-pickle":
            ids.add(mid)
    return ids


def _lookup_model(models_raw: dict[str, Any], model_id: str) -> tuple[str, dict[str, Any]] | None:
    result = models_raw.get(model_id)
    if result is not None:
        return model_id, result
    normalised = model_id.replace(".", "_")
    result = models_raw.get(normalised)
    if result is not None:
        return normalised, result
    return None


def _is_chat_model(mid: str, mdata: dict[str, Any]) -> bool:
    ctx = mdata.get("limit", {}).get("context", 0)
    if ctx < MIN_CHAT_CONTEXT:
        return False
    name_lower = mid.lower()
    return all(pat not in name_lower for pat in SKIP_PATTERNS)


def available_models() -> dict[str, list[str]]:
    """Sorted chat/free model ids per provider, filtering deprecated entries out."""
    zen_data = fetch_zen_models()
    md_data = fetch_models_dev()

    free_ids = get_free_zen_model_ids(zen_data)
    oc_models_raw = md_data.get("opencode", {}).get("models", {})
    zen_models: list[str] = []
    for mid in sorted(free_ids):
        lookup = _lookup_model(oc_models_raw, mid)
        if lookup is not None:
            _, m = lookup
            if m.get("status", "") == "deprecated":
                continue
        zen_models.append(mid)

    nv_models_raw = md_data.get("nvidia", {}).get("models", {})
    nvidia_models = [
        mid
        for mid, m in sorted(nv_models_raw.items())
        if m.get("status", "") != "deprecated" and _is_chat_model(mid, m)
    ]

    if not zen_models:
        msg = "No free OpenCode Zen models found"
        raise SystemExit(msg)

    return {OPENCODE_ZEN_PROVIDER: zen_models, NVIDIA_NIM_PROVIDER: nvidia_models}


def resolve_default_model(zen_models: list[str], current: str | None) -> str:
    """Keep a valid current default; otherwise pick ``deepseek-v4-flash-free``
    when it is free, else the first free model (mirrors the original
    ``_repair_default_model`` behaviour)."""
    if current in zen_models:
        return current
    if DEFAULT_MODEL in zen_models:
        return DEFAULT_MODEL
    return zen_models[0]


def dsh_home() -> Path:
    return Path(os.environ.get("DSH_HOME", Path.home() / ".dsh"))


def ensure_home_patch(zen_models: list[str], current_model: str | None) -> Path:
    """Write the default home patch or refresh just its default model line.

    The file may contain dsh ``!!js`` expressions, so updates are line-based
    and never parse the YAML: user rows outside ``agent-default-model`` are
    preserved untouched.
    """
    patch = dsh_home() / "cordis.patch.yml"
    model = resolve_default_model(zen_models, current_model)

    if not patch.exists():
        patch.parent.mkdir(parents=True, exist_ok=True)
        patch.write_text(HOME_PATCH_TEMPLATE.format(model=model))
        patch.chmod(0o600)
        return patch

    lines = patch.read_text().splitlines()
    section = False
    replaced = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "- id: agent-default-model":
            section = True
            continue
        if section:
            if not stripped.startswith("model:"):
                continue
            lines[idx] = f"    model: {model}"
            replaced = True
            break
    if not replaced:
        lines.extend(
            [
                "",
                "- id: agent-default-model",
                "  config:",
                f"    provider: {OPENCODE_ZEN_PROVIDER}",
                f"    model: {model}",
            ]
        )
    patch.write_text("\n".join(lines) + "\n")
    patch.chmod(0o600)
    return patch


def _load_credentials() -> dict[str, Any]:
    path = dsh_home() / ".credentials.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def ensure_opencode_public_key() -> None:
    """Ensure ``OPENCODE_API_KEY: public`` in ``$DSH_HOME/.credentials.yaml``."""
    creds = _load_credentials()
    creds[ZEN_API_KEY_ENV] = ZEN_API_KEY_VALUE
    path = dsh_home() / ".credentials.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(creds, sort_keys=False))
    path.chmod(0o600)


def run_dsh_doctor() -> None:
    """Validate the dsh composition by dumping the headless profile tree."""
    doctor = shutil.which("dsh")
    if doctor is None:
        sys.stderr.write("warning: 'dsh' not found on PATH; skipping doctor validation\n")
        return
    try:
        result = subprocess.run(  # noqa: S603 — resolved by shutil.which()
            [doctor, "--profile", "headless", "--dump-config"],
            timeout=120,
            check=False,
            capture_output=True,
        )
    except subprocess.TimeoutExpired:
        msg = "'dsh --dump-config' timed out after 120s"
        raise SystemExit(msg) from None
    except OSError as exc:
        msg = f"failed to run 'dsh --dump-config': {exc}"
        raise SystemExit(msg) from None
    if result.returncode != 0:
        msg = f"'dsh --dump-config' exited with code {result.returncode}"
        if result.stderr:
            msg += f"\n{result.stderr.decode(errors='replace').strip()}"
        raise SystemExit(msg)


def build_all(providers_filter: list[str] | None = None) -> dict[str, list[str]]:
    models = available_models()
    if providers_filter is not None:
        models = {k: v for k, v in models.items() if k in providers_filter}
    return models


def write_config(models: dict[str, list[str]]) -> Path:
    """Refresh the home-layer patch and credentials, then validate via doctor.

    Reads the current default model from the existing patch (line-based), then
    writes or repairs it. Returns the path that was written.
    """
    zen_models = models.get(OPENCODE_ZEN_PROVIDER, [])
    current = read_current_default_model()
    patch = ensure_home_patch(zen_models, current)
    ensure_opencode_public_key()
    run_dsh_doctor()
    return patch


def read_current_default_model() -> str | None:
    patch = dsh_home() / "cordis.patch.yml"
    if not patch.exists():
        return None
    section = False
    for line in patch.read_text().splitlines():
        stripped = line.strip()
        if stripped == "- id: agent-default-model":
            section = True
            continue
        if section:
            if stripped.startswith("model:"):
                return stripped.split(":", 1)[1].strip()
            if stripped.startswith(("- ", "#")):
                section = False
    return None
