{
  lib,
  formats,
  mcp-nixos,
  context7-mcp,
  nodejs-slim,
}:

# The dsh counterpart of the original reasonix-config.nix: a static
# configuration layer for the DeepSeek Harness CLI. It expresses the same
# deployment stance — unrestricted sandbox, never-asking approval, and the
# MCP servers reasonix ships (mcp-nixos, context7-mcp, mobile-mcp,
# open-websearch, grep-app) — in dsh's loader patch format, so it stays
# model-free: no provider routes, no model lists, no API endpoints. The one
# dynamic default (the zen default model selection) lives in the dsh bundle
# defaults and the .github/dsh-config tooling, never here.
#
# The generated file is a patch list for `dsh --patch <path>` (or a profile
# overlay). Each MCP server is one `@deepseek-ai/dsh-mcp-client` plugin
# instance (that plugin connects exactly one server per instance); sandbox
# policy and approval are plain config overrides. Its ids repeat the bundle
# defaults with identical values, so layering it on top is idempotent.

let
  # One dsh-mcp-client plugin instance per server (stdio transport).
  mcpClient = serverName: command: args: {
    id = serverName;
    name = "@deepseek-ai/dsh-mcp-client";
    config = {
      transport = "stdio";
      inherit serverName command args;
      env = { };
      cwd = ".";
      toolCallTimeoutMs = 60000;
      failOnStartupError = false;
    };
  };
  # One dsh-mcp-client plugin instance over Streamable HTTP.
  mcpClientHttp = serverName: url: {
    id = serverName;
    name = "@deepseek-ai/dsh-mcp-client";
    config = {
      transport = "streamable-http";
      inherit serverName url;
      headers = { };
      toolCallTimeoutMs = 60000;
      failOnStartupError = false;
    };
  };
in
(formats.yaml { }).generate "dsh-config.yml" [
  {
    insert = [
      (mcpClient "mcp-nixos" (lib.getExe mcp-nixos) [ ])
      (mcpClient "context7-mcp" (lib.getExe context7-mcp) [ ])
      # Available on PATH; matches the original reasonix config.
      (mcpClient "mobile-mcp" (lib.getExe' nodejs-slim "npx") [
        "-y"
        "@mobilenext/mobile-mcp@latest"
      ])
      (mcpClient "open-websearch" "open-websearch" [ ])
      (mcpClientHttp "grep-app" "https://mcp.grep.app")
    ];
  }
  {
    id = "sandbox-policy";
    config = {
      mode = "danger-full-access";
      workspaceRoot = "/";
    };
  }
  {
    id = "approval";
    config = {
      policy = "never";
    };
  }
]
