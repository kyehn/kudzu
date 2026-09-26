{
  lib,
  stdenv,
  buildNpmPackage,
  fetchzip,
  autoPatchelfHook,
  makeWrapper,
  nodejs,
  pnpm,
  python3,
  ripgrep,
  bashInteractive,
  versionCheckHook,
}:

buildNpmPackage (finalAttrs: {
  pname = "deepseek-harness";
  version = "0.1.7-rc.2";

  src = fetchzip {
    url = "https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-${finalAttrs.version}.tgz";
    hash = "sha256-G7Y+cbu1J/0//C5BAxuoZHQv8+QmZDHgNK0w2fV6H10=";
  };

  inherit nodejs;

  postPatch = ''
    cp ${./package-lock.json} package-lock.json
  '';

  npmDepsHash = "sha256-uQrFl+XdTkk2LolLqHNIhIYBogcMh+/OvrRN5AiNcLA=";

  dontNpmBuild = true;

  npmRebuildFlags = [ "node-pty" ];

  nativeBuildInputs = [
    autoPatchelfHook
    makeWrapper
    python3
  ];

  buildInputs = [ stdenv.cc.cc.lib ];

  autoPatchelfIgnoreMissingDeps = [ "libc.musl-*.so.1" ];

  postInstall = ''
    bashLib=$(find $out/lib -path '*dsh-terminal-bash/lib/index.js' -print -quit)
    if [ -n "$bashLib" ] && [ -f "$bashLib" ]; then
      substituteInPlace "$bashLib" --replace-quiet '"/bin/bash"' '"${lib.getExe bashInteractive}"'
    else
      echo "dsh-terminal-bash lib/index.js not found under $out/lib" >&2
      find $out/lib -maxdepth 4 -name 'dsh-terminal-bash' >&2 || true
      exit 1
    fi
    wrapProgram $out/bin/dsh \
      --prefix PATH : ${
        lib.makeBinPath [
          pnpm
          ripgrep
        ]
      }
  '';

  nativeInstallCheckInputs = [ versionCheckHook ];
  versionCheckProgramArg = "--version";
  doInstallCheck = true;

  meta = {
    description = "DeepSeek Harness (dsh) — DeepSeek's plugin-based AI agent harness";
    homepage = "https://github.com/deepseek-ai/deepseek-harness";
    changelog = "https://github.com/deepseek-ai/deepseek-harness/releases";
    license = lib.licenses.mit;
    mainProgram = "dsh";
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
  };
})
