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
  version = "0.6.2";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    tag = "v${finalAttrs.version}";
    hash = "sha256-34pnX/TCdncMrozDKe/BOBSoLnpRnHU/ePKAPpzIc00=";
  };

  cargoHash = "sha256-QGwg03rgcsX7CI9h23ustq1HE9xj5Sw9I1s/rJvFpqM=";

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
