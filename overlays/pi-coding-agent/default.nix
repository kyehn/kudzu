# pi-coding-agent: compiled Bun binary, matching upstream build-binaries.sh.
#
# Two derivations:
#   1. node_modules FOD (npm ci --ignore-scripts)
#   2. main: workspace build → bun build --compile → install binary + assets
#
# Runtime layout (mirrors upstream release archives):
#   $out/bin/pi                         compiled binary
#   $out/lib/pi/photon_rs_bg.wasm       WASM loaded from process.execPath dir
#   $out/lib/pi/theme/                  TUI theme JSON
#   $out/lib/pi/assets/                 image assets
#   $out/lib/pi/export-html/            HTML export templates
#   $out/lib/pi/docs/                   documentation
#   $out/lib/pi/examples/               examples
#   $out/lib/pi/node_modules/@mariozechner/clipboard*   native bindings
{
  lib,
  stdenv,
  cacert,
  fetchFromGitHub,
  fetchurl,
  bun,
  nodejs,
  makeBinaryWrapper,
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

  nodeModules = stdenv.mkDerivation {
    pname = "pi-coding-agent-node_modules";
    inherit version src;

    impureEnvVars = lib.fetchers.proxyImpureEnvVars;
    env.NODE_EXTRA_CA_CERTS = "${cacert}/etc/ssl/certs/ca-bundle.crt";

    nativeBuildInputs = [ nodejs writableTmpDirAsHomeHook ];
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

  runtimeBins = lib.makeBinPath [
    ripgrep
    fd
  ];
in
stdenv.mkDerivation {
  pname = "pi-coding-agent";
  inherit version src;

  strictDeps = true;

  # CRITICAL: Bun compiled binaries contain an embedded virtual filesystem
  # (bunfs). Stripping or patching the ELF breaks it — the binary must be
  # installed exactly as produced by `bun build --compile`.
  dontStrip = true;
  dontPatchELF = true;

  env.NODE_EXTRA_CA_CERTS = "${cacert}/etc/ssl/certs/ca-bundle.crt";

  nativeBuildInputs = [
    bun
    nodejs
    makeBinaryWrapper
    writableTmpDirAsHomeHook
  ];

  configurePhase = ''
    runHook preConfigure

    cp -R ${nodeModules}/. ./node_modules/
    chmod -R u+w node_modules
    patchShebangs node_modules >/dev/null

    # Restore gitignored model catalog.
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

  installPhase = ''
    runHook preInstall

    cd packages/coding-agent

    mkdir -p $out/bin $out/lib/pi

    # Compile into a standalone binary matching upstream build-binaries.sh.
    # Without --target, bun embeds its own runtime (nixpkgs bun IS baseline).
    bun build --compile \
      --no-compile-autoload-bunfig \
      ./dist/bun/cli.js \
      ./src/utils/image-resize-worker.ts \
      --outfile $out/bin/pi

    chmod +x $out/bin/pi

    # WASM — loaded at runtime from process.execPath directory.
    cp ../../node_modules/@silvia-odwyer/photon-node/photon_rs_bg.wasm \
      $out/lib/pi/

    # package.json — pi reads VERSION from it; the compiled binary looks
    # in PI_PACKAGE_DIR (set by wrapper below).
    cp package.json $out/lib/pi/

    # Static assets matching upstream release layout.
    mkdir -p $out/lib/pi/theme
    cp dist/modes/interactive/theme/*.json $out/lib/pi/theme/
    mkdir -p $out/lib/pi/assets
    cp dist/modes/interactive/assets/*.png $out/lib/pi/assets/
    cp -r dist/core/export-html $out/lib/pi/
    cp -r docs $out/lib/pi/
    cp -r examples $out/lib/pi/

    # Clipboard native bindings.
    mkdir -p $out/lib/pi/node_modules/@mariozechner
    cp -rL ../../node_modules/@mariozechner/clipboard \
      $out/lib/pi/node_modules/@mariozechner/

    runHook postInstall
  '';

  postFixup = ''
    wrapProgram $out/bin/pi \
      --prefix PATH : "${runtimeBins}" \
      --set PI_PACKAGE_DIR "$out/lib/pi" \
      --set-default PI_SKIP_VERSION_CHECK 1 \
      --set-default PI_TELEMETRY 0
  '';

  doInstallCheck = true;
  nativeInstallCheckInputs = [ versionCheckHook writableTmpDirAsHomeHook ];
  versionCheckKeepEnvironment = [ "HOME" ];
  versionCheckProgramArg = "--version";

  passthru = {
    inherit nodeModules;
  };

  meta = {
    description = "Pi coding agent CLI, compiled binary";
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
