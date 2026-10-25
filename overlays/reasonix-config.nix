{
  lib,
  formats,
  ripgrep,
  bashNonInteractive,
  open-websearch,
}:

(formats.toml { }).generate "config.toml" {
  default_model = "nvidia/minimaxai/minimax-m3.1-flash";
  language = "zh";
  auto_submit = true;
  ui.show_reasoning = true;
  environment.enabled = false;
  telemetry.cli_metrics = "off";
  agent = {
    reasoning_language = "auto";
    keep = [ ];
    max_subagent_depth = 2;
    max_subagent_concurrency = 3;
    max_parallel_writers = 3;
    compact_ratio = 0.75;
  };
  tools = {
    enabled = [ ];
    search.rg_path = lib.getExe ripgrep;
    shell.path = lib.getExe bashNonInteractive;
  };
  lsp.enabled = false;
  skills = {
    paths = [ "~/.agents/skills" ];
    max_depth = 1;
    excluded_paths = [ ];
    disabled_skills = [ ];
  };
  permissions = {
    mode = "allow";
    allow = [ ];
    deny = [
      "Bash(find /nix/store:*)"
      "Bash(ls /nix/store:*)"
      "Bash(find /:*)"
      "Bash(find /usr:*)"
      "Bash(find /home/runner:*)"
      "Bash(paseo daemon stop:*)"
      "Bash(paseo daemon restart:*)"
      "Bash(paseo restart:*)"
      "Bash(pkill -f paseo:*)"
      "Bash(pkill paseo:*)"
      "Bash(killall paseo:*)"
      "Bash(fuser -k 6767:*)"
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
      name = "mobile-mcp";
      type = "stdio";
      command = "mcp-server-mobile";
      concurrency = "serial";
    }
    {
      name = "open-websearch";
      type = "stdio";
      command = lib.getExe open-websearch;
      concurrency = "serial";
      env = {
        SEARCH_MODE = "request";
        DEFAULT_SEARCH_ENGINE = "duckduckgo";
        MODE = "stdio";
      };
    }
    {
      name = "grep-app";
      type = "http";
      url = "https://mcp.grep.app";
      concurrency = "serial";
    }
  ];
}
