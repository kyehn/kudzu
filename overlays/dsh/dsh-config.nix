{
  lib,
  formats,
  linkFarm,
  writeText,
  mcp-nixos,
  context7-mcp,
  codegraph,
  open-websearch,
}:
let
  yaml = formats.yaml { };
  profileName = "kudzu";
  cordisPatch = yaml.generate "cordis.patch.yml" [
    {
      id = "sandbox-policy";
      config.mode = "workspace-write";
    }
    {
      id = "approval";
      config.policy = "ask";
    }
    {
      id = "agent-default-model";
      config = {
        provider = "opencode";
        model = "muse-spark-1.3-contributor-free";
      };
    }
    {
      id = "mcp-nixos";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "nixos";
        transport = "stdio";
        command = lib.getExe mcp-nixos;
      };
    }
    {
      id = "mcp-context7";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "context7";
        transport = "stdio";
        command = lib.getExe context7-mcp;
      };
    }
    {
      id = "mcp-mobile";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "mobile";
        transport = "stdio";
        command = "mcp-server-mobile";
      };
    }
    {
      id = "mcp-codegraph";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "codegraph";
        transport = "stdio";
        command = lib.getExe codegraph;
        args = [
          "serve"
          "--mcp"
        ];
      };
    }
    {
      id = "mcp-websearch";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "websearch";
        transport = "stdio";
        command = lib.getExe open-websearch;
        env = {
          SEARCH_MODE = "request";
          DEFAULT_SEARCH_ENGINE = "duckduckgo";
          MODE = "stdio";
        };
      };
    }
    {
      id = "mcp-grepapp";
      name = "@deepseek-ai/dsh-mcp-client";
      config = {
        serverName = "grepapp";
        transport = "streamable-http";
        url = "https://mcp.grep.app";
      };
    }
  ];

  profilePackage = writeText "package.json" (
    builtins.toJSON {
      name = "dsh-profile-${profileName}";
      private = true;
      dsh.profile.bundles = [
        "@deepseek-ai/dsh-base"
        "dsh-acp-enhanced"
        "billion-context-dsh"
      ];
      dependencies = {
        "@deepseek-ai/dsh-base" = "0.1.7-rc.2";
        "dsh-acp-enhanced" = "0.9.1";
        "billion-context-dsh" = "0.2.26";
      };
    }
  );
in
linkFarm "dsh-config" [
  {
    name = "cordis.patch.yml";
    path = cordisPatch;
  }
  {
    name = "package.json";
    path = profilePackage;
  }
]
