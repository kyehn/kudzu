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
      uutils-util-linux
      gzip
      less
      uutils-coreutils-noprefix
      uutils-findutils
      uutils-procps
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
    etcBackupExtension = ".bak";
    sessionVariables = {
      EDITOR = "hx";
      LESS = "-SR";
      MANPAGER = "sh -c '${lib.getExe' pkgs.util-linux "col"} -bx | ${lib.getExe pkgs.bat} -l man -p'";
      MANROFFOPT = "-c";
      NIX_LD = pkgs.stdenv.cc.bintools.dynamicLinker;
      NIX_LD_LIBRARY_PATH = lib.makeLibraryPath (
        with pkgs;
        [
          bzip2
          curl
          libsodium
          libssh
          libxml2
          openssl
          stdenv.cc.cc
          util-linux
          xz
          (zlib-ng.override {
            withZlibCompat = true;
          })
          zstd
        ]
      );
    };
  };

  build.extraProotOptions = [
    "-b /data/data/com.termux.nix/files/usr/${pkgs.nix-ld}/libexec/nix-ld:/lib/ld-linux-${pkgs.stdenv.hostPlatform.parsed.cpu.name}.so.1"
    "-b /data/data/com.termux.nix/files/usr/${pkgs.nix-ld}/libexec/nix-ld:/lib64/ld-linux-${pkgs.stdenv.hostPlatform.parsed.cpu.name}.so.1"
  ];

  nix = {
    package = pkgs.nix;
    extraOptions = ''
      allow-unsafe-native-code-during-evaluation = true
      always-allow-substitutes = true
      experimental-features = nix-command flakes
      trusted-users =
      lazy-trees = true
      require-sigs = false
      show-trace = true
      warn-dirty = false
      flake-registry = https://channels.nixos.org/flake-registry.json
      nix-path = nixpkgs=flake:github:NixOS/nixpkgs/nixpkgs-unstable
      substituters = https://nix-community.cachix.org https://cache.nixos.org https://cache.garnix.io https://seilunako.cachix.org
      trusted-public-keys = cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY= nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs= cache.garnix.io:CTFPyKSLcx5RMJKfLo5EEPUObbA78b0YQ2DTCJXqr9g= seilunako.cachix.org-1:e/aJJI1S5hPY/BPeiVZcuPjt5ZjBRRo9dlYHmvwXPFM=
    '';
  };

  user.shell = lib.getExe pkgs.fish;

  time.timeZone = "Etc/GMT-8";
}
