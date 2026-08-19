{
  lib,
  buildNpmPackage,
  nodejs_22,
  makeWrapper,
}:

# The @deepseek-ai/dsh CLI plus the two bundled LLM adapter plugins
# (dsh-llm-opencode-zen, dsh-llm-nvidia-nim), packaged as a single npm bundle,
# together with the deepseek-acp editor-facing ACP adapter.
#
# Build notes:
# - The npm bundle has no top-level build script; the two plugin TypeScript
#   sources and the patch that re-exports serializeRequest/parseSse/translate
#   from dsh-llm-deepseek run in a custom buildPhase, which sits after
#   `npm ci` and before npmInstallHook copies node_modules into $out — so
#   their artifacts reach the store already compiled.
# - `dsh` warns that npm account/session data may exist in package-lock.json;
#   it does not for this lockfile.
# - The wrapper injects NODE_OPTIONS=--openssl-config=<openssl.cnf> so Node's
#   TLS cipher order matches BoringSSL (the opencode CLI's TLS stack); the
#   openssl.cnf documents exactly how far that alignment goes.
# - On first run the wrapper seeds $DSH_HOME/cordis.patch.yml (unless the user
#   already has one) so both provider plugins and the zen default model are
#   active out of the box; DSH_HOME defaults to ~/.dsh.

let
  pname = "dsh";
  version = "0.1.0-rc.7";
in
buildNpmPackage rec {
  inherit pname version;
  src = ./.;
  nodejs = nodejs_22;

  # Registry dependency set, pinned by package-lock.json (prefetch-npm-deps).
  npmDepsHash = "sha256-RylpHQjxcKToCNzU7y5HUbbVyiQ38Exr8P0Ez2UaWpw=";

  dontNpmBuild = true;

  nativeBuildInputs = [ makeWrapper ];

  buildPhase = ''
    runHook preBuild
    bash patch-llm-deepseek.sh node_modules/@deepseek-ai/dsh-llm-deepseek
    node_modules/.bin/tsc -p node_modules/@deepseek-ai/dsh-llm-opencode-zen/tsconfig.json
    node_modules/.bin/tsc -p node_modules/@deepseek-ai/dsh-llm-nvidia-nim/tsconfig.json
    bash patch-deepseek-acp.sh node_modules/deepseek-acp
    runHook postBuild
  '';

  # Install hook already copied the whole node_modules tree; add the TLS
  # config, the first-run defaults, and the `dsh` wrapper.
  postInstall = ''
        mkdir -p "$out/share/dsh/dsh-home" "$out/bin"
        install -m 0644 openssl.cnf "$out/share/dsh/openssl.cnf"
        install -m 0644 dsh-home/cordis.patch.yml "$out/share/dsh/dsh-home/cordis.patch.yml"

        cat > "$out/bin/dsh" <<'WRAPPER'
    #!/usr/bin/env bash
    set -euo pipefail
    # Home-layer patch default: seed $DSH_HOME/cordis.patch.yml once so both
    # plugins and the zen default model are active out of the box; a user file
    # (or a later dsh-config run) is never overwritten.
    home="''${DSH_HOME:-"$HOME/.dsh"}"
    mkdir -p "$home"
    if [ ! -f "$home/cordis.patch.yml" ]; then
      cp "@out@/share/dsh/dsh-home/cordis.patch.yml" "$home/cordis.patch.yml"
    fi

    # The bundled provider plugins must resolve from the profile dependency tree
    # (profiles/node_modules) exactly like dsh-headless does. dsh creates that
    # tree on its first profile boot, so prime it with a config dump (no boot),
    # then link the two plugin packages into it; ln -sfn keeps the links pointing
    # at the current store path across rebuilds and garbage collection.
    node="@node@"
    bin="@out@/lib/node_modules/dsh-bundle/node_modules/@deepseek-ai/dsh/lib/bin.js"
    plugins="@out@/lib/node_modules/dsh-bundle/node_modules/@deepseek-ai"
    if [ ! -d "$home/profiles/node_modules" ]; then
      "$node" --expose-internals "$bin" --profile headless --dump-config >/dev/null 2>&1 || true
    fi
    mkdir -p "$home/profiles/node_modules/@deepseek-ai"
    ln -sfn "$plugins/dsh-llm-opencode-zen" "$home/profiles/node_modules/@deepseek-ai/dsh-llm-opencode-zen"
    ln -sfn "$plugins/dsh-llm-nvidia-nim" "$home/profiles/node_modules/@deepseek-ai/dsh-llm-nvidia-nim"

    export DSH_HOME="$home"
    # Align Node's TLS cipher order with BoringSSL (opencode CLI stack). Any
    # user-supplied NODE_OPTIONS are preserved after ours.
    export NODE_OPTIONS="--openssl-config=@out@/share/dsh/openssl.cnf''${NODE_OPTIONS:+ $NODE_OPTIONS}"
    # --expose-internals cannot go through NODE_OPTIONS, so pass it explicitly:
    # dsh's HMR watch service resolves Node internals through it, while the
    # bundled node-addon-require-builtin fallback fails on nixpkgs-built Node.
    exec "$node" --expose-internals "$bin" "$@"
    WRAPPER
        sed -i "s|@out@|$out|g;s|@node@|${nodejs_22}/bin/node|g" "$out/bin/dsh"
        chmod +x "$out/bin/dsh"

        # deepseek-acp: the editor-facing ACP adapter (xintaofei/deepseek-acp).
        # It boots the dsh kernel from the same npm tree and speaks ACP over
        # stdio; the wrapper shares the DSH_HOME convention (sessions and
        # .credentials.yaml) and the BoringSSL cipher-order alignment.
        cat > "$out/bin/deepseek-acp" <<'WRAPPER'
    #!/usr/bin/env bash
    set -euo pipefail
    home="''${DSH_HOME:-"$HOME/.dsh"}"
    mkdir -p "$home"
    export DSH_HOME="$home"
    # Default to the keyless zen free channel instead of the DeepSeek official
    # API, which would need DEEPSEEK_API_KEY. Explicit user settings win.
    export DEEPSEEK_ACP_PROVIDER="''${DEEPSEEK_ACP_PROVIDER:-opencode-zen}"
    export DEEPSEEK_ACP_MODEL="''${DEEPSEEK_ACP_MODEL:-deepseek-v4-flash-free}"
    export NODE_OPTIONS="--openssl-config=@out@/share/dsh/openssl.cnf''${NODE_OPTIONS:+ $NODE_OPTIONS}"
    exec "@node@" "@out@/lib/node_modules/dsh-bundle/node_modules/deepseek-acp/lib/bin.js" "$@"
    WRAPPER
        sed -i "s|@out@|$out|g;s|@node@|${nodejs_22}/bin/node|g" "$out/bin/deepseek-acp"
        chmod +x "$out/bin/deepseek-acp"
  '';

  meta = {
    description = "DeepSeek Harness CLI (dsh) with opencode-zen and NVIDIA NIM adapter plugins, plus the deepseek-acp editor adapter";
    homepage = "https://github.com/deepseek-ai/deepseek-harness";
    license = lib.licenses.mit;
    mainProgram = "dsh";
  };
}
