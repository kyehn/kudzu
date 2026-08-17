{
  lib,
  buildNpmPackage,
  fetchzip,
  nodejs_24,
  jq,
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

  npmDepsHash = "sha256-9TIeZaxqrbrRQsQp+dB2vcM1GZmCO9dOI2gx4gaiP0w=";

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

  # web profile 的 HMR loader (@deepseek-ai/cordis-plugin-hmr) 需要
  # --expose-internals，否则 `dsh web` 报 "…is required for HMR service"。
  # 随后注入 opencode 客户端模拟（pi-ai openai-completions api）：
  # 对齐 overlays/reasonix/alignment.patch 的基准（UA/x-opencode-*/动态 id/TLS 参数）。
  postInstall = ''
    substituteInPlace $out/bin/dsh \
      --replace-fail '"${lib.getExe nodejs_24}"' '"${lib.getExe nodejs_24}" --expose-internals'
    ${lib.getExe nodejs_24} ${./opencode-sim/inject.mjs} \
      $out/lib/node_modules/@deepseek-ai/dsh/node_modules/@earendil-works/pi-ai/dist/api/openai-completions.js \
      ${./opencode-sim/opencode-sim.mjs}
  '';

  meta = {
    description = "DeepSeek Harness (dsh) - plugin-based agent harness by DeepSeek AI";
    homepage = "https://github.com/deepseek-ai/deepseek-harness";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux ++ lib.platforms.darwin;
    mainProgram = "dsh";
  };
}