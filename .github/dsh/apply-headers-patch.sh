#!/usr/bin/env bash
# Applies headers.patch to an installed deepseekharness-acp-interactive tree.
# Usage: ./apply-headers-patch.sh [npm-root]  (default: npm root -g)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${1:-$(npm root -g)}"
PKG="$ROOT/deepseekharness-acp-interactive/node_modules/@deepseek-ai/dsh-llm-pi-ai"
TARGET="$PKG/lib/index.js"
MARK="a deployment header wins a case-insensitive collision"

if [[ ! -f "$TARGET" ]]; then
	echo "not found: $TARGET" >&2
	exit 1
fi
if grep -q "$MARK" "$TARGET"; then
	echo "already applied: $TARGET"
	exit 0
fi
patch -p0 -d "$PKG" < "$SCRIPT_DIR/headers.patch"
node -e "import('$TARGET').then(() => console.log('import ok: $TARGET'))"
