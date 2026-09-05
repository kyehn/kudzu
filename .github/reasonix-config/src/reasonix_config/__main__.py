from __future__ import annotations

import argparse
import os
import sys

from reasonix_config.builder import (
    PROVIDER_NAMES,
    _fetch_official_list,
    _provider_entry,
    build_all,
    build_nvidia,
    ensure_env_placeholder,
    write_config,
)
from reasonix_config.fetcher import fetch_models_dev, probe_nvidia_live


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Zen free and NVIDIA NIM models to reasonix config.",
    )
    parser.add_argument(
        "--provider",
        action="append",
        choices=list(PROVIDER_NAMES),
        default=None,
        help="provider to configure (models.dev provider id); repeat for multiple (default: all)",
    )
    parser.add_argument(
        "--live-check",
        action="append",
        choices=["nvidia"],
        default=[],
        help="probe provider models against the live API and drop definite-404s "
        "(repeatable; ambiguous results are always kept)",
    )
    return parser.parse_args(argv)


def _nvidia_dead_live(md_data: dict, entry: dict) -> set[str]:
    """--live-check nvidia 的探活名单: fail-open.

    无 key (entry env[0]) 或探活本身抛错时返回空集 (保留全部候选, 仅警告),
    探活只能证伪 (404), 不能证真. 候选取自去除 dead 前的完整构建
    (官方名单 ∩ models.dev), base_url 派生自 provider 条目.
    """
    env_name = entry["env"][0]
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        sys.stderr.write(f"warning: --live-check nvidia without {env_name}; skipping probe\n")
        return set()
    try:
        official = _fetch_official_list(entry, "nvidia")
        api_url = f"{entry['api'].rstrip('/')}/models"
        candidates = build_nvidia("nvidia", md_data, official, api_url, set()).models
        dead = probe_nvidia_live(candidates, api_key, entry["api"])
    except (Exception, SystemExit) as exc:
        # 探活阶段出错只能保留全部候选, 不能中断生成.
        sys.stderr.write(f"warning: nvidia live probe failed ({exc}); keeping all candidates\n")
        return set()
    if dead:
        sys.stderr.write(f"live probe dropped {len(dead)} nvidia model(s): {sorted(dead)}\n")
    return dead


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    # build_all 默认不探活 (测试 hermetic); 探活名单经 dead 显式注入.
    md_data = fetch_models_dev()
    dead = None
    if "nvidia" in args.live_check:
        dead = {"nvidia": _nvidia_dead_live(md_data, _provider_entry(md_data, "nvidia"))}
    providers, errors = build_all(providers_filter=args.provider, dead=dead, md_data=md_data)
    if providers:
        path = write_config(providers)
        # zen 匿名凭据占位: 键名从 opencode provider env[0] 派生 (值见
        # ZEN_ANONYMOUS_CREDENTIAL); nvidia 永不写占位 (缺 key 即 fail-closed 在前).
        if args.provider is None or "opencode" in args.provider:
            for p in providers:
                if p.name == "opencode" and p.api_key_env:
                    ensure_env_placeholder(p.api_key_env)
        sys.stdout.write(f"Written {len(providers)} provider(s) to {path}\n")
        for p in providers:
            sys.stdout.write(
                f"  {p.name}: {len(p.models)} models, kind={p.kind}, base_url={p.base_url}\n"
            )
            if p.default:
                sys.stdout.write(f"    default: {p.default}\n")
    if errors:
        # 成功部分已写入; 有 provider 失败必须非零退出 (CI 可见),
        # 但不回滚成功部分 (隔离语义, 见 build_all).
        for err in errors:
            sys.stderr.write(f"error: {err}\n")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
