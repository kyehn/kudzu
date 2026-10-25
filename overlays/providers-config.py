#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3 python3Packages.httpx python3Packages.tomli-w python3Packages.pyyaml
from __future__ import annotations

import argparse
import os
import tomllib
from itertools import starmap
from pathlib import Path
from typing import Any

import httpx
import tomli_w
import yaml

MODELS_DEV_URL = "https://models.dev/api.json"
MAKI_PROVIDERS = Path.home() / ".config" / "maki" / "providers.toml"
REASONIX_CONFIG = Path.home() / ".reasonix" / "config.toml"
DSH_PATCH = Path.home() / ".dsh" / "cordis.patch.yml"
HARNESSES = ("maki", "reasonix", "dsh")
PROVIDER_NAMES = ("nvidia", "kilo")
NO_AUTH_PROVIDERS = {"kilo"}
BILLING_CURRENCY = "USD"
PROTOCOLS = {
    "openai": {
        "maki": "openai",
        "reasonix": "openai",
        "dsh": "openai-completions",
    },
    "responses": {
        "maki": "openai-responses",
        "reasonix": "responses",
        "dsh": "openai-responses",
    },
    "anthropic": {
        "maki": "anthropic",
        "reasonix": "anthropic",
        "dsh": "anthropic-messages",
    },
}

Route = tuple[str, str, str, str, list[tuple[str, dict[str, Any]]]]
Routes = dict[str, list[Route]]


def api_type(package_name: str | None) -> str:
    if package_name == "@ai-sdk/anthropic":
        return "anthropic"
    if package_name == "@ai-sdk/openai":
        return "responses"
    return "openai"


def belongs_to_provider(name: str, providers: list[str]) -> bool:
    return any(
        name == provider or name.startswith(f"{provider}-") for provider in providers
    )


def model_metadata(model: dict[str, Any]) -> dict[str, Any]:
    limit = model.get("limit") or {}
    input_modalities = (model.get("modalities") or {}).get("input") or []
    efforts: list[str] = []
    if model.get("reasoning"):
        for option in model.get("reasoning_options") or []:
            if isinstance(option, dict) and option.get("type") == "effort":
                efforts = [
                    "none" if value is None else value
                    for value in (option.get("values") or [])
                ]
                break
    return {
        "context_window": limit.get("context"),
        "max_output_tokens": limit.get("output"),
        "vision": bool(model.get("attachment")) or "image" in input_modalities,
        "reasoning": bool(model.get("reasoning")),
        "efforts": efforts,
    }


