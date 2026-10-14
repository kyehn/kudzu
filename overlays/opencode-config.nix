{
  lib,
  writeText,
  mcp-nixos,
  context7-mcp,
  open-websearch,
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
    model = "opencode/muse-spark-1.3-contributor-free";
    update = "disable";
    snapshots = false;
    formatter = false;
    websearch = false;
    warming = false;
    plugins = [
      "@cortexkit/opencode-magic-context"
      {
        package = "@prevalentware/opencode-goal-plugin";
        options = {
          max_auto_turns = 35;
          max_prompt_failures = 7;
          locale = "zh-CN";
          max_no_progress_turns = 5;
        };
      }
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
        "resource" = "ls /nix/store";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "ls /nix/store *";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "paseo daemon stop*";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "paseo daemon restart*";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "paseo restart*";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "pkill *paseo*";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "killall *paseo*";
        "effect" = "deny";
      }
      {
        "action" = "shell";
        "resource" = "fuser -k *6767*";
        "effect" = "deny";
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
        command = [ (lib.getExe open-websearch) ];
        environment = {
          SEARCH_MODE = "request";
          DEFAULT_SEARCH_ENGINE = "duckduckgo";
          MODE = "stdio";
        };
      };
      grep_app = {
        type = "remote";
        url = "https://mcp.grep.app";
      };
    };
  }
)
