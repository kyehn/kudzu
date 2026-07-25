"""Entry point for reasonix-provider-config.

Orchestrates: fetch model lists from OpenCode Zen and NVIDIA NIM,
cross-reference with models.dev/api.json, build provider config entries
(only for models present in BOTH sources), and update
~/.reasonix/config.toml.

CLI usage::

    reasonix-provider-config                          # sync ALL providers (default)
    reasonix-provider-config --provider opencode-zen  # only OpenCode Zen free
    reasonix-provider-config --provider nvidia-nim    # only NVIDIA NIM
    reasonix-provider-config --provider opencode-zen nvidia-nim  # explicit both
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from reasonix_provider_config.api import (
    fetch_models_dev,
    fetch_nvidia_models,
    fetch_zen_models,
)
from reasonix_provider_config.config import CONFIG_PATH, read_config, write_config
from reasonix_provider_config.models import ModelsDevModel, Pricing, ReasonixProvider
from reasonix_provider_config.mapping import print_mapping

# Provider metadata
ZEN_BASE_URL = "https://opencode.ai/zen/v1"
ZEN_API_KEY_ENV = ""  # OpenCode Zen does not require an API key

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_API_KEY_ENV = "NVIDIA_API_KEY"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Subcommands::

        reasonix-provider-config sync                           # sync providers (default)
        reasonix-provider-config sync --provider opencode-zen   # OpenCode Zen only
        reasonix-provider-config mapping                        # show mapping table
        reasonix-provider-config generate-config                # generate ProviderEntry TOML
    """
    parser = argparse.ArgumentParser(
        prog="reasonix-provider-config",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Sync provider list
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync model providers from OpenCode Zen and/or NVIDIA NIM to ~/.reasonix/config.toml",
    )
    sync_parser.add_argument(
        "--provider",
        nargs="*",
        choices=["opencode-zen", "nvidia-nim"],
        default=None,
        help=(
            "Provider(s) to sync. Can be specified multiple times: "
            "'--provider opencode-zen nvidia-nim'. "
            "Omit (default) to sync both."
        ),
    )

    # Show mapping
    mapping_parser = subparsers.add_parser(
        "mapping",
        aliases=["show-mapping"],
        help="Show OpenCode-to-ReasonIX field mapping table",
    )
    mapping_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of YAML",
    )

    # Generate config
    gen_parser = subparsers.add_parser(
        "generate-config",
        aliases=["gen"],
        help="Generate a ProviderEntry TOML configuration block",
    )
    gen_parser.add_argument("--name", default="my-provider", help="Provider name")
    gen_parser.add_argument("--base-url", default="https://api.example.com/v1", help="API base URL")
    gen_parser.add_argument("--model", default="my-model", help="Default model name")
    gen_parser.add_argument("--api-key-env", default="API_KEY", help="API key env var name")
    gen_parser.add_argument("--context-window", type=int, default=128000, help="Context window size")
    gen_parser.add_argument("--max-output", type=int, default=4096, help="Max output tokens")
    gen_parser.add_argument("--vision", action="store_true", help="Enable vision support")

    return parser.parse_args(argv)


def _is_zen_free_model(model_id: str) -> bool:
    """Check whether *model_id* ends with ``-free``."""
    return model_id.endswith("-free")


def _provider_name(model_id: str) -> str:
    """Build a unique provider name from a model ID.
    Replaces ``/`` with ``_`` to make it TOML-key-friendly.
    Only models with ``/`` get modified (e.g. deepseek-ai/deepseek-v4-flash
    becomes ``deepseek-ai_deepseek-v4-flash``). Models without ``/`` like
    ``deepseek-v4-flash-free`` pass through unchanged.
    """
    safe_id = model_id.replace("/", "_")
    return f"{safe_id}"


def _lookup_model(models_dev_data: dict, model_id: str) -> ModelsDevModel | None:
    r"""Look up a model ID in models.dev data, trying normalized forms.

    NVIDIA NIM API returns model IDs with dots (e.g.
    ``abacusai/dracarys-llama-3.1-70b-instruct``) while models.dev often
    normalises them to underscores (``abacusai/dracarys-llama-3_1-70b-instruct``).
    Try exact match first, then with ``.``\ →\ ``_``.
    """
    info = models_dev_data.get(model_id)
    if info is not None:
        return info
    normalised = model_id.replace(".", "_")
    return models_dev_data.get(normalised)


