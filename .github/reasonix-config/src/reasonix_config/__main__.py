from __future__ import annotations

import argparse
import sys

from reasonix_config.builder import build_all, write_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync OpenCode Zen free and NVIDIA NIM models to reasonix config.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=["opencode", "nvidia"],
        default=None,
        help="provider to configure (models.dev provider id); repeat for multiple (default: all)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    providers = build_all(providers_filter=args.provider)
    path = write_config(providers)
    sys.stdout.write(f"Written {len(providers)} provider(s) to {path}\n")
    for p in providers:
        sys.stdout.write(
            f"  {p.name}: {len(p.models)} models, kind={p.kind}, base_url={p.base_url}\n"
        )
        if p.default:
            sys.stdout.write(f"    default: {p.default}\n")


if __name__ == "__main__":
    main()
