{
  lib,
  rustPlatform,
  fetchFromGitHub,
  pkg-config,
  perl,
  python3,
  aws-lc,
  openssl,
  versionCheckHook,
}:

rustPlatform.buildRustPackage (finalAttrs: {
  pname = "maki";
  version = "0.7.4";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    tag = "v${finalAttrs.version}";
    hash = "sha256-5TP0cvR9pG+6sd0ZNqTQrIHYEXLzmfEj/TDBI6tWbIA=";
  };

  cargoHash = "sha256-CnF7KAwZOI9TaUJttLyY/FFkniIdidFIN8bHEQULN9M=";

  nativeBuildInputs = [
    pkg-config
    perl
    python3
  ];

  buildInputs = [
    aws-lc
    openssl
  ];

  env.OPENSSL_NO_VENDOR = "1";

  dontCargoCheck = true;

  doInstallCheck = true;

  nativeInstallCheckInputs = [ versionCheckHook ];

  meta.mainProgram = "maki";
})
