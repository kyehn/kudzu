#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3 python3Packages.httpx python3Packages.tomli-w
"""Configure maki models through custom providers only (never the builtins).

Variant of overlays/reasonix/reasonix-config.py: identical discovery (the
official /models list intersected with models.dev, keeping only
non-deprecated text models with tool calls and zero input/output cost) and
the same npm split (responses/chat/anthropic), but it writes custom
providers.toml tables instead of touching any builtin flow:

- ``zen-chat`` (protocol ``openai``) and ``zen-responses`` (protocol
  ``openai-responses``) both point at the zen gateway with the public
  fallback key, each carrying its own capture-pinned User-Agent plus
  ``x-opencode-client: cli``. Per-request ``x-opencode-request``,
  per-session ``x-opencode-session`` and the TLS cipher pin come from
  overlays/maki/fix.patch (base-URL gated, builtin files untouched).
- ``nvidia`` (protocol ``openai``) points at the models.dev nvidia endpoint
  with its own key env var and no zen identity headers.

Free models are also written as declared ``[[<slug>.models]]`` entries
(context window, output cap, thinking/vision flags, zero prices), so the
picker works even before the first ``discover_models`` refresh. Existing
unrelated tables in providers.toml are preserved; the three managed tables
are replaced wholesale, making reruns idempotent.
"""

from __future__ import annotations

import argparse
import tomllib
from itertools import starmap
from pathlib import Path
from typing import Any

import httpx
import tomli_w

USER_AGENT = "opencode/latest/1.18.31/cli"
# Per-endpoint CLI identity from overlays/reasonix/opencode/ captures.
USER_AGENT_CHAT = "opencode/1.18.31 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14"
USER_AGENT_RESPONSES = (
    "opencode/1.18.31 ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14"
)
MAKI_PROVIDERS = Path.home() / ".config" / "maki" / "providers.toml"
PROVIDER_NAMES = ("opencode", "nvidia")
REQUEST_TIMEOUT = 30.0
# First choice when present (known-good free reasoning model); otherwise the
# first id in sorted order. Deterministic either way.
PREFERRED_DEFAULT = "muse-spark-1.3-contributor-free"
# Literal public fallback documented upstream for zen free models (not a
# secret); custom slugs have no free-tier quirk, so it is inlined.
ZEN_PUBLIC_KEY = "public"


def _free_models(
    entry: dict[str, Any], official_model_ids: list[str]
) -> list[tuple[str, dict[str, Any]]]:
    free: list[tuple[str, dict[str, Any]]] = []
    for model_id in official_model_ids:
        model = entry["models"].get(model_id)
        if model is None or model.get("status") == "deprecated":
            continue
        output_modalities = (model.get("modalities") or {}).get("output") or []
        if output_modalities and "text" not in output_modalities:
            continue
        if model.get("tool_call") is False:
            continue
        cost = model.get("cost")
        if not (
            isinstance(cost, dict)
            and cost.get("input") == 0
            and cost.get("output") == 0
        ):
            continue
        free.append((model_id, model))
    return free


def _split_zen(
    models: list[tuple[str, dict[str, Any]]],
) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]:
    responses: list[tuple[str, dict[str, Any]]] = []
    chat: list[tuple[str, dict[str, Any]]] = []
    for model_id, model in models:
        npm = (model.get("provider") or {}).get("npm")
        if npm == "@ai-sdk/anthropic":
            continue
        if npm == "@ai-sdk/openai":
            responses.append((model_id, model))
        else:
            chat.append((model_id, model))
    return responses, chat


def _model_entry(model_id: str, model: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": model_id}
    limit = model.get("limit") or {}
    if limit.get("context"):
        entry["context_window"] = limit["context"]
    if limit.get("output"):
        entry["max_output_tokens"] = limit["output"]
    if model.get("reasoning"):
        entry["supports_thinking"] = True
    input_modalities = (model.get("modalities") or {}).get("input", [])
    if model.get("attachment") or "image" in (input_modalities or []):
        entry["supports_vision"] = True
    entry["pricing_input"] = 0.0
    entry["pricing_output"] = 0.0
    return entry


def _default(models: list[tuple[str, dict[str, Any]]]) -> str | None:
    ids = [model_id for model_id, _ in models]
    if PREFERRED_DEFAULT in ids:
        return PREFERRED_DEFAULT
    return ids[0] if ids else None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Configure maki custom zen/nvidia providers.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=list(PROVIDER_NAMES),
        default=None,
        help="provider to configure (models.dev provider id); repeat for multiple",
    )
    args = parser.parse_args(argv)
    providers = args.provider or list(PROVIDER_NAMES)
    response = httpx.get(
        "https://models.dev/api.json",
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    models_dev_data = response.json()
    tables: dict[str, dict[str, Any]] = {}
    for provider in providers:
        entry = models_dev_data[provider]
        response = httpx.get(
            f"{entry['api'].rstrip('/')}/models",
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        official_model_ids = sorted(model["id"] for model in response.json()["data"])
        if provider == "opencode":
            responses, chat = _split_zen(_free_models(entry, official_model_ids))
            base_url = entry["api"]
            for slug, kind, user_agent, models in (
                ("zen-chat", "openai", USER_AGENT_CHAT, chat),
                (
                    "zen-responses",
                    "openai-responses",
                    USER_AGENT_RESPONSES,
                    responses,
                ),
            ):
                default = _default(models)
                table: dict[str, Any] = {
                    "display_name": f"Zen {kind}",
                    "protocol": kind,
                    "base_url": base_url,
                    "api_key": ZEN_PUBLIC_KEY,
                    "discover_models": True,
                    "headers": {
                        "User-Agent": user_agent,
                        "x-opencode-client": "cli",
                    },
                    "models": list(starmap(_model_entry, models)),
                }
                if default is not None:
                    table["default_model"] = default
                tables[slug] = table
        else:
            base_url = entry["api"]
            free = _free_models(entry, official_model_ids)
            default = free[0][0] if free else None
            table = {
                "display_name": "NVIDIA",
                "protocol": "openai",
                "base_url": base_url,
                "api_key_env": entry["env"][0],
                "discover_models": True,
                "models": list(starmap(_model_entry, free)),
            }
            if default is not None:
                table["default_model"] = default
            tables[provider] = table
    existing_raw = (
        tomllib.loads(MAKI_PROVIDERS.read_text(encoding="utf-8"))
        if MAKI_PROVIDERS.exists()
        else {}
    )
    existing = existing_raw if isinstance(existing_raw, dict) else {}
    for slug, table in tables.items():
        existing[slug] = table
    MAKI_PROVIDERS.parent.mkdir(parents=True, exist_ok=True)
    MAKI_PROVIDERS.write_text(tomli_w.dumps(existing), encoding="utf-8")
    for slug, table in tables.items():
        print(
            f"Wrote [{slug}] ({table['protocol']}) to {MAKI_PROVIDERS}: "
            f"{len(table['models'])} models, "
            f"default {table.get('default_model')}"
        )


if __name__ == "__main__":
    main()
