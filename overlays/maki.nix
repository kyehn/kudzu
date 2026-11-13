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
  version = "0.7.1";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    tag = "v${finalAttrs.version}";
    hash = "sha256-Jtpi75JH2LIlrfNTVDwePYNqVuBYRPGyG/f1aZuTmUw=";
  };

  cargoHash = "sha256-5+hgRI3XyPdRcefSokYUXHrgjp2k8i1+9D3lCujm9uk=";

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
