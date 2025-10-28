{ inputs, ... }:

final: prev: {
  navicat-premium = prev.navicat-premium.overrideAttrs (oldAttrs: {
    src = prev.appimageTools.extractType2 {
      inherit (oldAttrs) pname version;
      src = prev.fetchurl {
        url = "https://dn.navicat.com/download/navicat17-premium-cs-x86_64.AppImage";
        hash = "sha256-699JZn+EJcSfsz6iOgEwrm7dDktTHcXR+g2iDF6LLPE=";
      };
    };
  });
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
        --add-flags "\''${NIXOS_OZONE_WL:+\''${WAYLAND_DISPLAY:+--ozone-platform-hint=auto --enable-features=WaylandWindowDecorations --enable-wayland-ime=true --wayland-text-input-version=3}}" \
        --add-flags "--enable-features=AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL"

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
        rg = prev.lib.getExe prev.ripgrep;
        fzf = prev.lib.getExe prev.fzf;
        hx = prev.lib.getExe prev.helix;
        bat = prev.lib.getExe prev.bat;
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
