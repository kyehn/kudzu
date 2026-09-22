#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3 python3Packages.httpx python3Packages.tomli-w
from __future__ import annotations

import argparse
import os
import tomllib
from pathlib import Path
from typing import Any

import httpx
import tomli_w

USER_AGENT = "opencode/1.18.31 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14"
MAKI_PROVIDERS = Path.home() / ".config" / "maki" / "providers.toml"
PROVIDER_NAMES = ("opencode", "nvidia")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Configure providers for maki",
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
        "https://models.dev/api.json", headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    models_dev_data = response.json()
    new_providers: dict[str, dict[str, Any]] = {}
    for provider in providers:
        entry = models_dev_data[provider]
        response = httpx.get(
            f"{entry['api'].rstrip('/')}/models", headers={"User-Agent": USER_AGENT}
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
        for protocol, provider_models in models.items():
            if not provider_models:
                continue
            model_configs = []
            for model_id, model in provider_models:
                model_config: dict[str, Any] = {"id": model_id}
                model_limit = model.get("limit") or {}
                if model_limit.get("context"):
                    model_config["context_window"] = model_limit["context"]
                if model_limit.get("output"):
                    model_config["max_output_tokens"] = model_limit["output"]
                if model.get("reasoning"):
                    model_config["supports_thinking"] = True
                    model_config["requires_thinking"] = True
                    for option in model.get("reasoning_options") or []:
                        if isinstance(option, dict) and option.get("type") == "effort":
                            effort_values = [
                                "none" if value is None else value
                                for value in (option.get("values") or [])
                            ]
                            if effort_values:
                                model_config["requires_thinking"] = (
                                    "none" not in effort_values
                                )
                                non_none_values = [
                                    value for value in effort_values if value != "none"
                                ]
                                if not model_config.get("thinking_fields"):
                                    model_config["thinking_fields"] = {}
                                if "none" in effort_values:
                                    model_config["thinking_fields"]["off"] = {
                                        "reasoning_effort": "none",
                                        "chat_template_kwargs": {
                                            "enable_thinking": False
                                        },
                                    }
                                if non_none_values:
                                    model_config["thinking_fields"]["adaptive"] = {
                                        "reasoning_effort": non_none_values[-1]
                                    }
                                    for value in non_none_values:
                                        model_config["thinking_fields"][value] = {
                                            "reasoning_effort": value
                                        }
                input_modalities = (model.get("modalities") or {}).get("input", [])
                if model.get("attachment") or "image" in input_modalities:
                    model_config["supports_vision"] = True
                model_config["pricing_input"] = 0.0
                model_config["pricing_output"] = 0.0
                model_configs.append(model_config)
            provider_config = {
                "display_name": f"{provider} {protocol}",
                "protocol": protocol,
                "base_url": entry["api"],
                "api_key": "public" if provider == "opencode" else None,
                "discover_models": False,
                "models": model_configs,
                "default_model": provider_models[0][0],
            }
            if provider == "opencode":
                if protocol == "openai-responses":
                    provider_config["headers"] = {
                        "User-Agent": "opencode/1.18.31 ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14",
                        "x-opencode-client": "cli",
                    }
                else:
                    provider_config["headers"] = {
                        "User-Agent": USER_AGENT,
                        "x-opencode-client": "cli",
                    }
            else:
                provider_config["api_key"] = os.getenv(entry["env"][0])
            new_providers[f"{provider}-{protocol}"] = provider_config
    existing_raw = (
        tomllib.loads(MAKI_PROVIDERS.read_text(encoding="utf-8"))
        if MAKI_PROVIDERS.exists()
        else {}
    )
    existing = existing_raw if isinstance(existing_raw, dict) else {}
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


if __name__ == "__main__":
    main()
