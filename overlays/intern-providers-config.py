#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3 python3Packages.httpx python3Packages.tomli-w python3Packages.pyyaml
from __future__ import annotations

import argparse
import os
import tomllib
from pathlib import Path
from typing import Any

import httpx
import tomli_w
import yaml

API_KEY_ENV = "TOKENPLAN_API_KEY"
MODELS_DEV_URL = "https://models.dev/models.json?type=all"
INTERN_MODELS_URL = "https://discovery-api.intern-ai.org.cn/v1/models"
BASE_URL = INTERN_MODELS_URL.removesuffix("/models")

MAKI_PROVIDERS = Path.home() / ".config" / "maki" / "providers.toml"
REASONIX_CONFIG = Path.home() / ".reasonix" / "config.toml"
DSH_PATCH = Path.home() / ".dsh" / "cordis.patch.yml"

PROVIDER_NAME = "intern-ai"


def find_models_dev_entry(
    model_id: str, models_dev: dict[str, Any]
) -> dict[str, Any] | None:
    target = model_id.lower()

    def norm(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    for key, model in models_dev.items():
        mid = str(model.get("id", key)).lower()
        if mid == target or mid.split("/")[-1] == target:
            return model
    normalized_target = norm(target)
    for key, model in models_dev.items():
        mid = str(model.get("id", key))
        name = str(model.get("name", ""))
        if norm(mid) == normalized_target or norm(name) == normalized_target:
            return model
    return None


def fetch_models_dev() -> dict[str, Any]:
    response = httpx.get(MODELS_DEV_URL, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def fetch_intern_models() -> list[dict[str, Any]]:
    api_key = os.getenv(API_KEY_ENV, "")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = httpx.get(INTERN_MODELS_URL, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    candidates = data.get("data") or data.get("models") or []
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id") or entry.get("name")
        if not model_id:
            continue
        if entry.get("status", "active") != "active":
            continue
        key = str(model_id).lower()
        if key in seen:
            continue
        seen.add(key)
        models.append(entry)
    return models


def intern_model_meta(entry: dict[str, Any]) -> dict[str, Any]:
    context = None
    input_modalities: list[str] = []
    for modality in entry.get("input_modalities") or []:
        modality_type = str(modality.get("type") or "")
        if modality_type in {"text", "image"}:
            input_modalities.append(modality_type)
        max_context = (
            (modality.get("supported_inputs") or {}).get("max_context_length") or {}
        ).get("value")
        if max_context:
            context = max(context or 0, max_context)
    output = None
    tool_call = False
    for modality in entry.get("output_modalities") or []:
        max_length = (modality.get("max_length") or {}).get("value")
        if max_length:
            output = max(output or 0, max_length)
        if (modality.get("supported_parameters") or {}).get("tools"):
            tool_call = True
    return {
        "context": context,
        "output": output,
        "input": input_modalities,
        "tool_call": tool_call,
    }


def build_models() -> list[tuple[str, dict[str, Any]]]:
    models_dev = fetch_models_dev()
    intern_models = fetch_intern_models()
    models: list[tuple[str, dict[str, Any]]] = []
    for entry in intern_models:
        model_id = str(entry.get("id") or entry.get("name"))
        meta = intern_model_meta(entry)
        model = find_models_dev_entry(model_id, models_dev)
        if model:
            limit = model.get("limit") or {}
            modalities = model.get("modalities") or {}
            context = limit.get("context") or meta["context"]
            output = limit.get("output") or meta["output"]
            input_modalities = list(modalities.get("input") or meta["input"])
            reasoning = bool(model.get("reasoning"))
            attachment = bool(model.get("attachment")) or "image" in input_modalities
            tool_call = model.get("tool_call", True)
        else:
            context = meta["context"]
            output = meta["output"]
            input_modalities = meta["input"]
            reasoning = False
            attachment = "image" in input_modalities
            tool_call = meta["tool_call"]
        models.append((
            model_id,
            {
                "limit": {"context": context, "output": output},
                "modalities": {
                    "input": input_modalities,
                    "output": ["text"],
                },
                "reasoning": reasoning,
                "attachment": attachment,
                "tool_call": tool_call,
                "provider": {"api": BASE_URL},
            },
        ))
    return models


def configure_maki(models: list[tuple[str, dict[str, Any]]], api_key: str) -> None:
    model_configs = []
    for model_id, model in models:
        model_limit = model.get("limit") or {}
        model_config: dict[str, Any] = {"id": model_id}
        if model_limit.get("context"):
            model_config["context_window"] = model_limit["context"]
        if model_limit.get("output"):
            model_config["max_output_tokens"] = model_limit["output"]
        if model.get("reasoning"):
            model_config["supports_thinking"] = True
            model_config["requires_thinking"] = True
        input_modalities = (model.get("modalities") or {}).get("input") or []
        if model.get("attachment") or "image" in input_modalities:
            model_config["supports_vision"] = True
        model_configs.append(model_config)
    new_providers: dict[str, dict[str, Any]] = {
        PROVIDER_NAME: {
            "display_name": PROVIDER_NAME,
            "protocol": "openai",
            "base_url": BASE_URL,
            "api_key": api_key,
            "discover_models": False,
            "models": model_configs,
            "default_model": models[0][0],
        }
    }
    existing_raw = (
        tomllib.loads(MAKI_PROVIDERS.read_text(encoding="utf-8"))
        if MAKI_PROVIDERS.exists()
        else {}
    )
    existing = existing_raw if isinstance(existing_raw, dict) else {}
    existing.pop(PROVIDER_NAME, None)
    for provider_name, provider_config in new_providers.items():
        existing[provider_name] = provider_config
    MAKI_PROVIDERS.parent.mkdir(parents=True, exist_ok=True)
    MAKI_PROVIDERS.write_text(
        tomli_w.dumps(existing),
        encoding="utf-8",
    )
    print(f"Wrote {len(new_providers)} provider(s) to {MAKI_PROVIDERS}")
    for provider_name, provider_config in new_providers.items():
        print(
            f"  {provider_name}: "
            f"{len(provider_config['models'])} models, "
            f"default {provider_config['default_model']}"
        )


def configure_reasonix(models: list[tuple[str, dict[str, Any]]]) -> None:
    provider_config: dict[str, Any] = {
        "name": PROVIDER_NAME,
        "kind": "openai",
        "base_url": BASE_URL,
        "models": [model_id for model_id, _ in models],
        "default": models[0][0],
        "api_key_env": API_KEY_ENV,
        "context_window": max(
            (model.get("limit", {}).get("context", 0) for _, model in models),
            default=0,
        ),
    }
    overrides = {}
    for model_id, model in models:
        model_limit = model.get("limit") or {}
        model_override: dict[str, Any] = {}
        if model_limit.get("context"):
            model_override["context_window"] = model_limit["context"]
        if model_limit.get("output"):
            model_override["max_output_tokens"] = model_limit["output"]
        if model.get("reasoning"):
            model_override["reasoning_protocol"] = "openai"
        input_modalities = (model.get("modalities") or {}).get("input", [])
        if model.get("attachment") or "image" in (input_modalities or []):
            model_override["vision"] = True
        if model_override:
            overrides[model_id] = model_override
    if overrides:
        provider_config["model_overrides"] = overrides
    new_providers = [provider_config]
    with REASONIX_CONFIG.open("rb") as config_file:
        existing = tomllib.load(config_file)
    new_names = {provider["name"] for provider in new_providers}
    existing["providers"] = [
        provider
        for provider in existing.get("providers", [])
        if provider.get("name") not in new_names
    ]
    existing["providers"].extend(new_providers)
    REASONIX_CONFIG.write_text(tomli_w.dumps(existing))
    print(f"Wrote {len(new_providers)} provider(s) to {REASONIX_CONFIG}")
    for provider in new_providers:
        print(
            f"  {provider['name']}: "
            f"{len(provider['models'])} models, "
            f"default {provider['default']}"
        )


def configure_dsh(models: list[tuple[str, dict[str, Any]]]) -> None:
    model_configs = []
    for model_id, model in models:
        model_limit = model.get("limit") or {}
        model_config: dict[str, Any] = {"id": model_id}
        if model_limit.get("context"):
            model_config["contextWindow"] = model_limit["context"]
        if model_limit.get("output"):
            model_config["maxTokens"] = model_limit["output"]
        input_modalities = (model.get("modalities") or {}).get("input") or []
        model_config["input"] = (
            ["text", "image"]
            if model.get("attachment") or "image" in input_modalities
            else ["text"]
        )
        if model.get("reasoning"):
            model_config["reasoningEfforts"] = {"low": "low", "high": "high"}
        model_configs.append(model_config)
    new_providers: dict[str, dict[str, Any]] = {
        PROVIDER_NAME: {
            "displayName": PROVIDER_NAME,
            "api": "openai-completions",
            "baseURL": BASE_URL,
            "retryPolicy": {"mode": "normal", "maxRetries": 9},
            "models": model_configs,
            "apiKeyEnv": API_KEY_ENV,
        }
    }
    patch_raw = (
        yaml.safe_load(DSH_PATCH.read_text(encoding="utf-8"))
        if DSH_PATCH.exists()
        else []
    )
    patch = patch_raw if isinstance(patch_raw, list) else []
    entry = next(
        (
            item
            for item in patch
            if isinstance(item, dict) and item.get("id") == "llm-pi-ai"
        ),
        None,
    )
    if entry is None:
        entry = {"id": "llm-pi-ai", "config": {}}
        patch.append(entry)
    providers_section = entry.setdefault("config", {}).setdefault("providers", {})
    for provider_name, provider_config in new_providers.items():
        providers_section[provider_name] = provider_config
    DSH_PATCH.parent.mkdir(parents=True, exist_ok=True)
    DSH_PATCH.write_text(
        yaml.safe_dump(patch, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(new_providers)} provider(s) to {DSH_PATCH}")
    for provider_name, provider_config in new_providers.items():
        print(
            f"  {provider_name}: "
            f"{len(provider_config['models'])} models, "
            f"first {provider_config['models'][0]['id']}"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Configure intern-ai providers for maki/reasonix/dsh",
    )
    parser.add_argument(
        "--target",
        choices=["maki", "reasonix", "dsh", "all"],
        default="all",
        help="which tool to configure",
    )
    args = parser.parse_args(argv)
    api_key = os.getenv(API_KEY_ENV, "")
    models = build_models()
    if not models:
        raise SystemExit("no models found")
    if args.target in {"maki", "all"}:
        configure_maki(models, api_key)
    if args.target in {"reasonix", "all"}:
        configure_reasonix(models)
    if args.target in {"dsh", "all"}:
        configure_dsh(models)


if __name__ == "__main__":
    main()
