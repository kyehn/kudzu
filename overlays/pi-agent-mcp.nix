{
  lib,
  writeText,
  mcp-nixos,
  context7-mcp,
  uv,
}:

writeText "mcp.json" (
  builtins.toJSON {
    mcpServers = {
      mcp-nixos = {
        command = lib.getExe mcp-nixos;
      };
      context7-mcp = {
        command = lib.getExe context7-mcp;
      };
      android-mcp = {
        command = lib.getExe' uv "uvx";
        args = [
          "--python"
          "3.13"
          "android-mcp"
        ];
      };
      open-websearch = {
        command = "open-websearch";
        env = {
          SEARCH_MODE = "request";
          DEFAULT_SEARCH_ENGINE = "duckduckgo";
        };
      };
    };
  }
)
