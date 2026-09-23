{
  lib,
  writeText,
  mcp-nixos,
  context7-mcp,
  codegraph,
}:

let
  subagent_model = {
    providerID = "opencode";
    model = "muse-spark-1.3-contributor-free";
    variant = "xhigh";
  };
in
writeText "opencode.json" (
  builtins.toJSON {
    general.model = subagent_model;
    explore.model = subagent_model;
    "$schema" = "https://opencode.ai/config.json";
    model = "opencode/mimo-v2.6-flash-free";
    update = "disable";
    snapshots = false;
    formatter = false;
    websearch = false;
    warming = false;
    plugins = [
      "@cortexkit/opencode-magic-context"
      "opencode-pty/v2"
      "context-mode"
    ];
    permissions = [
      {
        "action" = "shell";
        "resource" = "*";
        "effect" = "allow";
      }
      {
        "action" = "external_directory";
        "resource" = "*";
        "effect" = "allow";
      }
      {
        "action" = "shell";
        "resource" = "find / *";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "find /nix/store *";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "find /usr *";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "find /home/runner *";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "ls /nix/store *";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "git checkout -- *";
        "effect" = "ask";
      }
      {
        "action" = "edit";
        "resource" = ".github/workflows/*";
        "effect" = "ask";
      }
      {
        "action" = "edit";
        "resource" = ".github/actions/*";
        "effect" = "ask";
      }
      {
        "action" = "edit";
        "resource" = "flake.nix";
        "effect" = "ask";
      }
    ];
    experimental.portable_shell_scanner = true;
    compaction.auto = false;
    mcp.servers = {
      mcp-nixos = {
        type = "local";
        command = [ (lib.getExe mcp-nixos) ];
      };
      context7-mcp = {
        type = "local";
        command = [ (lib.getExe context7-mcp) ];
      };
      mobile-mcp = {
        type = "local";
        command = [ "mcp-server-mobile" ];
      };
      open-websearch = {
        type = "local";
        command = [ "open-websearch" ];
        environment = {
          SEARCH_MODE = "request";
          DEFAULT_SEARCH_ENGINE = "duckduckgo";
          MODE = "stdio";
        };
      };
      codegraph = {
        type = "local";
        command = [
          (lib.getExe codegraph)
          "serve"
          "--mcp"
        ];
      };
      grep_app = {
        type = "remote";
        url = "https://mcp.grep.app";
      };
    };
  }
)
