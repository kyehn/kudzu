"""CLI entry point for dsh-config."""

from __future__ import annotations

import argparse
import sys

from dsh_config.builder import (
    OPENCODE_ZEN_PROVIDER,
    build_all,
    read_current_default_model,
    resolve_default_model,
    write_config,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync NVIDIA NIM and OpenCode Zen free models to dsh config.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=[OPENCODE_ZEN_PROVIDER, "nvidia-nim"],
        default=None,
        help="provider to configure; repeat for multiple (default: all)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    models = build_all(providers_filter=args.provider)
    path = write_config(models)
    zen_models = models.get(OPENCODE_ZEN_PROVIDER, [])
    default = resolve_default_model(zen_models, read_current_default_model())
    sys.stdout.write(f"Written {sum(len(v) for v in models.values())} model(s) to {path}\n")
    for name, ids in models.items():
        default = default if name == OPENCODE_ZEN_PROVIDER else (ids[0] if ids else "-")
        sys.stdout.write(f"  {name}: {len(ids)} models, default={default}\n")


if __name__ == "__main__":
    main()
