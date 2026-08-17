{
  lib,
  formats,
  runCommand,
}:
# 声明式 dsh 配置（DSH_HOME 种子目录），模式对齐 overlays/reasonix-config.nix：
# 以 nix 数据生成配置文件，可经 overlay 引用。
#
# 使用（dsh 会向 DSH_HOME 写入 node_modules，store 只读产物需先物化）：
#
#   CFG="$(nix build .#dsh-config --print-out-paths 2>/dev/null)"
#   cp -rL "$CFG" ~/.dsh && chmod -R u+w ~/.dsh
#   dsh --profile main        # 或 dsh --profile main web（经 profile bundle 起 web）
#
# 覆盖内容：
#   - settings.yaml              llm-pi-ai namespace：openai 路由指向
#                                opencode zen 网关（deepseek-v4-flash-free）；
#                                adapter 配置的官方配置位（dsh-base 注释所述，
#                                热加载）
#   - cordis.patch.yml（最后一层，按行 id 整体替换 config）：
#     · agent-default-model     默认模型 = openai / deepseek-v4-flash-free
#     · sandbox-policy          部署默认 read-only → danger-full-access
#     · permission              defaultPreset = danger-full-access（sandbox 与
#                               approval 组合默认值无匹配 preset 时插件强制要求
#                               显式指定；含完整 presets 表，因 patch 替换整行
#                               config 而非合并）
let
  yaml = formats.yaml { };
  json = formats.json { };

  profile = "main";

  packageJson = json.generate "package.json" {
    name = "dsh-profile-${profile}";
    private = true;
    dependencies = { };
    dsh.profile.bundles = [
      "@deepseek-ai/dsh-base"
      "@deepseek-ai/dsh-web-app"
    ];
  };

  # $DSH_HOME/settings.yaml：namespace 分节由 dsh-settings-file 热加载，
  # adapter（llm-pi-ai）与权限插件据此覆盖部署默认。
  settingsYaml = yaml.generate "settings.yaml" {
    llm-pi-ai = {
      providers.openai = {
        apiKeyEnv = "OPENCODE_API_KEY";
        baseURL = "https://api.opencode.ai/zen/v1";
        # opencode 模拟触发器（见 overlays/dsh/opencode-sim/opencode-sim.mjs）：
        # 出现 x-opencode-client/x-opencode-project 即对该 provider 装配与
        # overlays/reasonix/alignment.patch 同源的 opencode 客户端特征
        # （权威 UA/Accept/Accept-Encoding/动态 session-request id 由注入层生成，
        # 配置只声明意图）。
        headers = {
          "x-opencode-client" = "cli";
          "x-opencode-project" = "global";
        };
        models = [
          {
            id = "deepseek-v4-flash-free";
            name = "DeepSeek V4 Flash (free)";
            contextWindow = 200000;
            maxTokens = 65536;
          }
        ];
      };
    };
  };

  # 用户 patch 层：覆盖各 bundle 层的行（最后写入者胜，每行整体替换 config）
  cordisPatch = yaml.generate "cordis.patch.yml" [
    {
      id = "agent-default-model";
      name = "@deepseek-ai/dsh-agent-default-model";
      config = {
        provider = "openai";
        model = "deepseek-v4-flash-free";
      };
    }
    {
      id = "sandbox-policy";
      name = "@deepseek-ai/dsh-sandbox-policy";
      config = {
        mode = "danger-full-access";
      };
    }
    {
      id = "permission";
      name = "@deepseek-ai/dsh-permission-presets";
      config = {
        defaultPreset = "danger-full-access";
        presets = {
          read-only = {
            sandbox = "read-only";
            approval = "ask";
          };
          workspace-write = {
            sandbox = "workspace-write";
            approval = "ask";
          };
          danger-full-access = {
            sandbox = "danger-full-access";
            approval = "never";
          };
        };
      };
    }
  ];

  # 组合根：空列表；树的补丁在 bundle 层与 cordis.patch.yml（文档要求勿编辑）
  cordisRoot = yaml.generate "cordis.yml" [ ];

  pnpmWorkspace = yaml.generate "pnpm-workspace.yaml" {
    packages = [ "." ];
    nodeLinker = "hoisted";
    autoInstallPeers = false;
  };
in
runCommand "dsh-config" { } ''
  mkdir -p $out/profiles/${profile}
  cp ${settingsYaml} $out/settings.yaml
  cp ${packageJson} $out/profiles/${profile}/package.json
  cp ${cordisPatch} $out/profiles/${profile}/cordis.patch.yml
  cp ${cordisRoot} $out/profiles/${profile}/cordis.yml
  cp ${pnpmWorkspace} $out/profiles/${profile}/pnpm-workspace.yaml
''