def build_routes(provider: str, entry: dict[str, Any]) -> list[Route]:
    response = httpx.get(f"{entry['api'].rstrip('/')}/models", timeout=30)
    response.raise_for_status()
    official_model_ids = sorted(model["id"] for model in response.json()["data"])
    models: dict[str, list[tuple[str, dict[str, Any]]]] = {
        "openai": [],
        "responses": [],
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
        models[api_type((model.get("provider") or {}).get("npm"))].append((
            model_id,
            model,
        ))
    default_type = api_type(entry.get("npm"))
    routes = []
    for kind, provider_models in models.items():
        if not provider_models:
            continue
        routes.append((
            provider if kind == default_type else f"{provider}-{kind}",
            kind,
            (provider_models[0][1].get("provider") or {}).get("api") or entry["api"],
            entry["env"][0],
            provider_models,
        ))
    return routes


def maki_model_config(model_id: str, model: dict[str, Any]) -> dict[str, Any]:
    metadata = model_metadata(model)
    model_config: dict[str, Any] = {"id": model_id}
    if metadata["context_window"]:
        model_config["context_window"] = metadata["context_window"]
    if metadata["max_output_tokens"]:
        model_config["max_output_tokens"] = metadata["max_output_tokens"]
    if metadata["reasoning"]:
        model_config["supports_thinking"] = True
        model_config["requires_thinking"] = True
        efforts = metadata["efforts"]
        if efforts:
            model_config["requires_thinking"] = "none" not in efforts
            non_none_efforts = [effort for effort in efforts if effort != "none"]
            thinking_fields = {}
            if "none" in efforts:
                thinking_fields["off"] = {
                    "reasoning_effort": "none",
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            if non_none_efforts:
                thinking_fields["adaptive"] = {"reasoning_effort": non_none_efforts[-1]}
                for effort in non_none_efforts:
                    thinking_fields[effort] = {"reasoning_effort": effort}
            if thinking_fields:
                model_config["thinking_fields"] = thinking_fields
    if metadata["vision"]:
        model_config["supports_vision"] = True
    model_config["pricing_input"] = 0.0
    model_config["pricing_output"] = 0.0
    return model_config


def configure_maki(routes: Routes) -> None:
    new_providers: dict[str, dict[str, Any]] = {}
    for provider, provider_routes in routes.items():
        for name, kind, base_url, api_key_env, provider_models in provider_routes:
            new_providers[name] = {
                "display_name": f"{provider} {PROTOCOLS[kind]['maki']}",
                "protocol": PROTOCOLS[kind]["maki"],
                "base_url": base_url,
                "api_key": (
                    "" if provider in NO_AUTH_PROVIDERS else os.getenv(api_key_env, "")
                ),
                "discover_models": False,
                "models": list(starmap(maki_model_config, provider_models)),
                "default_model": provider_models[0][0],
            }
    existing_raw = (
        tomllib.loads(MAKI_PROVIDERS.read_text(encoding="utf-8"))
        if MAKI_PROVIDERS.exists()
        else {}
    )
    existing = existing_raw if isinstance(existing_raw, dict) else {}
    for name in list(existing):
        if belongs_to_provider(name, list(routes)):
            del existing[name]
    existing.update(new_providers)
    MAKI_PROVIDERS.parent.mkdir(parents=True, exist_ok=True)
    MAKI_PROVIDERS.write_text(tomli_w.dumps(existing), encoding="utf-8")
    print(f"Wrote {len(new_providers)} provider(s) to {MAKI_PROVIDERS}")
    for name, provider_config in new_providers.items():
        print(
            f"  {name}: "
            f"{len(provider_config['models'])} models, "
            f"default {provider_config['default_model']}"
        )


def reasonix_provider_config(route: Route, provider: str) -> dict[str, Any]:
    name, kind, base_url, api_key_env, provider_models = route
    provider_config: dict[str, Any] = {
        "name": name,
        "kind": PROTOCOLS[kind]["reasonix"],
        "base_url": base_url,
        "models": [model_id for model_id, _ in provider_models],
        "default": provider_models[0][0],
        "api_key_env": "" if provider in NO_AUTH_PROVIDERS else api_key_env,
        "context_window": max(
            model_metadata(model)["context_window"] or 0 for _, model in provider_models
        ),
        "billing_currency": BILLING_CURRENCY,
    }
    if kind == "responses":
        provider_config["responses_mode"] = "stateless"
    prices = {}
    overrides = {}
    for model_id, model in provider_models:
        metadata = model_metadata(model)
        cost = model.get("cost") or {}
        model_price: dict[str, Any] = {
            "input": cost.get("input", 0),
            "output": cost.get("output", 0),
            "currency": BILLING_CURRENCY,
        }
        if cost.get("cache_read"):
            model_price["cache_hit"] = cost["cache_read"]
        if (
            model_price["input"]
            or model_price["output"]
            or model_price.get("cache_hit")
        ):
            prices[model_id] = model_price
        model_override: dict[str, Any] = {}
        if metadata["context_window"]:
            model_override["context_window"] = metadata["context_window"]
        if metadata["max_output_tokens"]:
            model_override["max_output_tokens"] = metadata["max_output_tokens"]
        if metadata["reasoning"]:
            model_override["reasoning_protocol"] = "openai"
            efforts = metadata["efforts"]
            if efforts:
                model_override["supported_efforts"] = efforts
                non_none_efforts = [effort for effort in efforts if effort != "none"]
                model_override["default_effort"] = (
                    non_none_efforts[-1] if non_none_efforts else efforts[-1]
                )
        if metadata["vision"]:
            model_override["vision"] = True
        if model_override:
            overrides[model_id] = model_override
    if prices:
        provider_config["prices"] = prices
    if overrides:
        provider_config["model_overrides"] = overrides
    return provider_config


def configure_reasonix(routes: Routes) -> None:
    new_providers = [
        reasonix_provider_config(route, provider)
        for provider, provider_routes in routes.items()
        for route in provider_routes
    ]
    with REASONIX_CONFIG.open("rb") as config_file:
        existing = tomllib.load(config_file)
    existing["providers"] = [
        provider_config
        for provider_config in existing.get("providers", [])
        if not belongs_to_provider(provider_config.get("name", ""), list(routes))
    ]
    existing["providers"].extend(new_providers)
    REASONIX_CONFIG.write_text(tomli_w.dumps(existing), encoding="utf-8")
    print(f"Wrote {len(new_providers)} provider(s) to {REASONIX_CONFIG}")
    for provider_config in new_providers:
        print(
            f"  {provider_config['name']}: "
            f"{len(provider_config['models'])} models, "
            f"default {provider_config['default']}"
        )


def configure_dsh(routes: Routes) -> None:
    new_providers: dict[str, dict[str, Any]] = {}
    for provider, provider_routes in routes.items():
        for name, kind, base_url, api_key_env, provider_models in provider_routes:
            model_configs = []
            for model_id, model in provider_models:
                metadata = model_metadata(model)
                model_config: dict[str, Any] = {"id": model_id}
                if metadata["context_window"]:
                    model_config["contextWindow"] = metadata["context_window"]
                if metadata["max_output_tokens"]:
                    model_config["maxTokens"] = metadata["max_output_tokens"]
                model_config["input"] = (
                    ["text", "image"] if metadata["vision"] else ["text"]
                )
                if metadata["reasoning"] and metadata["efforts"]:
                    model_config["reasoningEfforts"] = {
                        ("off" if effort == "none" else effort): effort
                        for effort in metadata["efforts"]
                    }
                model_configs.append(model_config)
            provider_config: dict[str, Any] = {
                "displayName": f"{provider} {PROTOCOLS[kind]['dsh']}",
                "api": PROTOCOLS[kind]["dsh"],
                "baseURL": base_url,
                "retryPolicy": {
                    "mode": "normal",
                    "maxRetries": 9,
                },
                "models": model_configs,
            }
            if provider in NO_AUTH_PROVIDERS:
                provider_config["headers"] = {"Authorization": "Bearer "}
            else:
                provider_config["apiKeyEnv"] = api_key_env
            new_providers[name] = provider_config
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
    for name in list(providers_section):
        if belongs_to_provider(name, list(routes)):
            del providers_section[name]
    providers_section.update(new_providers)
    DSH_PATCH.parent.mkdir(parents=True, exist_ok=True)
    DSH_PATCH.write_text(
        yaml.safe_dump(patch, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(new_providers)} provider(s) to {DSH_PATCH}")
    for name, provider_config in new_providers.items():
        print(
            f"  {name}: "
            f"{len(provider_config['models'])} models, "
            f"first {provider_config['models'][0]['id']}"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Configure model providers for coding agents",
    )
    parser.add_argument(
        "--harness",
        action="append",
        choices=list(HARNESSES),
        default=None,
        help="harness to configure; repeat for multiple",
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
    response = httpx.get(MODELS_DEV_URL, timeout=30)
    response.raise_for_status()
    models_dev_data = response.json()
    routes = {
        provider: build_routes(provider, models_dev_data[provider])
        for provider in providers
    }
    for harness in args.harness or list(HARNESSES):
        if harness == "maki":
            configure_maki(routes)
        elif harness == "reasonix":
            configure_reasonix(routes)
        else:
            configure_dsh(routes)


if __name__ == "__main__":
    main()
