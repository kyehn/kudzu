#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3 python3Packages.httpx python3Packages.tomli-w
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from typing import Any

import httpx
import tomli_w

USER_AGENT = "opencode/beta/0.0.0-beta-19151/cli"
REASONIX_CONFIG = Path.home() / ".reasonix" / "config.toml"
# models.dev cost 单位为美元 (USD)
BILLING_CURRENCY = "USD"
# models.dev provider.npm == 此值 → Responses wire, 否则 chat completions
RESPONSES_SDK_PACKAGE = "@ai-sdk/openai"

PROVIDER_NAMES = ("opencode", "nvidia")


def _provider_dict(
    name: str,
    kind: str,
    entry: dict[str, Any],
    models: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    provider_config: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "base_url": entry["api"],
        "models": [model_id for model_id, _ in models],
        "default": models[0][0],
        "api_key_env": entry["env"][0],
        "context_window": max(
            model.get("limit", {}).get("context", 0) for _, model in models
        ),
    }
    if kind == "responses":
        provider_config["responses_mode"] = "stateless"
    provider_config["billing_currency"] = BILLING_CURRENCY
    prices = {}
    overrides = {}
    for model_id, model in models:
        cost = model.get("cost") or {}
        model_price: dict[str, Any] = {
            "input": cost.get("input", 0),
            "output": cost.get("output", 0),
        }
        if cost.get("cache_read"):
            model_price["cache_hit"] = cost["cache_read"]
        model_price["currency"] = BILLING_CURRENCY
        if (
            model_price["input"]
            or model_price["output"]
            or model_price.get("cache_hit")
        ):
            prices[model_id] = model_price
        model_limit = model.get("limit") or {}
        model_override: dict[str, Any] = {}
        if model_limit.get("context"):
            model_override["context_window"] = model_limit["context"]
        if model_limit.get("output"):
            model_override["max_output_tokens"] = model_limit["output"]
        if model.get("reasoning"):
            model_override["reasoning_protocol"] = "openai"
            for option in model.get("reasoning_options", []):
                if isinstance(option, dict) and option.get("type") == "effort":
                    effort_values = [
                        "none" if value is None else value
                        for value in option.get("values", [])
                    ]
                    if effort_values:
                        model_override["supported_efforts"] = effort_values
                        non_none_values = [
                            value for value in effort_values if value != "none"
                        ]
                        model_override["default_effort"] = (
                            non_none_values[-1]
                            if non_none_values
                            else effort_values[-1]
                        )
                        break
        input_modalities = (model.get("modalities") or {}).get("input", [])
        if model.get("attachment") or "image" in (input_modalities or []):
            model_override["vision"] = True
        if model_override:
            overrides[model_id] = model_override
    if prices:
        provider_config["prices"] = prices
    if overrides:
        provider_config["model_overrides"] = overrides
    return provider_config


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Set models to reasonix config.",
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
    new_providers: list[dict[str, Any]] = []
    for provider in providers:
        entry = models_dev_data[provider]
        response = httpx.get(
            f"{entry['api'].rstrip('/')}/models", headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()
        official_model_ids = sorted(model["id"] for model in response.json()["data"])
        chat = []
        responses = []
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
            npm = (model.get("provider") or {}).get("npm")
            if npm == RESPONSES_SDK_PACKAGE:
                responses.append((model_id, model))
            else:
                chat.append((model_id, model))
        if chat:
            new_providers.append(_provider_dict(provider, "openai", entry, chat))
        if responses:
            new_providers.append(
                _provider_dict(
                    f"{provider}-responses",
                    "responses",
                    entry,
                    responses,
                )
            )
    with REASONIX_CONFIG.open("rb") as config_file:
        existing = tomllib.load(config_file)
    new_names = {provider_config["name"] for provider_config in new_providers}
    existing["providers"] = [
        provider_config
        for provider_config in existing.get("providers", [])
        if provider_config.get("name") not in new_names
    ]
    existing["providers"].extend(new_providers)
    REASONIX_CONFIG.write_text(tomli_w.dumps(existing))
    print(f"Wrote {len(new_providers)} provider(s) to {REASONIX_CONFIG}")
    for provider_config in new_providers:
        print(
            f"  {provider_config['name']}: "
            f"{len(provider_config['models'])} models, "
            f"default {provider_config['default']}"
        )


if __name__ == "__main__":
    main()
