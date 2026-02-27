{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
    nix = {
      url = "github:DeterminateSystems/nix-src/v3.16.3";
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
      inputs.home-manager.follows = "home-manager";
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
      systems = nixpkgs.lib.systems.flakeExposed;

      perSystem =
        {
          pkgs,
          system,
          ...
        }:
        {
          formatter = pkgs.nixfmt-tree.override {
            runtimeInputs = [ pkgs.yamlfmt ];
            settings = {
              formatter.yamlfmt = {
                command = "yamlfmt";
                includes = [
                  "*.yaml"
                  "*.yml"
                ];
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
        nixOnDroidConfigurations.default = nix-on-droid.lib.nixOnDroidConfiguration {
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
          modules = [
            ./nix-on-droid.nix
            {
              home-manager = {
                useGlobalPkgs = true;
                useUserPackages = true;
                extraSpecialArgs = { inherit inputs; };
                backupFileExtension = "bak";
                overwriteBackup = true;
                config = ./home-manager.nix;
              };
            }
          ];
        };
      };
    };
}
