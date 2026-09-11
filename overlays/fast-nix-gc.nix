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
  version = "0-unstable-2026-09-10";

  src = fetchFromGitHub {
    owner = "Mic92";
    repo = "fast-nix-gc";
    rev = "4225a2de3f3b4f1a680d41ad79214b8a973d087b";
    hash = "sha256-IGiThwVbnJRrWkFXngryoDxa0uPZJnP4fU+dfRWWJxk=";
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
