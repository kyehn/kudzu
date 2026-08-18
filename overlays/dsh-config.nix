{
  lib,
  formats,
  runCommand,
  esbuild,
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
# 内容（模型/provider 数据零硬编码，同 reasonix 约束——插件运行时装配）：
#   - plugins/opencode-sim/      模型配置 + opencode 模拟装配插件（cordis）：
#                                启动时动态抓取 opencode Zen free 模型与
#                                models.dev 元数据（UA 同 reasonix fetcher），
#                                向 llm-pi-ai settings namespace 写入
#                                opencode-zen（opencode.ai/zen/v1 + trigger
#                                headers）与 nvidia-nim（integrate.api.nvidia.
#                                com/v1）两个 provider 路由，并把默认模型设为
#                                opencode 模型（默认模型名称是 nix 之外的
#                                运行时代码，nix 内无任何 provider/model
#                                数据）；配合 overlays/dsh/opencode-sim.mjs
#                                （postInstall 注入 dsh 包）在请求层装配与
#                                reasonix 同源的完整 opencode 客户端特征
#                                （UA/headers/动态 id/TLS 指纹）
#   - cordis.patch.yml（最后一层，按行 id 整体替换 config）：
#     · insert opencode-sim   在 include 树根追加插件条目
#     · sandbox-policy        部署默认 read-only → danger-full-access
#     · permission            defaultPreset = danger-full-access（sandbox 与
#                             approval 组合默认值无匹配 preset 时插件强制要求
#                             显式指定；含完整 presets 表，因 patch 替换整行
#                             config 而非合并）
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

  # $DSH_HOME/settings.yaml：空文档。llm-pi-ai provider 路由与默认模型由
  # opencode-sim 插件在启动时经 settings 服务写入（官方配置位，热加载），
  # 不在 nix 内出现任何 provider/model 数据。
  settingsYaml = yaml.generate "settings.yaml" { };

  # 用户 patch 层：覆盖各 bundle 层的行（最后写入者胜，每行整体替换 config）；
  # insert 无 id 时向根追加新条目（name 相对 Include baseUrl=profiles/main 解析）。
  cordisPatch = yaml.generate "cordis.patch.yml" [
    {
      insert = [
        {
          id = "opencode-sim";
          name = "./plugins/opencode-sim/index.js";
          config = { };
        }
      ];
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

  # 插件 TypeScript 源码目录（Determinate Nix 只支持目录 path 引用）
  pluginSrc = ./dsh/opencode-sim-plugin/src;
in
runCommand "dsh-config"
  {
    nativeBuildInputs = [ esbuild ];
  }
  ''
    mkdir -p $out/profiles/${profile}/plugins/opencode-sim
    cp ${settingsYaml} $out/settings.yaml
    cp ${packageJson} $out/profiles/${profile}/package.json
    cp ${cordisPatch} $out/profiles/${profile}/cordis.patch.yml
    cp ${cordisRoot} $out/profiles/${profile}/cordis.yml
    cp ${pnpmWorkspace} $out/profiles/${profile}/pnpm-workspace.yaml
    cp ${./dsh/opencode-sim-plugin/package.json} $out/profiles/${profile}/plugins/opencode-sim/package.json
    # v2 插件：构建期 esbuild 编译 TypeScript 源码为 ESM 产物（仅依赖
    # node:fs/os/path 内建模块，零外部依赖），保证可复现装配。
    esbuild ${pluginSrc}/index.ts --bundle --format=esm --platform=node \
      --target=node24 --packages=external \
      --outfile=$out/profiles/${profile}/plugins/opencode-sim/index.js
  ''
