{
  lib,
  formats,
  mcp-nixos,
  context7-mcp,
  uv,
  go,
  gopls,
}:

(formats.toml { }).generate "config.toml" {
  config_version = 5;
  default_model = "deepseek-v4-flash-free";
  language = "zh";
  ui.show_reasoning = true;
  environment = {
    enabled = true;
    tools = {
      go = lib.getExe go;
    };
  };
  agent = {
    reasoning_language = "auto";
    max_subagent_depth = 2;
    max_subagent_concurrency = 3;
    max_parallel_writers = 3;
  };
  tools.enabled = [ ];
  lsp = {
    enabled = true;
    servers.go = {
      command = lib.getExe gopls;
      extensions = [ ".go" ];
    };
  };
  skills = {
    max_depth = 1;
    excluded_paths = [ ];
    disabled_skills = [ ];
  };
  permissions = {
    mode = "allow";
    allow = [
      "Bash"
      "Edit()"
    ];
    deny = [ "Bash(find /nix/store*)" ];
    ask = [
      "Edit(.github/workflows/**)"
      "Edit(.github/actions/**)"
      "Edit(flake.nix)"
    ];
  };
  sandbox = {
    workspace_root = "/";
    allow_write = [ "/" ];
    forbid_read = [ ];
    bash = "off";
    network = true;
  };
  bot.enabled = false;
  secrets = {
    filter_subprocess_env = false;
    protect_sensitive_files = false;
  };
  plugins = [
    {
      name = "mcp-nixos";
      type = "stdio";
      command = lib.getExe mcp-nixos;
    }
    {
      name = "context7-mcp";
      type = "stdio";
      command = lib.getExe context7-mcp;
    }
    {
      name = "android-mcp";
      type = "stdio";
      command = lib.getExe' uv "uvx";
      args = [
        "--python"
        "3.13"
        "android-mcp"
      ];
    }
    {
      name = "open-websearch";
      type = "stdio";
      command = "open-websearch";
      env = {
        SEARCH_MODE = "request";
        DEFAULT_SEARCH_ENGINE = "duckduckgo";
      };
    }
    {
      name = "grep-app";
      type = "http";
      url = "https://mcp.grep.app";
    }
  ];
}
