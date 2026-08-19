{
  lib,
  buildNpmPackage,
  nodejs_22,
  makeWrapper,
  dsh-config,
}:

# The @deepseek-ai/dsh CLI plus the two bundled LLM adapter plugins
# (dsh-llm-opencode-zen, dsh-llm-nvidia-nim), packaged as a single npm bundle,
# together with the dsh-acp-paseo ACP bridge that serves the same harness to
# Paseo (model catalog, plan/execute modes, thinking levels and slash commands
# auto-discovered; zero config on the Paseo side).
#
# Build notes:
# - The npm bundle has no top-level build script; the two plugin TypeScript
#   sources and the patch that re-exports serializeRequest/parseSse/translate
#   from dsh-llm-deepseek run in a custom buildPhase, which sits after
#   `npm ci` and before npmInstallHook copies node_modules into $out — so
#   their artifacts reach the store already compiled. The llm-deepseek patch
#   also makes parseSse accept the zen-compat `delta.reasoning` alias (see
#   patch-llm-deepseek.sh); without it the thinking blocks are dropped and the
#   DeepSeek Console rejects the next tool-call turn with "The reasoning_content
#   in the thinking mode must be passed back to the API".
# - The wrapper injects NODE_OPTIONS=--openssl-config=<openssl.cnf> so Node's
#   TLS cipher order matches BoringSSL (the opencode CLI's TLS stack); the
#   openssl.cnf documents exactly how far that alignment goes. Node on every
#   platform (Linux, macOS, Windows) links OpenSSL and honors this file.
# - All runtime configuration is nix-managed: the dsh-acp-paseo profile
#   (bundles, cordis.patch.yml) is generated from the dsh-config derivation
#   output plus the plugin inserts, stored under $out/share/dsh, and seeded
#   into $DSH_HOME only by the launcher wrapper. Nothing writes
#   $DSH_HOME/cordis.patch.yml. Default provider/model choices are env vars
#   (DSH_ACP_PASEO_PROVIDER=opencode-zen, DSH_ACP_PASEO_MODEL=deepseek-v4-flash-free),
#   not configuration data.

let
  pname = "dsh";
  version = "0.1.0-rc.7";
