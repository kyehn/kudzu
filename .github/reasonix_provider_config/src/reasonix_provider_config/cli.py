"""CLI tool to compare opencode vs reasonix HTTP requests."""

from __future__ import annotations

import json
import sys
from reasonix_provider_config.mapping import diff_http_requests


def main() -> None:
    result = diff_http_requests()

    print("=" * 72)
    print("  OpenCode vs Reasonix HTTP Request 比较")
    print("=" * 72)

    print("\n📌 唯一 detectable 的差异:\n")
    for diff in result["differences"]:
        print(f"  字段:    {diff['field']}")
        print(f"  opencode:  {diff['opencode']}")
        print(f"  reasonix:  {diff['reasonix']}")
        print(f"  影响:    {diff['impact']}")
        print(f"  可通过配置修复: {'❌ 否' if not diff['fixable_in_config'] else '✅ 是'}")
        print(f"  修复方案: {diff['fix']}")
        print()

    print("\n📊 统计:")
    print(f"  ✅ 完全一致:    {result['match_count']}")
    print(f"  ⚠️ 运行时差异:  {result['gap_count']}")
    print(f"  ⚠️ 配置不可调:  {len([d for d in result['differences'] if not d['fixable_in_config']])}")
    print()

    if "--json" in sys.argv:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        print()


if __name__ == "__main__":
    main()
