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
  version = "0.7.3";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    tag = "v${finalAttrs.version}";
    hash = "sha256-HSkefH0xY/XipjF2dGWGg2pNbweFH0qyX+88vaeUKmk=";
  };

  cargoHash = "sha256-cgv82OcT6Ub8/7s1h/YN9wCwOXURhc6erf9NviWWAww=";

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
