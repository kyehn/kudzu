{
  lib,
  writeText,
  mcp-nixos,
  context7-mcp,
}:

writeText "mcp.json" (
  builtins.toJSON {
    settings = {
      allowInstall = false;
      showStatusIcon = false;
      mcpFooterStatus = "off";
      warnOnLargeDirectTools = false;
      notifyOnStartupConnect = false;
      samplingAutoApprove = true;
      trace.enabled = false;
    };
    mcpServers = {
      mcp-nixos.command = lib.getExe mcp-nixos;
      context7-mcp.command = lib.getExe context7-mcp;
      mobile-mcp.command = "mcp-server-mobile";
      open-websearch = {
        command = "open-websearch";
        env = {
          SEARCH_MODE = "request";
          DEFAULT_SEARCH_ENGINE = "duckduckgo";
          MODE = "stdio";
        };
      };
      grep-app.url = "https://mcp.grep.app";
    };
  }
)
