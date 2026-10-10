{
  lib,
  linkFarm,
  formats,
  mcp-nixos,
  context7-mcp,
  open-websearch,
}:

(formats.yaml { }).generate "cordis.patch.yml" [
  {
    insert = [
      {
        id = "mcp-nixos";
        name = "@deepseek-ai/dsh-mcp-client";
        config = {
          transport = "stdio";
          serverName = "mcp-nixos";
          command = lib.getExe mcp-nixos;
        };
      }
      {
        id = "context7-mcp";
        name = "@deepseek-ai/dsh-mcp-client";
        config = {
          transport = "stdio";
          serverName = "context7-mcp";
          command = lib.getExe context7-mcp;
        };
      }
      {
        id = "open-websearch";
        name = "@deepseek-ai/dsh-mcp-client";
        config = {
          transport = "stdio";
          serverName = "open-websearch";
          command = lib.getExe open-websearch;
          env = {
            SEARCH_MODE = "request";
            DEFAULT_SEARCH_ENGINE = "duckduckgo";
            MODE = "stdio";
          };
        };
      }
      {
        id = "mobile-mcp";
        name = "@deepseek-ai/dsh-mcp-client";
        config = {
          transport = "stdio";
          serverName = "mobile-mcp";
          command = "mcp-server-mobile";
        };
      }
      {
        id = "grep-app";
        name = "@deepseek-ai/dsh-mcp-client";
        config = {
          transport = "streamable-http";
          serverName = "grep-app";
          url = "https://mcp.grep.app";
        };
      }
    ];
  }
  {
    id = "llm-deepseek";
    name = "@deepseek-ai/dsh-llm-deepseek-api-key";
    disabled = true;
  }
  {
    id = "web-search-deepseek";
    name = "@deepseek-ai/dsh-web-search-deepseek";
    disabled = true;
  }
  {
    id = "agent-instructions";
    name = "@deepseek-ai/dsh-agent-instructions";
    config = {
      maxBytes = 65536;
      instructionFileCandidates = [ "AGENTS.md" ];
      localInstructionFileCandidates = [ "AGENTS.local.md" ];
    };
  }
  {
    id = "tool-web";
    name = "@deepseek-ai/dsh-tool-web";
    config.search = false;
  }
  {
    id = "compaction-basic";
    name = "@deepseek-ai/dsh-compaction-basic";
    config.thresholdRatio = 0.6;
  }
  {
    id = "permission";
    name = "@deepseek-ai/dsh-permission-presets";
    config = {
      presets.danger-full-access = {
        sandbox = "danger-full-access";
        approval = "ask";
      };
      defaultPreset = "danger-full-access";
    };
  }
  {
    id = "permission-rules";
    name = "dsh-permission-rules";
    config = {
      fallbackPath = (formats.yaml { }).generate "rules.yaml" {
        rules = [
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "sleep";
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "git";
                args = [
                  "checkout"
                  "--"
                ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "git";
                args = [ "restore" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "git";
                args = [
                  "reset"
                  "--hard"
                ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "find";
                args = [ "/nix/store" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "ls";
                args = [ "/nix/store" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "find";
                args = [ "/" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "find";
                args = [ "/usr" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "find";
                args = [ "/home/runner" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "paseo";
                args = [
                  "daemon"
                  "stop*"
                ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "paseo";
                args = [
                  "daemon"
                  "restart*"
                ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "paseo";
                args = [ "restart*" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "pkill";
                anyArg = [ "*paseo*" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "killall";
                anyArg = [ "*paseo*" ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = {
              tools = [ "bash" ];
              argv = {
                command = "fuser";
                args = [
                  "-k"
                  "*6767*"
                ];
              };
            };
            action = "deny";
            reason = "Permission denied";
          }
          {
            match = { };
            action = "allow";
            reason = "allow";
          }
        ];
      };
      language = "zh";
      watch = false;
      network = {
        enabled = false;
        mode = "allow-all";
      };
      builtin.enabled = false;
    };
  }
  {
    id = "agent-default-model";
    config = {
      provider = "opencode-openai-responses";
      model = "muse-spark-1.3-contributor-free";
    };
  }
]
