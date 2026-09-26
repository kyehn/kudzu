{
  lib,
  writeText,
}:

writeText "settings.json" (
  builtins.toJSON {
    quietStartup = true;
    defaultProjectTrust = "always";
    enableInstallTelemetry = false;
    fullscreenCopyOnSelect = false;
    enableSkillCommands = false;
    retry = {
      maxRetries = 9;
      provider.maxRetries = 9;
    };
    packages = [
      "npm:pi-background-tasks"
      "npm:@dietrichgebert/ponytail"
      "npm:context-mode"
      "npm:@cortexkit/pi-magic-context"
      "npm:pi-mcp-adapter"
      "npm:@juicesharp/rpiv-ask-user-question"
      "npm:@juicesharp/rpiv-todo"
      "npm:@ff-labs/pi-fff"
      "npm:pi-memory"
      "npm:pi-rtk-optimizer"
    ];
    env = {
      PI_BG_DISABLE_PI_TELEMETRY = 1;
      PI_BG_DISABLE_UPDATE_CHECK = 1;
      PONYTAIL_DEFAULT_MODE = "lite";
      PI_FFF_MODE = "override";
      FFF_ENABLE_HOME_SCAN = 0;
      FFF_WARN_HOME_SCAN = 0;
    };
    defaultProvider = "opencode";
    defaultModel = "muse-spark-1.3-contributor-free";
    defaultThinkingLevel = "max";
  }
)
