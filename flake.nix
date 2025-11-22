{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable-small";
    nixos-hardware.url = "github:NixOS/nixos-hardware/master";
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
    nix = {
      url = "github:DeterminateSystems/nix-src/v3.13.1";
      inputs.nixpkgs.follows = "nixpkgs";
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
    firefox-addons = {
      url = "gitlab:rycee/nur-expressions?dir=pkgs/firefox-addons";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nix-alien = {
      url = "github:thiagokokada/nix-alien";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.nix-index-database.follows = "nix-index-database";
    };
  };

  outputs =
    {
      flake-parts,
      nixpkgs,
      firefox-addons,
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
          formatter = pkgs.nixfmt-tree;

          _module.args.pkgs = import nixpkgs {
            inherit system;
            config = {
              allowUnfree = true;
              allowAliases = false;
              warnUndeclaredOptions = true;
              microsoftVisualStudioLicenseAccepted = true;
            };
            overlays = [
              firefox-addons.overlays.default
              (import ./overlays { inherit inputs; })
            ];
          };

          legacyPackages = pkgs;

          packages.default = pkgs.symlinkJoin {
            name = "default";
            paths = with pkgs; [ coreutils ];
          };
        };

      flake = {
        nixosConfigurations.noirriko = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          specialArgs.inputs = inputs;
          modules = [
            nixos/noirriko/configuration.nix
            home-manager.nixosModules.home-manager
            {
              home-manager = {
                useGlobalPkgs = true;
                useUserPackages = true;
                overwriteBackup = true;
                extraSpecialArgs = { inherit inputs; };
                backupFileExtension = "bak";
                users.uymi.imports = [ home-manager/uymi.nix ];
              };
            }
          ];
        };

        homeConfigurations.uymi = home-manager.lib.homeManagerConfiguration {
          pkgs = import nixpkgs {
            system = "x86_64-linux";
            config = {
              allowUnfree = true;
              allowAliases = false;
              warnUndeclaredOptions = true;
              microsoftVisualStudioLicenseAccepted = true;
            };
            overlays = [
              firefox-addons.overlays.default
              (import ./overlays { inherit inputs; })
            ];
          };
          extraSpecialArgs.inputs = inputs;
          modules = [ home-manager/uymi.nix ];
        };
      };
    };
}
