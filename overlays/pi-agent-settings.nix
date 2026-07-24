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
      "npm:@hypabolic/pi-hypa"
      "npm:pi-subagents"
      # "npm:context-mode"
      "npm:@cortexkit/pi-magic-context"
      "npm:pi-mcp-adapter"
      "npm:@juicesharp/rpiv-ask-user-question"
      "npm:@juicesharp/rpiv-todo"
      "npm:pi-lens"
      "npm:@ff-labs/pi-fff"
      "npm:@quintinshaw/pi-dynamic-workflows"
      "npm:pi-codex-goal"
      "npm:pi-autoresearch"
    ];
    env = {
      HYPA_PI_ASK_NON_INTERACTIVE = "allow";
      HYPA_PI_CONFIG = "none";
      PI_LENS_STARTUP_MODE = "minimal";
    };
    defaultProvider = "opencode-zen";
    defaultModel = "deepseek-v4-flash-free";
    defaultThinkingLevel = "high";
    subagents = {
      modelScope = {
        enforce = true;
        allow = [ "opencode-zen/*" ];
      };
    };
  }
)
