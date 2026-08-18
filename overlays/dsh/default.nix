{
  lib,
  buildNpmPackage,
  fetchurl,
  makeWrapper,
  nodejs,
  runCommand,
  stdenv,
  versionCheckHook,
  writableTmpDirAsHomeHook,
}:

let
  version = "0.1.0-rc.7";

  # 发布 tarball 已预构建 (lib/bin.js 为产物), 补上离线 lockfile 后交给
  # buildNpmPackage 安装依赖; 不 vendor 任何源码, 全部来自 npm registry.
  srcWithLock = runCommand "dsh-source" { } ''
    mkdir -p $out
    tar -xzf ${
      fetchurl {
        url = "https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-${version}.tgz";
        hash = "sha256-L48Ldj1hGsU296lBHuQ8CvwGfBuHMsMQLATb45i8rMU=";
      }
    } -C $out --strip-components=1
    cp ${./package-lock.json} $out/package-lock.json
  '';

  # opencode 模拟 HTTP 层: 启动时 --import 注入, 只对 opencode Zen 请求复刻
  # CLI 的 JA3 TLS 指纹、UA 与 x-opencode-* 头 (node-tls-client), 其余透传.
  # 不写 LLM adapter 插件: dsh 本体内置的 llm-pi-ai 承担全部 LLM 功能.
  opencodeFetch = buildNpmPackage {
    pname = "opencode-fetch";
    version = "0.1.0";
    src = ./opencode-fetch;
    npmDepsFetcherVersion = 2;
    npmDepsHash = "sha256-UQMDXa0FqAdgRSG9tXvn+Ct3bl1LNS0EvI8TsGKGIng=";
    dontNpmBuild = true;
  };

  # 自定义 TLS ClientHello 共享库 (JA3/JA4 指纹), 构建期注入, 零运行时下载.
  tlsLibrary = import ./tls-client.nix {
    inherit fetchurl lib stdenv;
  };
in
buildNpmPackage {
  pname = "dsh";
  inherit version;
  src = srcWithLock;

  npmDepsFetcherVersion = 2;
  npmDepsHash = "sha256-tZRYdh4ky085pBUtVafxy09WDREsfWElP1dcny7o/xs=";

  dontNpmBuild = true;

  nativeBuildInputs = [ makeWrapper ];

  # dsh 用到了 --expose-internals (numtide 与 nixpkgs PR 同款包装).
  postInstall = ''
    # 合并 opencode-fetch 补丁及其依赖 (node-tls-client/koffi 等, 全部来自
    # npm registry), 放到 dsh 的 node_modules 下供 --import 解析.
    cp -r --no-preserve=mode ${opencodeFetch}/lib/node_modules/* $out/lib/node_modules/

    # node-tls-client: 让共享库路径可注入 (OPENCODE_TLS_LIBRARY), 替代其
    # 运行时的 GitHub 下载逻辑. 依赖按 opencode-fetch 的嵌套 node_modules 布局.
    patchTarget=$out/lib/node_modules/opencode-fetch/node_modules/node-tls-client/dist/utils/native.js
    node -e '
      const fs = require("node:fs");
      const file = process.argv[1];
      const src = fs.readFileSync(file, "utf8");
      const needle = "path_1.default.join(os_1.default.tmpdir()";
      const replaced = "process.env.OPENCODE_TLS_LIBRARY ? process.env.OPENCODE_TLS_LIBRARY : " + needle;
      if (!src.includes(needle)) {
        console.error("node-tls-client native.js layout changed: " + needle);
        process.exit(1);
      }
      fs.writeFileSync(file, src.split(needle).join(replaced));
    ' "$patchTarget"

    # 安装共享库并注入路径.
    mkdir -p $out/lib/dsh
    cp ${tlsLibrary} $out/lib/dsh/tls-client.so

    rm $out/bin/dsh
    makeWrapper ${lib.getExe nodejs} $out/bin/dsh \
      --argv0 dsh \
      --add-flags "--expose-internals" \
      --add-flags "--import" \
      --add-flags "$out/lib/node_modules/opencode-fetch/index.mjs" \
      --add-flags "$out/lib/node_modules/@deepseek-ai/dsh/lib/bin.js" \
      --set-default OPENCODE_TLS_LIBRARY $out/lib/dsh/tls-client.so
  '';

  doInstallCheck = true;
  nativeInstallCheckInputs = [
    versionCheckHook
    writableTmpDirAsHomeHook
  ];
  versionCheckKeepEnvironment = [ "HOME" ];
  versionCheckProgramArg = "--version";

  meta = {
    description = "Open-source agent harness developed by DeepSeek AI (with an HTTP-layer opencode simulation for opencode Zen)";
    homepage = "https://github.com/deepseek-ai/deepseek-harness";
    changelog = "https://github.com/deepseek-ai/deepseek-harness/releases";
    license = lib.licenses.mit;
    mainProgram = "dsh";
    platforms = lib.platforms.all;
  };
}
