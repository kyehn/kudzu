# pi-coding-agent: Bun runtime wrapper, matching nixpkgs/lukasl pattern.
#
# Two derivations:
#   1. node_modules FOD (npm ci --ignore-scripts)
#   2. main: workspace build → bun runtime wrapper
#
# Runtime layout:
#   $out/bin/pi  →  bun ... $out/lib/node_modules/.../dist/cli.js
#   $out/lib/node_modules/                       all runtime deps
#   $out/lib/node_modules/@earendil-works/pi-*/  built workspace packages
{
  lib,
  stdenv,
  cacert,
  fetchFromGitHub,
  fetchurl,
  bun,
  nodejs,
  makeWrapper,
  ripgrep,
  fd,
  versionCheckHook,
  writableTmpDirAsHomeHook,
}:
let
  version = "0.84.2";

  src = fetchFromGitHub {
    owner = "earendil-works";
    repo = "pi";
    tag = "v${version}";
    hash = "sha256-d29ft9otYxdHRWYIAX8KMHPpppToX9ME5LbPb1rPcYo=";
  };

  modelData = fetchurl {
    url = "https://registry.npmjs.org/@earendil-works/pi-ai/-/pi-ai-${version}.tgz";
    hash = "sha256-AmJ4Wnaw6y7sWWzYp6su4j7vidLvG7EhHE8KGUTaz0E=";
  };

  runtimeBins = lib.makeBinPath [
    ripgrep
    fd
  ];

  nodeModules = stdenv.mkDerivation {
    pname = "pi-coding-agent-node_modules";
    inherit version src;

    impureEnvVars = lib.fetchers.proxyImpureEnvVars;
    env.NODE_EXTRA_CA_CERTS = "${cacert}/etc/ssl/certs/ca-bundle.crt";

    nativeBuildInputs = [
      nodejs
      writableTmpDirAsHomeHook
    ];
    dontConfigure = true;

    buildPhase = ''
      runHook preBuild
      npm ci --ignore-scripts --no-audit --no-fund
      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall
      cp -R node_modules $out
      runHook postInstall
    '';

    dontFixup = true;
    outputHashMode = "recursive";
    outputHashAlgo = "sha256";
    outputHash = "sha256-nvku/nqBHt7QU+bB2olGlzTK9vKzK6lg3VQb1j8lEU0=";
  };
in
stdenv.mkDerivation {
  pname = "pi-coding-agent";
  inherit version src;

  strictDeps = true;
  env.NODE_EXTRA_CA_CERTS = "${cacert}/etc/ssl/certs/ca-bundle.crt";

  nativeBuildInputs = [
    bun
    nodejs
    makeWrapper
    writableTmpDirAsHomeHook
  ];

  configurePhase = ''
    runHook preConfigure

    cp -R ${nodeModules}/. ./node_modules/
    chmod -R u+w node_modules
    patchShebangs node_modules >/dev/null

    mkdir -p packages/ai/src/providers/data
    tar --extract --gzip --file=${modelData} \
      --directory=packages/ai/src/providers/data \
      --strip-components=4 \
      package/dist/providers/data

    runHook postConfigure
  '';

  buildPhase = ''
    runHook preBuild

    npx tsgo -p packages/tui/tsconfig.build.json
    npx tsgo -p packages/telemetry/tsconfig.build.json
    npx tsgo -p packages/ai/tsconfig.build.json
    npx tsgo -p packages/agent/tsconfig.build.json
    npx tsgo -p packages/protocol/tsconfig.build.json
    npx tsgo -p packages/client/tsconfig.build.json
    npm run build --workspace=packages/coding-agent

    runHook postBuild
  '';

  # Follow lukasl/pi.nix: stage workspace dist, then copy full node_modules.
  installPhase = ''
    runHook preInstall

    mkdir -p $out/bin $out/lib/node_modules/@earendil-works

    for pkg in tui telemetry ai agent protocol client coding-agent; do
      [ -d "packages/$pkg/dist" ] || continue
      mkdir -p "$out/lib/node_modules/@earendil-works/pi-$pkg"
      cp -r packages/$pkg/dist/* "$out/lib/node_modules/@earendil-works/pi-$pkg/"
      cp packages/$pkg/package.json "$out/lib/node_modules/@earendil-works/pi-$pkg/"
    done

    cp -rL node_modules/. "$out/lib/node_modules/"

    makeWrapper ${lib.getExe bun} $out/bin/pi \
      --add-flags "$out/lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js" \
      --set PI_PACKAGE_DIR "$out/lib/node_modules/@earendil-works/pi-coding-agent" \
      --prefix NODE_PATH : "$out/lib/node_modules" \
      --suffix PATH : "${runtimeBins}" \
      --set-default PI_SKIP_VERSION_CHECK 1 \
      --set-default PI_TELEMETRY 0

    runHook postInstall
  '';

  doInstallCheck = true;
  nativeInstallCheckInputs = [
    versionCheckHook
    writableTmpDirAsHomeHook
  ];
  versionCheckKeepEnvironment = [ "HOME" ];
  versionCheckProgramArg = "--version";

  passthru = {
    inherit nodeModules;
  };

  meta = {
    description = "Pi coding agent CLI, built with Bun";
    homepage = "https://pi.dev/";
    license = lib.licenses.mit;
    mainProgram = "pi";
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
      "x86_64-darwin"
      "aarch64-darwin"
    ];
  };
}
