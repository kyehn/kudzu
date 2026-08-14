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
  version = "0-unstable-2026-08-13";

  src = fetchFromGitHub {
    owner = "Mic92";
    repo = "fast-nix-gc";
    rev = "254a2ba0a4f1570b3880bc10bb6166afe1e25936";
    hash = "sha256-KNAjsTgfweOoqYxMAsIolrDcIV5AikvrSW9EpJ7fnK8=";
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
