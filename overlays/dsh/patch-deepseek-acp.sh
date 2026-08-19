#!/usr/bin/env bash
# Patch the deepseek-acp npm package so the bundled LLM adapter plugins
# (dsh-llm-opencode-zen, dsh-llm-nvidia-nim) are loaded into its cordis app.
# deepseek-acp assembles a fixed plugin list in lib/launcher/boot.js; we append
# two ESM imports (hoisted, so position in the file is irrelevant) and extend
# the assembly loop. This lets DEEPSEEK_ACP_PROVIDER route to the zen/NVIDIA
# providers instead of requiring a DeepSeek API key.
set -euo pipefail

acp="$1"
boot="$acp/lib/launcher/boot.js"

# Verify the exact assembly line exists before rewriting it.
grep -q 'for (const plugin of \[SessionService, LlmService, ToolRegistry, AgentRegistry, AgentLoop\]) {' "$boot"

printf '\nimport { apply as OpencodeZenApply, name as OpencodeZenName, inject as OpencodeZenInject } from "@deepseek-ai/dsh-llm-opencode-zen";\nimport { apply as NvidiaNimApply, name as NvidiaNimName, inject as NvidiaNimInject } from "@deepseek-ai/dsh-llm-nvidia-nim";\nconst OpencodeZenPlugin = { name: OpencodeZenName, apply: OpencodeZenApply, inject: OpencodeZenInject };\nconst NvidiaNimPlugin = { name: NvidiaNimName, apply: NvidiaNimApply, inject: NvidiaNimInject };\n' >> "$boot"

sed -i 's|for (const plugin of \[SessionService, LlmService, ToolRegistry, AgentRegistry, AgentLoop\]) {|for (const plugin of [SessionService, LlmService, ToolRegistry, AgentRegistry, AgentLoop, OpencodeZenPlugin, NvidiaNimPlugin]) {|' "$boot"

# Leave a trace for debugging and verify the patch landed.
printf '// patched by patch-deepseek-acp.sh: bundled LLM adapter plugins loaded\n' >> "$boot"
grep -q 'OpencodeZenPlugin, NvidiaNimPlugin' "$boot"
echo "patched: $boot"