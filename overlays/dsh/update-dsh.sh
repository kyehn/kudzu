#!/usr/bin/env bash
# 将 overlays/dsh 升级到 npm 上最新的 @deepseek-ai/dsh 版本。
#
# 用法：./overlays/dsh/update-dsh.sh
# 依赖：curl tar npm nix nix-prefetch-url；prefetch-npm-deps
#       （通过 nix shell nixpkgs#nodePackages.prefetch-npm-deps 自动获取）。
# 脚本只更新 default.nix 与 package-lock.json 两个文件，请先确认工作区
# 干净（已 commit），跑完 `git diff` 审阅后再 `nix build .#dsh` 验证。
set -euo pipefail

dsh_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
default_nix="$dsh_dir/default.nix"

current="$(sed -n 's/^  version = "\([^"]*\)";$/\1/p' "$default_nix" | head -1)"
latest="$(npm view @deepseek-ai/dsh version 2>/dev/null || true)"

if [[ -z "$latest" ]]; then
  echo "错误：无法获取 npm 最新版本（npm view 失败）" >&2
  exit 1
fi

if [[ "$current" == "$latest" ]]; then
  echo "已是最新：$current"
  exit 0
fi

echo "发现新版本：$current -> $latest"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

tgz="$tmp/dsh-$latest.tgz"
curl -fsSL "https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-$latest.tgz" -o "$tgz"
tar -xzf "$tgz" -C "$tmp"

(
  cd "$tmp/package"
  npm install --package-lock-only --ignore-scripts >/dev/null
)

src_hash="$(nix-prefetch-url --unpack "https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-$latest.tgz")"
npm_hash="$(nix shell nixpkgs#nodePackages.prefetch-npm-deps -c prefetch-npm-deps "$tmp/package/package-lock.json")"

python3 - "$default_nix" "$current" "$latest" "$src_hash" "$npm_hash" <<'PY'
import re
import sys

path, cur, new, src_hash, npm_hash = sys.argv[1:]
s = open(path, encoding="utf-8").read()
s = s.replace(f'version = "{cur}"', f'version = "{new}"')
# 仅替换 fetchzip 块内的 src hash 行
s = re.sub(
    r'(url = "https://registry\.npmjs\.org/@deepseek-ai/dsh/-/dsh-\$\{version\}\.tgz";\n    hash = ")[^"]*(";)',
    rf"\g<1>{src_hash}\g<2>",
    s,
)
s = re.sub(r'(npmDepsHash = ")[^"]*(";)', rf"\g<1>{npm_hash}\g<2>", s)
open(path, "w", encoding="utf-8").write(s)
PY

cp "$tmp/package/package-lock.json" "$dsh_dir/package-lock.json"

echo "已更新：default.nix（$current -> $latest）与 package-lock.json"
echo "下一步：git diff 审阅 → nix build .#dsh → nix run .#dsh -- --version → commit"