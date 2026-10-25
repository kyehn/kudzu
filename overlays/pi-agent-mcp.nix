{
  lib,
  writeText,
  open-websearch,
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
      mobile-mcp.command = "mcp-server-mobile";
      open-websearch = {
        command = lib.getExe open-websearch;
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
