{
  lib,
  rustPlatform,
  pkg-config,
  nix,
  sqlite,
  fetchFromGitHub,
}:

rustPlatform.buildRustPackage (finalAttrs: {
  pname = "fast-nix-gc";
  version = "0-unstable-2026-08-20";

  src = fetchFromGitHub {
    owner = "Mic92";
    repo = "fast-nix-gc";
    rev = "68287b2eb3ff360daead3e879568a9e26df5bfb1";
    hash = "sha256-AiAvfCRAeUMHmhUaKbtKhKyEmLJ2whreUP2XG2xgj8U=";
  };

  cargoHash = "sha256-18tDUm75DZHfKrlPj57rpwYVboWfOdI5jCzqRlNN7fY=";

  nativeBuildInputs = [ pkg-config ];

  buildInputs = [
    nix
    sqlite
  ];

  cargoBuildFlags = [
    "--package"
    "fast-nix-gc"
    "--package"
    "fast-nix-optimise"
  ];

  cargoTestFlags = [
    "--package"
    "fast-nix-gc"
    "--package"
    "fast-nix-common"
    "--package"
    "fast-nix-optimise"
  ];

  meta.mainProgram = "fast-nix-gc";
})
