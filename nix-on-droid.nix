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
    substituters = [
      "https://mirrors.ustc.edu.cn/nix-channels/store"
      "https://nix-community.cachix.org"
      "https://cache.garnix.io"
      "https://seilunako.cachix.org"
    ];
    trustedPublicKeys = [
      "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
      "cache.garnix.io:CTFPyKSLcx5RMJKfLo5EEPUObbA78b0YQ2DTCJXqr9g="
      "seilunako.cachix.org-1:e/aJJI1S5hPY/BPeiVZcuPjt5ZjBRRo9dlYHmvwXPFM="
    ];
    nixPath = [ "nixpkgs=${pkgs.path}" ];
    extraOptions = ''
      always-allow-substitutes = true
      auto-allocate-uids = true
      experimental-features = nix-command flakes auto-allocate-uids
      eval-cores = 0
      lazy-trees = true
      min-free = 10240
      require-sigs = false
      show-trace = true
      warn-dirty = false       
    '';
  };

  user.shell = lib.getExe pkgs.fish;

  system.stateVersion = lib.trivial.release;

  time.timeZone = "Etc/GMT-8";
}
