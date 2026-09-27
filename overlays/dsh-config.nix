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
      agent-loop = {
        maxParallelToolCalls = 10;
      };
      permission = {
        defaultPreset = "danger-full-access";
      };
      llm-deepseek = {
        models = [ ];
      };
      web-search-deepseek = {
        maxUses = 0;
      };
      mcp = {
        mcp-nixos.command = lib.getExe mcp-nixos;
        context7-mcp.command = lib.getExe context7-mcp;
        mobile-mcp.command = "mcp-server-mobile";
        grep-app = {
          type = "http";
          url = "https://mcp.grep.app";
        };
      };
    };
  }
]