in
buildNpmPackage rec {
  inherit pname version;
  src = ./.;
  nodejs = nodejs_22;

  # Registry dependency set, pinned by package-lock.json (prefetch-npm-deps).
  npmDepsHash = "sha256-cxqgfiKbHBMPfEhcrsGbinh+Rsd85MsoU8KTDnmHizk=";

  dontNpmBuild = true;

  nativeBuildInputs = [ makeWrapper ];

  buildPhase = ''
    runHook preBuild
    bash patch-llm-deepseek.sh node_modules/@deepseek-ai/dsh-llm-deepseek
    node_modules/.bin/tsc -p node_modules/@deepseek-ai/dsh-llm-opencode-zen/tsconfig.json
    node_modules/.bin/tsc -p node_modules/@deepseek-ai/dsh-llm-nvidia-nim/tsconfig.json
    runHook postBuild
  '';

  # Install hook already copied the whole node_modules tree; add the TLS
  # config, the nix-generated profile patch, and the two wrappers.
  postInstall = ''
    mkdir -p "$out/share/dsh" "$out/bin"
    install -m 0644 openssl.cnf "$out/share/dsh/openssl.cnf"
    install -m 0644 paseo-profile-package.json "$out/share/dsh/paseo-profile-package.json"

    # Profile patch = dsh-config (MCP servers, danger-full-access sandbox,
    # never-asking approval — zero provider/model data) + the plugin inserts.
    # formats.yaml.generate puts the YAML file at $out itself.
    cat "${dsh-config}" > "$out/share/dsh/cordis.patch.yml"
    printf '\n- insert:\n    - id: llm-opencode-zen\n      name: %s\n    - id: llm-nvidia-nim\n      name: %s\n' "'@deepseek-ai/dsh-llm-opencode-zen'" "'@deepseek-ai/dsh-llm-nvidia-nim'" >> "$out/share/dsh/cordis.patch.yml"

    cat > "$out/bin/dsh" <<'WRAPPER'
    #!/usr/bin/env bash
    set -euo pipefail
    # Bare dsh CLI (headless profile). Provider plugins must resolve from the
    # profile dependency tree (profiles/node_modules) exactly like dsh-headless
    # does; dsh creates that tree on first profile boot, so prime it with a
    # config dump (no boot), then link the two plugin packages into it.
    home="''${DSH_HOME:-"$HOME/.dsh"}"
    mkdir -p "$home"
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

    cat > "$out/bin/dsh-acp-paseo-launch" <<'WRAPPER'
    #!/usr/bin/env bash
    set -euo pipefail
    # Paseo provider entry: seeds the nix-managed dsh-acp-paseo profile into
    # $DSH_HOME (idempotent), then execs the dsh-acp-paseo launcher, which
    # answers Paseo's --version probe, re-checks the profile bundle and spawns
    # `dsh --profile dsh-acp-paseo`. Default provider/model are env defaults,
    # overridable by the user; nothing is hard-coded in configuration files.
    home="''${DSH_HOME:-"$HOME/.dsh"}"
    node="@node@"
    bundle="@out@/lib/node_modules/dsh-bundle/node_modules"
    mkdir -p "$home/profiles/dsh-acp-paseo" "$home/profiles/node_modules"
    # Profile manifest and patch are regenerated on every run from the store
    # copies, so a rebuilt/GC'd store path never leaves stale configuration.
    install -m 0644 "@out@/share/dsh/paseo-profile-package.json" "$home/profiles/dsh-acp-paseo/package.json"
    install -m 0644 "@out@/share/dsh/cordis.patch.yml" "$home/profiles/dsh-acp-paseo/cordis.patch.yml"

    # Prime the shared profile dependency tree (idempotent) and link the
    # bundles/plugins into it; ln -sfn keeps links pointing at the current
    # store path across rebuilds and garbage collection.
    dshbin="@out@/lib/node_modules/dsh-bundle/node_modules/@deepseek-ai/dsh/lib/bin.js"
    if [ ! -d "$home/profiles/node_modules/.dsh-primed" ]; then
      "$node" --expose-internals "$dshbin" --profile dsh-acp-paseo --dump-config >/dev/null 2>&1 || true
      touch "$home/profiles/node_modules/.dsh-primed"
    fi
    ln -sfn "$bundle/@deepseek-ai/dsh-base" "$home/profiles/node_modules/@deepseek-ai/dsh-base"
    ln -sfn "$bundle/dsh-acp-paseo" "$home/profiles/node_modules/dsh-acp-paseo"
    ln -sfn "$bundle/@deepseek-ai/dsh-llm-opencode-zen" "$home/profiles/node_modules/@deepseek-ai/dsh-llm-opencode-zen"
    ln -sfn "$bundle/@deepseek-ai/dsh-llm-nvidia-nim" "$home/profiles/node_modules/@deepseek-ai/dsh-llm-nvidia-nim"

    export DSH_HOME="$home"
    export DSH_ACP_PASEO_PROVIDER="''${DSH_ACP_PASEO_PROVIDER:-opencode-zen}"
    export DSH_ACP_PASEO_MODEL="''${DSH_ACP_PASEO_MODEL:-deepseek-v4-flash-free}"
    export NODE_OPTIONS="--openssl-config=@out@/share/dsh/openssl.cnf''${NODE_OPTIONS:+ $NODE_OPTIONS}"
    exec "$node" --expose-internals "$bundle/dsh-acp-paseo/bin/dsh-acp-paseo-launch.mjs" "$@"
    WRAPPER
    sed -i "s|@out@|$out|g;s|@node@|${nodejs_22}/bin/node|g" "$out/bin/dsh-acp-paseo-launch"
    chmod +x "$out/bin/dsh-acp-paseo-launch"
  '';

  meta = {
    description = "DeepSeek Harness CLI (dsh) with opencode-zen and NVIDIA NIM adapter plugins, plus the dsh-acp-paseo bridge for Paseo";
    homepage = "https://github.com/deepseek-ai/deepseek-harness";
    license = lib.licenses.mit;
    mainProgram = "dsh";
  };
}
