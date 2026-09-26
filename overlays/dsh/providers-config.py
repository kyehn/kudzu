#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3 python3Packages.httpx python3Packages.pyyaml
"""Generate the dsh llm-pi-ai providers patch from models.dev + official listings.

Reads no local state except an existing patch file it merges into. Writes a
Cordis bundle patch (``- id: llm-pi-ai``) whose ``config.providers`` dict is
the whole model surface: route per upstream provider id, models filtered to
the free tier with tool calls and text output, capacities defaulted from the
installed pi-ai catalog entry of the same id.

Wire identity (opencode ``User-Agent`` pins, ``x-opencode-*`` ids) is NOT part
of this file: ``User-Agent`` is owned by the harness attribution layer and a
static ``x-opencode-request``/``x-opencode-session`` would be a hardcoded id.
The live algorithm lives in ``wire-identity.py`` next to this script;
``--print-wire-identity`` executes it once for inspection.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

OPENCODE_VERSION = "1.18.32"
BUN_VERSION = "1.3.14"
# Static CLI constants (same values pi-opencode stamps). Per-request ids and
# the per-endpoint User-Agent are NOT here: the former would be hardcoded ids,
# the latter is owned by the harness attribution layer. See README.md.
WIRE_HEADERS = {
    "x-opencode-client": "cli",
    "x-opencode-project": "global",
}
PROVIDER_UTILS = {
    "openai-completions": "4.0.23",
    "openai-responses": "4.0.40",
    "anthropic-messages": "4.0.46",
}
USER_AGENT_BY_API = {
    api: f"opencode/{OPENCODE_VERSION} ai-sdk/provider-utils/{utils} runtime/bun/{BUN_VERSION}"
    for api, utils in PROVIDER_UTILS.items()
}
USER_AGENT = next(iter(USER_AGENT_BY_API.values()))
PROVIDER_NAMES = ("opencode", "nvidia")
API_KEY_ENV = {"opencode": "OPENCODE_API_KEY", "nvidia": "NVIDIA_API_KEY"}
DEFAULT_PATCH = Path.home() / ".dsh" / "profiles" / "kudzu" / "providers.patch.yml"


def is_free_text_tool_model(entry: dict[str, Any], model_id: str) -> bool:
    model = entry["models"].get(model_id)
    if model is None or model.get("status") == "deprecated":
        return False
    output_modalities = (model.get("modalities") or {}).get("output") or []
    if output_modalities and "text" not in output_modalities:
        return False
    if model.get("tool_call") is False:
        return False
    cost = model.get("cost")
    return isinstance(cost, dict) and cost.get("input") == 0 and cost.get("output") == 0


def reasoning_efforts(model: dict[str, Any]) -> dict[str, str | None] | None:
    if not model.get("reasoning"):
        return None
    for option in model.get("reasoning_options") or []:
        if isinstance(option, dict) and option.get("type") == "effort":
            values = [
                "none" if value is None else value
                for value in (option.get("values") or [])
            ]
            if values:
                return {
                    ("off" if value == "none" else value): (
                        None if value == "none" else value
                    )
                    for value in values
                }
    return {"max": "max"}


def model_entry(model_id: str, model: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": model_id}
    limit = model.get("limit") or {}
    if limit.get("context"):
        entry["contextWindow"] = limit["context"]
    if limit.get("output"):
        entry["maxTokens"] = limit["output"]
    input_modalities = (model.get("modalities") or {}).get("input", [])
    if model.get("attachment") or "image" in (input_modalities or []):
        entry["input"] = ["text", "image"]
    efforts = reasoning_efforts(model)
    if efforts is not None:
        entry["reasoningEfforts"] = efforts
    return entry


def fetch_models(client: httpx.Client, provider: str) -> dict[str, Any]:
    models_dev = client.get(
        "https://models.dev/api.json", headers={"User-Agent": USER_AGENT}
    )
    models_dev.raise_for_status()
    data = models_dev.json()
    entry = data[provider]
    response = client.get(
        f"{entry['api'].rstrip('/')}/models", headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    official_ids = sorted(model["id"] for model in response.json()["data"])
    models = [
        model_entry(model_id, entry["models"][model_id])
        for model_id in official_ids
        if is_free_text_tool_model(entry, model_id)
    ]
    if not models:
        msg = f"dsh providers: provider {provider!r} projects to no free model"
        raise ValueError(msg)
    return {
        "displayName": f"{provider} free tier",
        "apiKeyEnv": API_KEY_ENV[provider],
        "headers": dict(WIRE_HEADERS),
        "models": models,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate dsh llm-pi-ai providers patch"
    )
    parser.add_argument(
        "--provider", action="append", choices=list(PROVIDER_NAMES), default=None
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--print-wire-identity", action="store_true")
    args = parser.parse_args(argv)
    if args.print_wire_identity:
        spec = importlib.util.spec_from_file_location(
            "wire_identity", Path(__file__).with_name("wire-identity.py")
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(module.wire_identity("openai-completions", module.new_session_id()))
        return
    providers = args.provider or list(PROVIDER_NAMES)
    with httpx.Client(timeout=30.0) as client:
        configs = {name: fetch_models(client, name) for name in providers}
    patch = [{"id": "llm-pi-ai", "config": {"providers": configs}}]
    out = args.out or Path(os.environ.get("DSH_PROVIDERS_PATCH", str(DEFAULT_PATCH)))
    if out.exists():
        existing = yaml.safe_load(out.read_text(encoding="utf-8")) or []
        rows = [row for row in existing if row.get("id") != "llm-pi-ai"]
        rows.extend(patch)
    else:
        rows = patch
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(configs)} provider(s) to {out}")
    for name, config in configs.items():
        print(f"  {name}: {len(config['models'])} models")


if __name__ == "__main__":
    main()
