{
  lib,
  nixfmt-rs,
  rustfmt,
  shfmt,
  taplo,
  yamlfmt,
  mcp-nixos,
  context7-mcp,
  uv,
  writeText,
}:

writeText "opencode-config.json" (
  builtins.toJSON {
    "$schema" = "https://opencode.ai/config.json";
    autoshare = false;
    autoupdate = false;
    tui = {
      scroll_acceleration.enabled = true;
      diff_style = "stacked";
    };
    model = "opencode/deepseek-v4-flash-free";
    plugin = [
      "@cortexkit/opencode-magic-context"
      # "@zilliz/memsearch-opencode"
      "opencode-pty"
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
    permission = "allow";
    compaction = {
      auto = false;
      prune = false;
    };
    formatter = {
      nixfmt = {
        command = [
          (lib.getExe nixfmt-rs)
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
          "open-websearch"
        ];
        enabled = true;
        environment = {
          SEARCH_MODE = "request";
          DEFAULT_SEARCH_ENGINE = "duckduckgo";
        };
      };
      gh_grep = {
        enabled = true;
        type = "remote";
        url = "https://mcp.grep.app";
      };
    };
    command = {
      goal = {
        description = "Set a session-scoped goal and auto-continue until complete.";
        template = "$ARGUMENTS";
      };
    };
  }
)
