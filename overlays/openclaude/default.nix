{
  lib,
  buildNpmPackage,
  fetchFromGitHub,
  nodejs_22,
  bun,
}:

buildNpmPackage (finalAttrs: {
  pname = "openclaude";
  version = "0.11.0";

  src = fetchFromGitHub {
    owner = "Gitlawb";
    repo = "openclaude";
    tag = "v${finalAttrs.version}";
    hash = "sha256-4nRERC574JVf8Wvi2PdIPYnlao9m8/rGte7ReYR0dtw=";
  };

  nodejs = nodejs_22;

  npmDepsHash = "sha256-mBDr+tLoIscL5C8JhmhgYzSztuQVGoMEPsh47LDhTXI=";

  nativeBuildInputs = [ bun ];

  npmFlags = [ "--ignore-scripts" ];

  npmBuildScript = "build";

  postPatch = ''
    cp ${./package-lock.json} package-lock.json
  '';

  meta.mainProgram = "openclaude";
})
