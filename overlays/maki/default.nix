{
  lib,
  rustPlatform,
  fetchFromGitHub,
  pkg-config,
  perl,
  python3,
  openssl,
  versionCheckHook,
}:

rustPlatform.buildRustPackage (finalAttrs: {
  pname = "maki";
  version = "0.6.3";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    tag = "v${finalAttrs.version}";
    hash = "sha256-HARWyuE8ajvLORYYbpXPM5E64C8+67auLzMdLM9pxwo=";
  };

  cargoHash = "sha256-GUrIXCue02+gjOHML+K4hy5EFr45NyZwcCNcAq77+co=";

  patches = [ ./fix.patch ];

  nativeBuildInputs = [
    pkg-config
    perl
    python3
  ];

  buildInputs = [ openssl ];

  env.OPENSSL_NO_VENDOR = "1";

  doInstallCheck = true;

  nativeInstallCheckInputs = [ versionCheckHook ];

  meta.mainProgram = "maki";
})
