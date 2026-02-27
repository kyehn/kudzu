{
  inputs,
  lib,
  pkgs,
  ...
}:

{
  environment = {
    packages = with pkgs; [
      age
      bashInteractive
      comma
      curl
      uutils-diffutils
      gawk
      gnugrep
      gnupatch
      gnused
      util-linux
      gzip
      less
      uutils-coreutils-noprefix
      uutils-findutils
      procps
      ncurses
      netcat-openbsd
      openssh
      opencode
      rfv
      riffdiff
      time
      which
      (python314.withPackages (
        ps: with ps; [
          requests
          python-dotenv
        ]
      ))
      (pkgs.writeShellScriptBin "patchedpython" ''
        export LD_LIBRARY_PATH=$NIX_LD_LIBRARY_PATH
        exec python $@
      '')
    ];
    sessionVariables = {
      EDITOR = "hx";
      LESS = "-SR";
      MANPAGER = "sh -c '${lib.getExe' pkgs.util-linux "col"} -bx | ${lib.getExe pkgs.bat} -l man -p'";
      MANROFFOPT = "-c";
    };
  };

  nix = {
    package = pkgs.nix;
    settings = {
      substituters = lib.mkForce [
        "https://nix-community.cachix.org"
        "https://cache.nixos.org"
        "https://cache.garnix.io"
        "https://seilunako.cachix.org"
      ];
      trusted-public-keys = lib.mkForce [
        "cache.nixos.org-1:6NCHD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
        "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
        "cache.garnix.io:CTFPyKSLcx5RMJKfLo5EEPUObbA78b0YQ2DTCJXqr9g="
        "seilunako.cachix.org-1:e/aJJI1S5hPY/BPeiVZcuPjt5ZjBRRo9dlYHmvwXPFM="
      ];
    };
    extraOptions = lib.mkForce ''
      always-allow-substitutes = true
      builders-use-substitutes = true
      lazy-trees = true
      show-trace = true
      warn-dirty = false
      flake-registry = ${
        pkgs.writeText "flake-registry.json" (
          builtins.toJSON {
            version = 2;
            flakes = map (name: {
              from = {
                id = name;
                type = "indirect";
              };
              to = {
                type = "path";
                path = inputs.${name};
              };
            }) (builtins.filter (name: name != "self") (builtins.attrNames inputs));
          }
        )
      }
      nix-path = nixpkgs=${inputs.nixpkgs}
    '';
  };

  user.shell = lib.getExe pkgs.fish;

  time.timeZone = "Etc/GMT-8";
}
