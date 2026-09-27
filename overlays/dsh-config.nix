{
  lib,
  linkFarm,
  formats,
  mcp-nixos,
  context7-mcp,
}:

linkFarm "dsh" [
  {
    name = "settings.yaml";
    path = (formats.yaml { }).generate "settings.yaml" {
      permission.defaultPreset = "danger-full-access";
      llm-deepseek.models = [ ];
    };
  }
  {
    name = "cordis.patch.yml";
    path = (formats.yaml { }).generate "cordis.patch.yml" [
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
        id = "web-search-deepseek";
        disabled = true;
      }
      {
        id = "tool-web";
        config.search = false;
      }
      {
        id = "compaction-basic";
        config.thresholdRatio = 0.6;
      }
    ];
  }
]