def _validate_with_reasonix_doctor() -> None:
    """Validate ``~/.reasonix/config.toml`` by running ``reasonix doctor``.

    Uses ``reasonix doctor`` exit code as the truth — exits non-zero iff
    the config has real structural or semantic errors. Pre-existing
    ReasonIX-level non-fatal warnings (e.g. skill tool registry staleness)
    do not affect the exit code and are not treated as errors here.

    Fatally exits with code 1 if ``reasonix`` is unavailable, times out,
    or the config is invalid.
    """
    doctor = _find_reasonix()
    try:
        result = subprocess.run(  # noqa: S603 — resolved by trusted _find_reasonix()
            [doctor, "doctor"],
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write("Error: 'reasonix doctor' timed out\n")
        sys.exit(1)
    except OSError as exc:
        sys.stderr.write(f"Error: failed to run 'reasonix doctor': {exc}\n")
        sys.exit(1)

    if result.returncode != 0:
        sys.stderr.write(
            f"Error: 'reasonix doctor' exited with code {result.returncode}\n",
        )
        sys.exit(1)


def _find_reasonix() -> str:
    """Locate the ``reasonix`` binary.

    Returns the resolved full path.
    Exits with code 1 if not found.
    """
    resolved = shutil.which("reasonix")
    if resolved is not None:
        return resolved

    for candidate in (
        "/usr/local/bin/reasonix",
        "/usr/bin/reasonix",
        str(Path.home() / ".local" / "bin" / "reasonix"),
    ):
        p = Path(candidate)
        if p.is_file():
            return str(p.resolve())

    sys.stderr.write(
        "Error: 'reasonix' not found in PATH or standard locations\n",
    )
    sys.exit(1)


def _build_providers(  # noqa: C901, PLR0913
    model_ids: list[str],
    *,
    prefix: str,
    base_url: str,
    api_key_env: str,
    models_dev_data: dict,
    filter_free_only: bool = False,
) -> list[ReasonixProvider]:
    """Build ReasonixProvider entries from API model IDs enriched with models.dev.

    Only models that appear in BOTH the API model list AND models.dev data
    are included. Models from the API that lack a models.dev entry (and thus
    lack ``context_window``) are skipped — they are logged to stderr for
    transparency.

    Args:
        model_ids: List of model IDs from the API (authoritative).
        prefix: Prefix for provider names (e.g. "opencode", "nvidia").
        base_url: API base URL.
        api_key_env: Environment variable for API key.
        models_dev_data: The ``models`` dict from models.dev for enrichment.
        filter_free_only: If True, only include models with ``-free`` suffix.

    Returns:
        List of ReasonixProvider instances.

    """
    providers: list[ReasonixProvider] = []
    seen_names: set[str] = set()
    skipped: list[str] = []
    deprecated: list[str] = []

    for mid in model_ids:
        if filter_free_only and not _is_zen_free_model(mid):
            continue

        name = _provider_name(mid)
        if name in seen_names:
            continue
        seen_names.add(name)

        model_info = _lookup_model(models_dev_data, mid)
        if model_info is None or model_info.limit.context <= 0:
            skipped.append(mid)
            continue

        if model_info.status == "deprecated":
            deprecated.append(mid)
            continue

        price: Pricing | None = None
        if model_info.cost.input > 0 or model_info.cost.output > 0:
            price = Pricing(
                input=model_info.cost.input,
                output=model_info.cost.output,
                cache_hit=model_info.cost.cache_read,
            )

        # Detect vision capability from modalities
        vision = "image" in model_info.modalities.input

        # Extract supported_efforts from reasoning_options
        supported_efforts: list[str] | None = None
        for opt in model_info.reasoning_options:
            if opt.type == "effort" and opt.values:
                supported_efforts = opt.values
                break

        provider_kwargs: dict[str, Any] = dict(
            name=name,
            kind="openai",
            base_url=base_url,
            model=mid,
            api_key_env=api_key_env,
            context_window=model_info.limit.context,
            price=price,
            vision=vision,
            supported_efforts=supported_efforts,
        )

        # Add max_output when available
        if model_info.limit.output > 0:
            provider_kwargs["max_output"] = model_info.limit.output

        # opencode sends a clean standard OpenAI-compatible request with no
        # extra headers (no User-Agent, no custom headers). We mirror this
        # by not adding any extra headers here.

        provider = ReasonixProvider(**provider_kwargs)
        providers.append(provider)

    if skipped:
        sys.stderr.write(
            f"Warning: {len(skipped)} model(s) from '{prefix}' not in models.dev — skipped:\n",
        )
        for mid in sorted(skipped):
            sys.stderr.write(f"  {mid}\n")

    if deprecated:
        sys.stderr.write(
            f"Warning: {len(deprecated)} deprecated model(s) from '{prefix}' — skipped:\n",
        )
        for mid in sorted(deprecated):
            sys.stderr.write(f"  {mid} (deprecated)\n")

    return providers


def main(argv: list[str] | None = None) -> None:  # noqa: C901
    """Run the tool.

    Args:
        argv: CLI arguments. If ``None``, uses ``sys.argv[1:]``.

    Supports subcommands:
    - ``sync`` (default if omitted): sync providers
    - ``mapping`` / ``show-mapping``: show field mapping table
    - ``generate-config`` / ``gen``: generate ProviderEntry TOML

    """
    args = _parse_args(argv)

    # Handle subcommands
    if args.command in ("mapping", "show-mapping"):
        output = args.json and "json" or "yaml"
        print_mapping(output)
        return

    if args.command in ("generate-config", "gen"):
        from reasonix_provider_config.mapping import generate_toml

        toml = generate_toml(
            name=args.name,
            base_url=args.base_url,
            model=args.model,
            api_key_env=args.api_key_env,
            context_window=args.context_window,
            max_output=args.max_output,
            vision=args.vision,
        )
        print(toml)
        return
        return

    # Default: sync providers
    if args.command not in (None, "sync"):
        print(f"Error: unknown command '{args.command}'", file=sys.stderr)
        sys.exit(1)

    selected = args.provider  # None (both), ["opencode-zen"], ["nvidia-nim"], or both

    # Providers selected by user or default (both)
    use_zen = selected is None or "opencode-zen" in selected
    use_nvidia = selected is None or "nvidia-nim" in selected

    # Step 1: Fetch model lists from APIs
    zen_all: list[str] = []
    nvidia_all: list[str] = []

    if use_zen:
        zen_all = fetch_zen_models()
    if use_nvidia:
        nvidia_all = fetch_nvidia_models()

    # Step 2: Fetch models.dev data
    all_providers = fetch_models_dev()

    opencode_data: dict = {}
    nvidia_data: dict = {}

    if use_zen:
        if "opencode" not in all_providers:
            sys.stderr.write(
                "Error: 'opencode' provider not found in models.dev data\n",
            )
            sys.exit(1)
        opencode_data = all_providers["opencode"].models

    if use_nvidia:
        if "nvidia" not in all_providers:
            sys.stderr.write(
                "Error: 'nvidia' provider not found in models.dev data\n",
            )
            sys.exit(1)
        nvidia_data = all_providers["nvidia"].models

    # Step 3: Build provider entries
    zen_providers: list[ReasonixProvider] = []
    nvidia_providers: list[ReasonixProvider] = []

    if use_zen:
        zen_providers = _build_providers(
            zen_all,
            prefix="opencode",
            base_url=ZEN_BASE_URL,
            api_key_env=ZEN_API_KEY_ENV,
            models_dev_data=opencode_data,
            filter_free_only=True,
        )

    if use_nvidia:
        nvidia_providers = _build_providers(
            nvidia_all,
            prefix="nvidia",
            base_url=NVIDIA_BASE_URL,
            api_key_env=NVIDIA_API_KEY_ENV,
            models_dev_data=nvidia_data,
            filter_free_only=False,
        )

    all_new_providers = zen_providers + nvidia_providers

    if not all_new_providers:
        sys.stderr.write("Error: no models found to configure\n")
        sys.exit(1)

    # Step 4: Read existing config
    config = read_config()

    # Step 5: Replace providers
    config.providers = all_new_providers

    # Step 5b: Migrate model references if they no longer exist
    # Provider names may have changed (e.g. old "-" to new "_" for "/").
    available_names: set[str] = {p.name for p in all_new_providers}
    for ref_field in ("default_model", "planner_model", "subagent_model"):
        old_ref = getattr(config, ref_field, None)
        if not old_ref or old_ref in available_names:
            continue
        # Old naming used "-" for "/", new naming uses "_".
        # Try replacing "-" → "_" in the provider part only (before "/" if any).
        migrated: str | None = None
        if "/" in old_ref:
            prov, model = old_ref.rsplit("/", 1)
            migrated = f"{prov.replace('-', '_')}/{model}"
        else:
            migrated = old_ref.replace("-", "_")
        if migrated and migrated in available_names:
            sys.stderr.write(f"Info: {ref_field} migrated from {old_ref!r} to {migrated!r}\n")
            setattr(config, ref_field, migrated)
        else:
            first = sorted(available_names)[0]
            sys.stderr.write(f"Info: {ref_field} {old_ref!r} not found; reset to {first!r}\n")
            setattr(config, ref_field, first)

    # Step 6: Write back
    write_config(config)

    # Step 7: Validate with reasonix doctor
    _validate_with_reasonix_doctor()

    total = len(all_new_providers)
    parts: list[str] = []
    if use_zen:
        parts.append(f"{len(zen_providers)} OpenCode Zen free")
    if use_nvidia:
        parts.append(f"{len(nvidia_providers)} NVIDIA NIM")
    sys.stderr.write(
        f"Updated {CONFIG_PATH} with {total} provider(s) ({', '.join(parts)})\n",
    )


if __name__ == "__main__":
    main()
