{
  lib,
  writeText,
  mcp-nixos,
  context7-mcp,
  uv,
  nodejs-slim,
}:

writeText "settings.json" (
  builtins.toJSON {
    quietStartup = true;
    defaultProjectTrust = "always";
    enableInstallTelemetry = false;
    retry = {
      maxRetries = 9;
      provider.maxRetries = 9;
    };
    packages = [
      "npm:pi-background-tasks"
      "npm:pi-subagents"
      "npm:context-mode"
      "npm:@cortexkit/pi-magic-context"
      "npm:pi-mcp-adapter"
      "npm:@juicesharp/rpiv-ask-user-question"
      "npm:@juicesharp/rpiv-todo"
      "npm:@ff-labs/pi-fff"
      "npm:pi-memory"
    ];
    env.PI_LENS_STARTUP_MODE = "minimal";
    defaultProvider = "opencode";
    defaultModel = "muse-spark-1.3-contributor-free";
    defaultThinkingLevel = "max";
  }
)
