#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3 python3Packages.httpx python3Packages.pyyaml
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import httpx
import yaml

OPENCODE_VERSION = "1.18.32"
BUN_VERSION = "1.3.14"
USER_AGENTS = {
    api: (
        f"opencode/{OPENCODE_VERSION} ai-sdk/provider-utils/{utils} "
        f"runtime/bun/{BUN_VERSION}"
    )
    for api, utils in (
        ("openai-completions", "4.0.23"),
        ("openai-responses", "4.0.40"),
        ("anthropic-messages", "4.0.46"),
    )
}
USER_AGENT = USER_AGENTS["openai-completions"]
THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
DSH_PATCH = Path.home() / ".dsh" / "cordis.patch.yml"
PROVIDER_NAMES = ("opencode", "nvidia")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Configure providers for dsh",
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
        "https://models.dev/api.json", headers={"User-Agent": USER_AGENT}, timeout=30
    )
    response.raise_for_status()
    models_dev_data = response.json()
    new_providers: dict[str, dict[str, Any]] = {}
    for provider in providers:
        entry = models_dev_data[provider]
        response = httpx.get(
            f"{entry['api'].rstrip('/')}/models",
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        official_model_ids = sorted(model["id"] for model in response.json()["data"])
        models = {
            "openai": [],
            "openai-responses": [],
            "anthropic": [],
        }
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
            package_name = (model.get("provider") or {}).get("npm")
            if package_name == "@ai-sdk/anthropic":
                models["anthropic"].append((model_id, model))
            elif package_name == "@ai-sdk/openai":
                models["openai-responses"].append((model_id, model))
            else:
                models["openai"].append((model_id, model))
        protocols = (
            ("openai-completions", "openai"),
            ("openai-responses", "openai-responses"),
            ("anthropic-messages", "anthropic"),
        )
        for protocol, bucket in protocols:
            provider_models = models[bucket]
            if not provider_models:
                continue
            model_configs = []
            for model_id, model in provider_models:
                model_config: dict[str, Any] = {"id": model_id}
                model_limit = model.get("limit") or {}
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
                    for option in model.get("reasoning_options") or []:
                        if isinstance(option, dict) and option.get("type") == "effort":
                            effort_values = [
                                "none" if value is None else value
                                for value in (option.get("values") or [])
                            ]
                            if effort_values:
                                model_config["reasoningEfforts"] = {
                                    ("off" if value == "none" else value): value
                                    for value in effort_values
                                }
                model_configs.append(model_config)
            common_levels: set[str] | None = None
            for model_config in model_configs:
                levels = set((model_config.get("reasoningEfforts") or {}).keys())
                common_levels = (
                    levels if common_levels is None else common_levels & levels
                )
            default_reasoning = None
            if common_levels:
                for level in reversed(THINKING_LEVELS):
                    if level != "off" and level in common_levels:
                        default_reasoning = level
                        break
            route_key = f"{provider}-{bucket}"
            provider_config: dict[str, Any] = {
                "displayName": f"{provider} {protocol}",
                "api": protocol,
                "baseURL": entry["api"],
                "apiKeyEnv": entry["env"][0],
                "retryPolicy": {
                    "mode": "normal",
                    "maxRetries": 9,
                },
                "models": model_configs,
            }
            if default_reasoning is not None:
                provider_config["reasoning"] = default_reasoning
            if provider == "opencode":
                provider_config["headers"] = {
                    "User-Agent": USER_AGENTS[protocol],
                    "x-opencode-client": "cli",
                    "x-opencode-project": "global",
                }
            new_providers[route_key] = provider_config
    if not new_providers:
        raise SystemExit("no models found")
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


if __name__ == "__main__":
    main()
