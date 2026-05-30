{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
    nix = {
      url = "github:DeterminateSystems/nix-src/v3.21.0";
      # inputs.nixpkgs.follows = "nixpkgs";
      inputs.nixpkgs-regression.follows = "nixpkgs";
      inputs.nixpkgs-23-11.follows = "nixpkgs";
      inputs.flake-parts.follows = "flake-parts";
    };
    home-manager = {
      url = "github:nix-community/home-manager/master";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nix-index-database = {
      url = "github:Mic92/nix-index-database";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nix-on-droid = {
      url = "github:kyehn/nix-on-droid";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.flake-parts.follows = "flake-parts";
    };
  };

  outputs =
    {
      flake-parts,
      nixpkgs,
      nix-on-droid,
      home-manager,
      ...
    }@inputs:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = builtins.filter (system: system != "x86_64-darwin") nixpkgs.lib.systems.flakeExposed;

      perSystem =
        {
          pkgs,
          system,
          ...
        }:
        {
          formatter = pkgs.nixfmt-tree.override {
            nixfmtPackage = pkgs.nixfmt-rs;
            runtimeInputs = with pkgs; [
              yamlfmt
              biome
            ];
            settings.formatter = {
              yamlfmt = {
                command = "yamlfmt";
                includes = [
                  "*.yaml"
                  "*.yml"
                ];
              };
              biome = {
                command = "biome";
                options = [
                  "check"
                  "--write"
                ];
                includes = [ "*.json" ];
              };
            };
          };

          _module.args.pkgs = import nixpkgs {
            inherit system;
            config = {
              allowUnfree = true;
              allowAliases = false;
              warnUndeclaredOptions = true;
            };
            overlays = [
              (import ./overlays { inherit inputs; })
            ];
          };

          legacyPackages = pkgs;

          packages.default = pkgs.symlinkJoin {
            name = "default";
            paths = with pkgs; [ nix ];
          };
        };

      flake = {
        nixosConfigurations.default = nix-on-droid.lib.nixOnDroidConfiguration {
          pkgs = import nixpkgs {
            system = builtins.currentSystem;
            config = {
              allowUnfree = true;
              allowAliases = false;
              warnUndeclaredOptions = true;
            };
            overlays = [
              (import ./overlays { inherit inputs; })
            ];
          };
          extraSpecialArgs = { inherit inputs; };
          modules = [
            ./nix-on-droid.nix
            "${inputs.nix-on-droid}/modules/home-manager.nix"
            "${inputs.home-manager}/nixos/common.nix"
            {
              home-manager = {
                useGlobalPkgs = true;
                useUserPackages = true;
                extraSpecialArgs = { inherit inputs; };
                backupFileExtension = "bak";
                overwriteBackup = true;
                users.nix-on-droid.imports = [ ./home-manager.nix ];
              };
            }
          ];
        };
      };
    };
}
