from __future__ import annotations

import argparse
import sys

from dsh_config.builder import build_all, write_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync OpenCode Zen free and NVIDIA NIM models to dsh (DeepSeek Harness) settings.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=["opencode-zen", "nvidia-nim"],
        default=None,
        help="provider to configure; repeat for multiple (default: all)",
    )
    parser.add_argument(
        "--dsh-home",
        default=None,
        help="DSH home directory (default: $DSH_HOME or ~/.dsh)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    providers = build_all(providers_filter=args.provider)
    paths = write_config(providers, dsh_home=args.dsh_home)
    sys.stdout.write(f"Written {len(providers)} provider(s) to {paths.settings}\n")
    for p in providers:
        sys.stdout.write(
            f"  {p.name}: {len(p.models)} models, kind={p.kind}, base_url={p.base_url}\n"
        )
        if p.default:
            sys.stdout.write(f"    default: {p.default}\n")


if __name__ == "__main__":
    main()
