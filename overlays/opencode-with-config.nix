{
  lib,
  runCommand,
  makeWrapper,
  opencode,
  rust-analyzer,
  ktlint,
  nixd,
  ruff,
  bun,
  openspec,
  nixfmt,
  rustfmt,
  shfmt,
  taplo,
  yamlfmt,
  mcp-nixos,
  mcp-server-filesystem,
  mcp-server-git,
  mcp-server-fetch,
  github-mcp-server,
  context7-mcp,
  nodejs-slim,
  uv,
  writeText,
}:

runCommand "opencode"
  {
    buildInputs = [ makeWrapper ];
  }
  ''
    mkdir --parents $out/bin
    makeWrapper ${lib.getExe opencode} $out/bin/opencode \
      --prefix PATH : ${
        lib.makeBinPath [
          rust-analyzer
          ktlint
          nixd
          ruff
          bun
          openspec
        ]
      } \
      --set OPENCODE_DISABLE_DEFAULT_PLUGINS true \
      --set OPENCODE_EXPERIMENTAL_PARALLEL true \
      --set OPENCODE_ENABLE_EXPERIMENTAL_MODELS true \
      --set OPENCODE_EXPERIMENTAL_LSP_TY true \
      --set OPENCODE_CONFIG ${
        writeText "opencode-config.json" (
          builtins.toJSON {
            "$schema" = "https://opencode.ai/config.json";
            autoshare = false;
            autoupdate = false;
            model = "opencode/deepseek-v4-flash-free";
            plugin = [
              "@cortexkit/opencode-magic-context"
              [
                "opencode-goal-plugin"
                {
                  maxTurns = 40;
                  maxDurationMs = 12000000;
                  maxTokens = 60000000;
                  maxRecentMessages = 180;
                  noProgressTurnsBeforePause = 7;
                  maxPromptFailures = 7;
                  completionAudit = true;
                }
              ]
            ];
            compaction = {
              auto = false;
              prune = false;
            };
            formatter = {
              nixfmt = {
                command = [
                  (lib.getExe nixfmt)
                  "$FILE"
                ];
                extensions = [ ".nix" ];
              };
              rustfmt = {
                command = [
                  (lib.getExe rustfmt)
                  "--config"
                  "skip_children=true"
                  "$FILE"
                ];
                extensions = [ ".rs" ];
              };
              shfmt = {
                command = [
                  (lib.getExe shfmt)
                  "-w"
                  "$FILE"
                ];
                extensions = [
                  "*.sh"
                  "*.bash"
                  "*.envrc"
                  "*.envrc.*"
                ];
              };
              taplo = {
                command = [
                  (lib.getExe taplo)
                  "format"
                  "$FILE"
                ];
                extensions = [ "*.toml" ];
              };
              yamlfmt = {
                command = [
                  (lib.getExe yamlfmt)
                  "$FILE"
                ];
                extensions = [
                  "*.yaml"
                  "*.yml"
                ];
              };
            };
            share = "disabled";
            mcp = {
              mcp-nixos = {
                enabled = true;
                type = "local";
                command = [ (lib.getExe mcp-nixos) ];
              };
              context7-mcp = {
                type = "local";
                command = [ (lib.getExe context7-mcp) ];
                enabled = true;
              };
              android-mcp = {
                type = "local";
                command = [
                  (lib.getExe' uv "uvx")
                  "--python"
                  "3.13"
                  "android-mcp"
                ];
                enabled = true;
              };
              web-search = {
                type = "local";
                command = [
                  (lib.getExe' nodejs-slim "npx")
                  "--yes"
                  "open-websearch@latest"
                ];
                enabled = true;
                environment = {
                  SEARCH_MODE = "request";
                  DEFAULT_SEARCH_ENGINE = "duckduckgo";
                };
              };
            };
            command = {
              goal = {
                description = "Set a session-scoped goal and auto-continue until complete.";
                template = "$ARGUMENTS";
                agent = "build";
              };
            };
          }
        )
      }
  ''
