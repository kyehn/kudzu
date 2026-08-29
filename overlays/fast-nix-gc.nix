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
  version = "0-unstable-2026-08-27";

  src = fetchFromGitHub {
    owner = "Mic92";
    repo = "fast-nix-gc";
    rev = "217094c7568a288a91de06ea09fc27b825fff13e";
    hash = "sha256-cWKRacO/FdQqI/CZiAd7VHFdihLt3Am6+edgcTgxs9Y=";
  };

  cargoHash = "sha256-bHMR29uAAy0lUkqRIxv0GFqCe2ljA/UEsmzVillidkU=";

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
