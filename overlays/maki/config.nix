{
  lib,
  linkFarm,
  writeText,
  mcp-nixos,
  context7-mcp,
  uv,
  nodejs-slim,
}:

linkFarm "maki" [
  {
    name = "init.lua";
    path = writeText "init.lua" ''
      maki.setup(${
        lib.generators.toLua { } {
          ui.splash_animation = false;
          always_yolo = true;
          agent.max_continuation_turns = 17;
          telemetry.enabled = false;
          plugins = {
            edit.insert_lines = true;
            task.allow_model = true;
          };
          provider = {
            default_model = "opencode-openai-responses/muse-spark-1.3-contributor-free";
            allowed_models = [
              "opencode-*/*"
              "nvidia-*/*"
            ];
            excluded_models = [
              "openai/*"
              "anthropic/*"
            ];
            max_retries = 10;
            max_timeout_retries = 15;
          };
          net.allowed_private_hosts = [
            "localhost"
            "127.0.0.1"
          ];
          trust = {
            paths = [ "**" ];
            prompt = false;
          };
        }
      })
    '';
  }
  {
    name = "permissions.toml";
    path = (formats.toml { }).generate "permissions.toml" {
      default = "allow";
      bash.deny = [
        "git checkout -- *"
        "find /nix/store *"
        "ls /nix/store *"
        "find / *"
      ];
    };
  }
  {
    name = "mcp.toml";
    path = (formats.toml { }).generate "mcp.toml" {
      mcp = {
        mcp-nixos = {
          command = [ (lib.getExe mcp-nixos) ];
        };
        context7-mcp = {
          command = [ (lib.getExe context7-mcp) ];
        };
        mobile-mcp = {
          command = [
            (lib.getExe' nodejs-slim "npx")
            "--yes"
            "@mobilenext/mobile-mcp@latest"
          ];
        };
        open-websearch = {
          command = [ "open-websearch" ];
          environment = {
            SEARCH_MODE = "request";
            DEFAULT_SEARCH_ENGINE = "duckduckgo";
            MODE = "stdio";
          };
        };
        grep-app = {
          url = "https://mcp.grep.app";
        };
      };
    };
  }
]
