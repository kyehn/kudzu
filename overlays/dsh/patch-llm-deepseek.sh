#!/usr/bin/env bash
# Patch @deepseek-ai/dsh-llm-deepseek to also export serializeRequest / parseSse /
# translate. The npm bundle keeps them module-private; the opencode-zen and
# nvidia-nim adapters reuse exactly these three functions so request-body
# building and SSE decoding are not re-implemented anywhere.
#
# Usage: patch-llm-deepseek.sh <path-to-package-dir>
set -euo pipefail

target="$1"
lib="$target/lib/index.js"
types="$target/lib/types/index.d.ts"

# 1) Append a second export statement to lib/index.js (ESM allows several).
if ! grep -q '^export { .*serializeRequest' "$lib"; then
  printf '\nexport { serializeRequest, parseSse, translate };\n' >>"$lib"
fi

# 2) The type-level re-exports (NodeNext suffix imports, matching the file's style).
if ! grep -q '^export { serializeRequest }' "$types"; then
  cat >>"$types" <<'EOF'

export { serializeRequest } from './serialize.ts';
export { parseSse } from './sse.ts';
export { translate } from './translate.ts';
EOF
fi
