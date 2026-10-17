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
  version = "0.6.4";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    tag = "v${finalAttrs.version}";
    hash = "sha256-dCIsPwD6xCIh+etbybpTkf0NtCRBG4icdpDgsNazIAE=";
  };

  cargoHash = "sha256-auo1N+ZEIDLVDbMP24MZcnG0kmNuAPt3waAus09OLic=";

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
