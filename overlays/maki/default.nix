{
  lib,
  rustPlatform,
  fetchFromGitHub,
  pkg-config,
  perl,
  python3,
  openssl,
}:

rustPlatform.buildRustPackage (finalAttrs: {
  pname = "maki";
  version = "0.5.5";

  src = fetchFromGitHub {
    owner = "tontinton";
    repo = "maki";
    rev = "v${finalAttrs.version}";
    hash = "sha256-6IEdSMLeL0dmDynBS3qCEPxrW8wN/FyJDgojjqmZn7g=";
  };

  cargoHash = "sha256-Y30sGDJyA3SRWxBQLqBhSW7zyAYdAh4qFzLcuEWkeYM=";

  patches = [ ./fix.patch ];

  nativeBuildInputs = [
    pkg-config
    perl
    python3
  ];

  buildInputs = [
    openssl
  ];

  # isahc pulls openssl-sys with `static-ssl`, which would compile a vendored
  # OpenSSL from source. Point it at nixpkgs openssl instead (same as the
  # upstream devShell's OPENSSL_NO_VENDOR=1).
  env.OPENSSL_NO_VENDOR = "1";

  doInstallCheck = true;

  installCheckPhase = ''
    runHook preInstallCheck
    "$out/bin/maki" --version
    runHook postInstallCheck
  '';

  meta = {
    description = "AI coding agent with native Rust TUI";
    homepage = "https://maki.sh";
    license = lib.licenses.mit;
    mainProgram = "maki";
  };
})
