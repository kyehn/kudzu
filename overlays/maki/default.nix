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
  version = "0.5.6";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    tag = "v${finalAttrs.version}";
    hash = "sha256-p3OS5A6VvXiVo8uPoD1dgbUNUnct1+xIEfZPkToFBtk=";
  };

  cargoHash = "sha256-kpuCfHdLdJWjLLSbK5o1Zz/U60aWP7SaW9324ShQkp4=";

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
