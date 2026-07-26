{
  lib,
  runCommand,
  makeBinaryWrapper,
  opencode,
  ripgrep,
  rust-analyzer,
  ktlint,
  nixd,
  ruff,
  bun,
  openspec,
  go,
  nixfmt-rs,
}:

runCommand "opencode"
  {
    buildInputs = [ makeBinaryWrapper ];
  }
  ''
    mkdir --parents $out/bin
    makeWrapper ${lib.getExe' opencode ".opencode-wrapped"} $out/bin/opencode \
      --prefix PATH : ${
        lib.makeBinPath [
          ripgrep
          rust-analyzer
          ktlint
          nixd
          ruff
          bun
          openspec
          go
          nixfmt-rs
        ]
      } \
      --set OPENCODE_DISABLE_AUTOUPDATE true \
      --set OPENCODE_DISABLE_DEFAULT_PLUGINS true \
      --set OPENCODE_EXPERIMENTAL_PARALLEL true \
      --set OPENCODE_ENABLE_EXPERIMENTAL_MODELS true \
      --set OPENCODE_DISABLE_CLAUDE_CODE 1 \
      --set OPENCODE_DISABLE_CLAUDE_CODE_PROMPT 1 \
      --set OPENCODE_DISABLE_CLAUDE_CODE_SKILLS 1 \
      --set OPENCODE_ENABLE_EXA false \
      --set OPENCODE_AUTO_SHARE false \
      --set OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER true \
      --set OPENCODE_EXPERIMENTAL_PLAN_MODE true \
      --set OPENCODE_EXPERIMENTAL_NATIVE_LLM true \
      --set OPENCODE_EXPERIMENTAL_DISABLE_COPY_ON_SELECT true \
      --set OPENCODE_EXPERIMENTAL_LSP_TOOL true \
      --set OPENCODE_EXPERIMENTAL_OXFMT true \
      --set OPENCODE_EXPERIMENTAL_LSP_TY true \
      --set OPENCODE_EXPERIMENTAL_SCOUT true
  ''
