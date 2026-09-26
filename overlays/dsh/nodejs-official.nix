{
  lib,
  stdenv,
  autoPatchelfHook,
  nodejs_22,
}:

stdenv.mkDerivation (finalAttrs: {
  pname = "nodejs-official";
  version = "22.23.2";

  src =
    {
      x86_64-linux = builtins.fetchurl {
        url = "https://nodejs.org/dist/v${finalAttrs.version}/node-v${finalAttrs.version}-linux-x64.tar.xz";
        sha256 = "01zk0d5ly8abclcyfparfl47lfbl1ldy085dn15jaci91bhcy2nn";
      };
      aarch64-linux = builtins.fetchurl {
        url = "https://nodejs.org/dist/v${finalAttrs.version}/node-v${finalAttrs.version}-linux-arm64.tar.xz";
        sha256 = "1f5bji7aai77q59gx4zv9f97405wndyxp21cz5vqarggbn60gx7z";
      };
    }
    .${stdenv.hostPlatform.system}
      or (throw "nodejs-official: unsupported system ${stdenv.hostPlatform.system}");

  dontConfigure = true;
  dontBuild = true;

  nativeBuildInputs = [ autoPatchelfHook ];
  buildInputs = [ stdenv.cc.cc.lib ];

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    cp -r bin include lib share $out/
    # npm-cli.js keeps `#!/usr/bin/env node`, which the sandbox cannot
    # resolve; point it at this package's own node directly.
    substituteInPlace $out/lib/node_modules/npm/bin/npm-cli.js \
      --replace-quiet '#!/usr/bin/env node' "#!$out/bin/node"
    substituteInPlace $out/lib/node_modules/npm/bin/npx-cli.js \
      --replace-quiet '#!/usr/bin/env node' "#!$out/bin/node"
    patchShebangs --host $out/bin
    runHook postInstall
  '';

  python = nodejs_22.python;

  meta = {
    description = "Node.js ${finalAttrs.version} official binary (V8 codegen required by dsh native loader)";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
  };
})
