{
  lib,
  stdenv,
  fetchurl,
  autoPatchelfHook,
  makeBinaryWrapper,
  fzf,
  ripgrep,
  opencode,
}:

stdenv.mkDerivation (finalAttrs: {
  pname = "opencode-bin";
  version = "1.15.12";

  src = fetchurl {
    url = "https://github.com/anomalyco/opencode/releases/download/v${finalAttrs.version}/opencode-linux-arm64.tar.gz";
    hash = "sha256-7VGBuB6Xj6An2fR81n+Prr7GNCI9f4JKoiYSYYjMvuU=";
  };

  unpackPhase = ''
    runHook preUnpack

    tar -xzf $src

    runHook postUnpack
  '';

  nativeBuildInputs = [
    autoPatchelfHook
    makeBinaryWrapper
  ];

  buildInputs = [ (lib.getLib stdenv.cc.cc) ];

  dontConfigure = true;

  dontBuild = true;

  dontStrip = true;

  installPhase = ''
    runHook preInstall

    install -D --mode=0755 opencode $out/bin/opencode
    wrapProgram $out/bin/opencode \
      --set OPENCODE_DISABLE_DEFAULT_PLUGINS true \
      --set OPENCODE_DISABLE_LSP_DOWNLOAD true \
      --prefix PATH : ${
        lib.makeBinPath [
          fzf
          ripgrep
        ]
      }

    runHook postInstall
  '';

  meta = opencode.meta // {
    sourceProvenance = with lib.sourceTypes; [ binaryNativeCode ];
    platforms = [ "aarch64-linux" ];
  };
})
