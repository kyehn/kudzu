{
  lib,
  buildNpmPackage,
  fetchzip,
  nodejs_24,
  jq,
  esbuild,
}:

let
  version = "0.1.0-rc.7";
in
(buildNpmPackage.override { nodejs = nodejs_24; }) {
  pname = "dsh";
  inherit version;

  # 发布产物：官方 npm tarball（已预构建 JS），跟随 npm 发布版本而非上游 git
  src = fetchzip {
    url = "https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-${version}.tgz";
    hash = "sha256-YffiyssFlYxdLbjRmAFDkJRL07bTTI/0xbbOBqHw8sQ=";
  };

  npmDepsHash = "sha256-f0SHDXoqOlFgtvvpJUos0j6/7AEg774LZzfHmhiXb3Q=";

  # npm tarball 只含运行时依赖；devDependencies 属于 monorepo 构建产物。
  # 删掉它们使 vendored lockfile（本目录 package-lock.json）与 package.json
  # 保持同步，`npm ci` 才能通过。jq 用绝对路径：该 hook 也会在
  # fetchNpmDeps derivation 内运行，那里没有 nativeBuildInputs。
  postPatch = ''
    ${jq}/bin/jq 'del(.devDependencies) | .dependencies.undici = "^7.29.0"' package.json > package.json.new
    mv package.json.new package.json
    cp ${./package-lock.json} package-lock.json
  '';

  dontNpmBuild = true;

  # opencode-sim 为 TypeScript 源码（opencode-sim/opencode-sim.ts）：Node 24
  # 默认 type stripping 禁止 node_modules 内 .ts（ERR_UNSUPPORTED_NODE_MODULES_
  # TYPE_STRIPPING），故构建期用 esbuild 编译为纯 ESM 注入（--packages=external
  # 保留 undici/node:* 外部导入，运行时从 pi-ai 向上解析）。
  buildInputs = [ esbuild ];

  # web profile 的 HMR loader (@deepseek-ai/cordis-plugin-hmr) 需要
  # --expose-internals，否则 `dsh web` 报 "…is required for HMR service"。
  # --openssl-config 提供 TLS ClientHello 的 signature_algorithms 对齐
  # （Node 唯一无法经 API 控制的维度，见 opencode-sim/openssl.cnf）。
  # 随后注入 opencode 客户端模拟（pi-ai openai-completions api）：
  # 对齐 overlays/reasonix/alignment.patch 的基准（UA/x-opencode-*/动态 id/TLS 参数）。
  postInstall = ''
    substituteInPlace $out/bin/dsh \
      --replace-fail '"${lib.getExe nodejs_24}"' "\"${lib.getExe nodejs_24}\" --expose-internals --openssl-config=$out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/openssl.cnf"
    mkdir -p $out/lib/node_modules/@deepseek-ai/dsh/opencode-sim
    cp ${./opencode-sim/openssl.cnf} $out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/openssl.cnf
    # esbuild 需要 entry 与相对导入（opencode-wire.ts）同目录：整体复制源码目录
    cp ${./opencode-sim}/opencode-sim.ts $out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/opencode-sim.ts
    cp ${./opencode-sim}/opencode-wire.ts $out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/opencode-wire.ts
    ${lib.getExe esbuild} $out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/opencode-sim.ts \
      --bundle --format=esm --platform=node --target=node24 --packages=external \
      --outfile=$out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/opencode-sim.mjs
    rm $out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/opencode-sim.ts $out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/opencode-wire.ts
    ${lib.getExe nodejs_24} ${./opencode-sim/inject.mjs} \
      $out/lib/node_modules/@deepseek-ai/dsh/node_modules/@earendil-works/pi-ai/dist/api/openai-completions.js \
      $out/lib/node_modules/@deepseek-ai/dsh/opencode-sim/opencode-sim.mjs
  '';

  meta = {
    description = "DeepSeek Harness (dsh) - plugin-based agent harness by DeepSeek AI";
    homepage = "https://github.com/deepseek-ai/deepseek-harness";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux ++ lib.platforms.darwin;
    mainProgram = "dsh";
  };
}
