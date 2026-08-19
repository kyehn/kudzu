#!/usr/bin/env bash
# Patch @deepseek-ai/dsh-llm-deepseek:
#  1) also export serializeRequest / parseSse / translate. The npm bundle keeps
#     them module-private; the opencode-zen and nvidia-nim adapters reuse
#     exactly these three functions so request-body building and SSE decoding
#     are not re-implemented anywhere.
#  2) accept `delta.reasoning` as a reasoning alias in parseSse. The zen
#     compat layer streams DeepSeek thinking as `reasoning` (+
#     `reasoning_details`) instead of the official `reasoning_content`; without
#     this, thinking blocks are dropped from the session history and the next
#     assistant tool-call turn is sent without reasoning_content, which the
#     DeepSeek Console rejects with "The reasoning_content in the thinking mode
#     must be passed back to the API."
#
# Run by the nix buildPhase, after `npm ci`, so node_modules files exist here
# (a patchPhase-time applyPatches could not target them yet).
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

# 3) zen-compat reasoning alias in parseSse (idempotent line swap).
if grep -q 'const reasoning = delta?.reasoning_content;' "$lib"; then
  sed -i 's/const reasoning = delta?.reasoning_content;/const reasoning = delta?.reasoning_content ?? delta?.reasoning;/' "$lib"
fi
