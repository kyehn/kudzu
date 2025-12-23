{
  inputs,
  lib,
  pkgs,
  ...
}:

{
  environment = {
    packages = with pkgs; [
      typst
      age
      rfv
      riffdiff
      (lib.hiPrio gnused)
      (lib.hiPrio gnugrep)
      busybox
      (lib.hiPrio uutils-coreutils-noprefix)
      (lib.hiPrio uutils-findutils)
      comma
      (python313.withPackages (
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
    motd = null;
    etcBackupExtension = ".bak";
    sessionVariables = {
      EDITOR = "hx";
      LESS = "-SR";
      MANPAGER = "sh -c 'col -bx | ${lib.getExe pkgs.bat} -l man -p'";
      MANROFFOPT = "-c";
    };
  };

  android-integration = {
    xdg-open.enable = true;
    termux-open-url.enable = true;
    am.enable = true;
    termux-open.enable = true;
  };

  nix = {
    package = pkgs.nix;
    substituters = lib.mkForce [
      "https://mirrors.ustc.edu.cn/nix-channels/store"
      "https://nix-community.cachix.org"
      "https://cache.garnix.io"
      "https://cache.nixos.org"
      "https://seilunako.cachix.org"
    ];
    trustedPublicKeys = lib.mkForce [
      "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
      "cache.garnix.io:CTFPyKSLcx5RMJKfLo5EEPUObbA78b0YQ2DTCJXqr9g="
      "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
      "seilunako.cachix.org-1:e/aJJI1S5hPY/BPeiVZcuPjt5ZjBRRo9dlYHmvwXPFM="
    ];
    nixPath = [ "nixpkgs=${pkgs.path}" ];
    extraOptions = ''
      always-allow-substitutes = true
      experimental-features = nix-command flakes
      trusted-users =
      lazy-trees = true
      require-sigs = false
      show-trace = true
      warn-dirty = false       
    '';
  };

  user.shell = lib.getExe pkgs.fish;

  system.stateVersion = lib.trivial.release;

  time.timeZone = "Etc/GMT-8";
}
