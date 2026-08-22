# pi-coding-agent, packaged to run with Bun.
#
# Pattern: npm ci FOD (node_modules) + offline workspace build, following the
# lukasl/pi.nix Bun approach for installPhase — copy the entire node_modules
# tree to the output so all runtime dependencies (chalk, commander, etc.) are
# present; overlay workspace packages with their built dist/.
#
# Runtime layout:
#   $out/bin/pi                                    bun → dist/cli.js wrapper
#   $out/lib/node_modules/@earendil-works/pi-*/dist/   built workspace JS
#   $out/lib/node_modules/...                      all npm runtime deps
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

  # Hydrated provider model catalog shipped in the published pi-ai package.
  modelData = fetchurl {
    url = "https://registry.npmjs.org/@earendil-works/pi-ai/-/pi-ai-${version}.tgz";
    hash = "sha256-AmJ4Wnaw6y7sWWzYp6su4j7vidLvG7EhHE8KGUTaz0E=";
  };

  # node_modules FOD — network only here, fixed output.
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

    # Workspace symlinks point back into packages/*, absent in this FOD by
    # construction. The main derivation has the tree and rebuilds those
    # workspaces before packaging.
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
  pname = "pi-coding-agent-bun";
  inherit version src;

  strictDeps = true;

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

    # Restore gitignored model catalog from the published pi-ai tarball.
    mkdir -p packages/ai/src/providers/data
    tar --extract --gzip --file=${modelData} \
      --directory=packages/ai/src/providers/data \
      --strip-components=4 \
      package/dist/providers/data

    runHook postConfigure
  '';

  # Workspace build order: tsgo for deps, npm run build for coding-agent.
  # pi-ai uses tsgo directly — its npm build script would re-fetch the model
  # catalog over the network, which modelData above already supplies.
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

  # Follow the lukasl/pi.nix pattern: copy the entire node_modules tree
  # (including all runtime deps like chalk, commander, etc.) to the output,
  # then overlay workspace packages with their built dist/.
  installPhase = ''
    runHook preInstall

    mkdir -p $out/lib/node_modules/@earendil-works

    # Stage built workspace dist + package.json.
    for pkg in tui telemetry ai agent protocol client coding-agent; do
      [ -d "packages/$pkg/dist" ] || continue
      mkdir -p "$out/lib/node_modules/@earendil-works/pi-$pkg"
      cp -r packages/$pkg/dist "$out/lib/node_modules/@earendil-works/pi-$pkg/"
      cp packages/$pkg/package.json "$out/lib/node_modules/@earendil-works/pi-$pkg/"
    done

    # Copy the full node_modules tree (following symlinks with -L for
    # workspace packages). This gives us ALL runtime deps: chalk, commander,
    # @silvia-odwyer/photon-node/photon_rs_bg.wasm, etc.
    cp -rL node_modules/. "$out/lib/node_modules/"

    # Wrapper: bun executes the coding-agent entry point.
    mkdir -p $out/bin
    makeWrapper ${lib.getExe bun} $out/bin/pi \
      --add-flags "$out/lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js" \
      --prefix PATH : "${runtimeBins}" \
      --set-default PI_SKIP_VERSION_CHECK 1 \
      --set-default PI_TELEMETRY 0

    runHook postInstall
  '';

  doInstallCheck = true;
  nativeInstallCheckInputs = [ versionCheckHook writableTmpDirAsHomeHook ];
  versionCheckKeepEnvironment = [ "HOME" ];
  versionCheckProgramArg = "--version";

  passthru = {
    inherit nodeModules;
  };

  meta = {
    description = "Pi coding agent CLI, running on Bun";
    homepage = "https://pi.dev/";
    license = lib.licenses.mit;
    mainProgram = "pi";
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
  };
}
