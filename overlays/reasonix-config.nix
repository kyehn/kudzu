{
  lib,
  formats,
  mcp-nixos,
  context7-mcp,
  nodejs-slim,
  go,
  nil,
  ty,
  kotlin-language-server,
  typescript-language-server,
  rust-analyzer,
  ripgrep,
  bashNonInteractive,
}:

(formats.toml { }).generate "config.toml" {
  config_version = 5;
  default_model = "deepseek-v4-flash-free";
  language = "zh";
  ui.show_reasoning = true;
  environment.enabled = false;
  telemetry.cli_metrics = "off";
  agent = {
    reasoning_language = "auto";
    keep = [ ];
    recent_keep = 1;
    max_subagent_depth = 2;
    max_subagent_concurrency = 3;
    max_parallel_writers = 3;
    soft_compact_ratio = 0.4;
    tool_result_snip_ratio = 0.5;
    compact_ratio = 0.7;
    compact_force_ratio = 0.8;
  };
  tools = {
    enabled = [ ];
    search.rg_path = lib.getExe ripgrep;
    shell.path = lib.getExe bashNonInteractive;
  };
  lsp = {
    enabled = true;
    servers = {
      nix = {
        command = lib.getExe nil;
        extensions = [ ".nix" ];
        language_id = "nix";
      };
      python = {
        command = lib.getExe ty;
        args = [ "server" ];
        extensions = [ ".py" ];
      };
      kotlin = {
        command = lib.getExe kotlin-language-server;
        extensions = [ ".kt" ];
      };
      typescript = {
        command = lib.getExe typescript-language-server;
        extensions = [ ".ts" ];
      };
      rust = {
        command = lib.getExe rust-analyzer;
        extensions = [ ".rs" ];
      };
    };
  };
  skills = {
    max_depth = 1;
    excluded_paths = [ ];
    disabled_skills = [ ];
  };
  permissions = {
    mode = "allow";
    allow_dynamic_bash = true;
    allow = [
      "bash"
      "bash_output"
      "code_index"
      "complete_step"
      "delete_range"
      "delete_symbol"
      "edit_file"
      "glob"
      "grep"
      "kill_shell"
      "ls"
      "move_file"
      "multi_edit"
      "notebook_edit"
      "read_file"
      "todo_write"
      "update_goal"
      "wait"
      "web_fetch"
      "write_file"
      "Edit"
      "lsp_definition"
      "lsp_references"
      "lsp_hover"
      "lsp_diagnostics"
      "task"
      "read_only_task"
      "parallel_tasks"
      "fleet"
      "read_subagent_result"
      "ask"
      "docs"
      "history"
      "list_sessions"
      "read_session"
      "memory"
      "remember"
      "forget"
      "run_skill"
      "read_skill"
      "read_only_skill"
      "install_skill"
      "slash_command"
      "explore"
      "research"
      "review"
      "security_review"
      "install_source"
      "connect_tool_source"
      "use_capability"
    ];
    deny = [
      "Bash(find /nix/store*)"
      "Bash(ls /nix/store *)"
    ];
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
      name = "mobile-mcp";
      type = "stdio";
      command = lib.getExe' nodejs-slim "npx";
      args = [
        "-y"
        "@mobilenext/mobile-mcp@latest"
      ];
    }
    {
      name = "open-websearch";
      type = "stdio";
      command = "open-websearch";
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
    }
  ];
}
