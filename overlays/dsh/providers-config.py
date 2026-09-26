#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3 python3Packages.httpx python3Packages.pyyaml
"""Generate the dsh opencode-wire providers patch from models.dev.

Same shape as overlays/maki/providers-config.py: models.dev plus the
provider's official /models listing, free tier with tool calls and text
output only, split into protocol buckets by the model's npm provider
(@ai-sdk/anthropic, @ai-sdk/openai, everything else). Each bucket becomes one
harness route `<provider>-<protocol>` so the request path carries the pi-ai
api the gateway expects.

Wire identity is NOT part of this file: headers are computed per request by
the opencode-wire bundle at stream time. The live algorithm's executable
reference is wire-identity.py; --print-wire-identity executes it once.
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
USER_AGENT = (
    f"opencode/{OPENCODE_VERSION} ai-sdk/provider-utils/4.0.23 "
    f"runtime/bun/{BUN_VERSION}"
)
# The profile user layer: dsh reads exactly one cordis.patch.yml per profile,
# so the generated routes merge into the nix-written file, not a sibling.
DSH_PROVIDERS = Path.home() / ".dsh" / "profiles" / "default" / "cordis.patch.yml"
PROVIDER_NAMES = ("opencode", "nvidia")
# models.dev protocol bucket -> the pi-ai api the route dispatches with.
PROTOCOL_API = {
    "openai": "openai-completions",
    "openai-responses": "openai-responses",
    "anthropic": "anthropic-messages",
}


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
        print(module.wire_identity("openai", module.new_session_id()))
        return
    providers = args.provider or list(PROVIDER_NAMES)
    response = httpx.get(
        "https://models.dev/api.json", headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    models_dev_data = response.json()
    new_providers: dict[str, dict[str, Any]] = {}
    with httpx.Client(timeout=30.0) as client:
        for provider in providers:
            entry = models_dev_data[provider]
            response = client.get(
                f"{entry['api'].rstrip('/')}/models",
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            official_model_ids = sorted(
                model["id"] for model in response.json()["data"]
            )
            models: dict[str, list[tuple[str, dict[str, Any]]]] = {
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
                        model_config["contextWindow"] = model_limit["context"]
                    if model_limit.get("output"):
                        model_config["maxTokens"] = model_limit["output"]
                    if model.get("reasoning"):
                        # Every effort models.dev declares, none dropped: `none`
                        # becomes the harness `off` (the only level allowed to
                        # carry no wire value), the rest pass through by name.
                        for option in model.get("reasoning_options") or []:
                            if (
                                isinstance(option, dict)
                                and option.get("type") == "effort"
                            ):
                                effort_values = [
                                    "none" if value is None else value
                                    for value in (option.get("values") or [])
                                ]
                                if effort_values:
                                    model_config["reasoningEfforts"] = {
                                        ("off" if value == "none" else value): (
                                            None if value == "none" else value
                                        )
                                        for value in effort_values
                                    }
                    input_modalities = (model.get("modalities") or {}).get("input", [])
                    if model.get("attachment") or "image" in input_modalities:
                        model_config["input"] = ["text", "image"]
                    model_configs.append(model_config)
                route = f"{provider}-{protocol}"
                new_providers[route] = {
                    "api": PROTOCOL_API[protocol],
                    "baseURL": entry["api"],
                    "apiKeyEnv": entry["env"][0],
                    "retryPolicy": {"mode": "normal", "maxRetries": 12},
                    "models": model_configs,
                }
    if not new_providers:
        msg = f"dsh providers: providers {providers!r} project to no free model"
        raise ValueError(msg)
    patch = [{"id": "opencode-wire", "config": {"providers": new_providers}}]
    out = args.out or Path(os.environ.get("DSH_PROVIDERS_PATCH", str(DSH_PROVIDERS)))
    existing_raw = (
        yaml.safe_load(out.read_text(encoding="utf-8")) if out.exists() else []
    )
    existing = existing_raw if isinstance(existing_raw, list) else []
    rows = [row for row in existing if row.get("id") != "opencode-wire"]
    rows.extend(patch)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(new_providers)} provider(s) to {out}")
    for route, route_config in new_providers.items():
        print(f"  {route}: {len(route_config['models'])} models")


if __name__ == "__main__":
    main()
