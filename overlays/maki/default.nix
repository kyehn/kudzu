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
  version = "0.6.0";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    tag = "v${finalAttrs.version}";
    hash = "sha256-VdnGTPhRw8BMREIfSRCcddecZ8/9Ot8pF2mBADmnx0U=";
  };

  cargoHash = "sha256-GXHkaGcXJnC56QHBws70vj5FaBy3yVIHzPmCoZvSPdo=";

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
