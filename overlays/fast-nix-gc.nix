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
  version = "0-unstable-2026-10-01";

  src = fetchFromGitHub {
    owner = "Mic92";
    repo = "fast-nix-gc";
    rev = "78aeb273d682ae18197f7036ca8e03a2715568fc";
    hash = "sha256-wnFAQIAnjxqXUtkhdxSwegmI3kmDg23zrqsl5iI/jgA=";
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
