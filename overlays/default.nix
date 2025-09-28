{ inputs, ... }:
final: prev: {
  e-search = prev.callPackage ./e-search.nix { };
  navicat-premium = prev.callPackage ./navicat-premium.nix { };
  cheating-daddy = prev.callPackage ./cheating-daddy.nix { };
  bilibili = prev.bilibili.overrideAttrs (oldAttrs: {
    nativeBuildInputs = oldAttrs.nativeBuildInputs ++ [ prev.autoPatchelfHook ];

    buildInputs = (oldAttrs.buildInputs or [ ]) ++ [
      prev.libinput
      prev.libx11
      prev.xorg.libXtst
      (prev.lib.getLib prev.stdenv.cc.cc)
    ];

    installPhase = ''
      runHook preInstall

      mkdir --parents $out/libexec $out/bin
      substituteInPlace usr/share/applications/io.github.msojocs.bilibili.desktop \
        --replace-fail "/opt/apps/io.github.msojocs.bilibili/files/bin//bin/bilibili" "bilibili"
      cp --recursive usr/share $out/share
      cp --recursive opt/apps/io.github.msojocs.bilibili/files/bin/app $out/libexec/bilibili
      makeWrapper ${prev.lib.getExe prev.electron} $out/bin/bilibili \
        --argv0 bilibili \
        --prefix LD_LIBRARY_PATH : ${prev.lib.makeLibraryPath [ prev.libva ]} \
        --set-default ELECTRON_FORCE_IS_PACKAGED true \
        --set-default ELECTRON_IS_DEV 0 \
        --add-flags $out/libexec/bilibili/app.asar \
        --add-flags --enable-features=AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL

      runHook postInstall
    '';
  });
  nautilus = prev.nautilus.overrideAttrs (oldAttrs: {
    postPatch = (oldAttrs.postPatch or "") + ''
      sed -i '/static void\s*action_send_email/,/^\}/d' src/nautilus-files-view.c
      sed -i '/\.name = "send-email"/d' src/nautilus-files-view.c
      sed -i '/action = g_action_map_lookup_action.*(view_action_group, "send-email");/,/^\s*}$/d' src/nautilus-files-view.c
    '';
  });
  nix = inputs.nix.packages."${prev.stdenv.hostPlatform.system}".default;
  orchis-theme = prev.orchis-theme.overrideAttrs (oldAttrs: {
    installPhase = ''
      runHook preInstall

      bash install.sh -d $out/share/themes -t default green --tweaks solid macos compact black primary submenu nord

      runHook postInstall
    '';
  });
  rfv = prev.writeShellScriptBin "rfv" (
    builtins.readFile (
      prev.replaceVars ./rfv {
        rg = "${prev.ripgrep}/bin/rg";
        fzf = "${prev.fzf}/bin/fzf";
        hx = "${prev.helix}/bin/hx";
        bat = "${prev.bat}/bin/bat";
      }
    )
  );
  fhs = (
    prev.buildFHSEnv (
      prev.appimageTools.defaultFhsEnvArgs
      // {
        name = "fhs";
        targetPkgs =
          pkgs: (prev.appimageTools.defaultFhsEnvArgs.targetPkgs pkgs) ++ (with pkgs; [ webkitgtk_4_1 ]);
        runScript = "fish --interactive";
        extraOutputsToInstall = [ "dev" ];
      }
    )
  );
}
