{
  lib,
  stdenv,
}:

stdenv.mkDerivation {
  pname = "opencode-wire";
  version = "0.1.0";

  src = lib.fileset.toSource {
    root = ../../.;
    fileset = lib.fileset.unions [
      ./package.json
      ./cordis.patch.yml
      ./src/index.js
    ];
  };

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p $out/lib/opencode-wire/src
    cp $src/dsh/opencode-wire/package.json $src/dsh/opencode-wire/cordis.patch.yml $out/lib/opencode-wire/
    cp $src/dsh/opencode-wire/src/index.js $out/lib/opencode-wire/src/index.js
    runHook postInstall
  '';

  meta = {
    description = "dsh bundle plugin: per-request opencode wire identity over pi-ai routes";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
  };
}
