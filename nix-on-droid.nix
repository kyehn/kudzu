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
      nix-ld
      rfv
      riffdiff
      time
      typst
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
    motd = null;
    etcBackupExtension = ".bak";
    sessionVariables = {
      EDITOR = "hx";
      LESS = "-SR";
      MANPAGER = "sh -c '${lib.getExe' pkgs.util-linux "col"} -bx | ${lib.getExe pkgs.bat} -l man -p'";
      MANROFFOPT = "-c";
      NIX_LD = "/lib/ld-linux-${pkgs.stdenv.hostPlatform.parsed.cpu.name}.so.1";
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
    "-b /data/data/com.termux.nix/files/usr/${pkgs.glibc}/lib/ld-linux-${pkgs.stdenv.hostPlatform.parsed.cpu.name}.so.1:/lib/ld-linux-${pkgs.stdenv.hostPlatform.parsed.cpu.name}.so.1"
    "-b /data/data/com.termux.nix/files/usr/${pkgs.glibc}/lib/ld-linux-${pkgs.stdenv.hostPlatform.parsed.cpu.name}.so.1:/lib64/ld-linux-${pkgs.stdenv.hostPlatform.parsed.cpu.name}.so.1"
  ];

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
      allow-unsafe-native-code-during-evaluation = true
      always-allow-substitutes = true
      experimental-features = nix-command flakes
      trusted-users =
      lazy-trees = true
      require-sigs = false
      show-trace = true
      warn-dirty = false       
    '';
  };

  terminal.font = "${
    pkgs.maple-mono.Normal-NF-CN.overrideAttrs (_: {
      installPhase = ''
        runHook preInstall

        install MapleMonoNormal-NF-CN-Medium.ttf -D --target-directory $out/share/fonts/truetype

        runHook postInstall
      '';
    })
  }/share/fonts/truetype/MapleMonoNormal-NF-CN-Medium.ttf";

  user.shell = lib.getExe pkgs.fish;

  system.stateVersion = lib.trivial.release;

  time.timeZone = "Etc/GMT-8";
}
