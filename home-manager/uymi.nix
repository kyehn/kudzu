{
  inputs,
  pkgs,
  lib,
  ...
}:

let
  username = "uymi";
  cursorName = "Bibata-Modern-Classic";
  cursorPackage = pkgs.bibata-cursors;
  cursorSize = 24;
in
{
  imports = [
    inputs.nix-index-database.homeModules.nix-index
  ]
  ++ [
    modules/fish
    modules/color
    modules/dconf.nix
    modules/librewolf.nix
  ];

  home = {
    username = username;
    homeDirectory = "/home/${username}";
    stateVersion = lib.trivial.release;
    pointerCursor = {
      name = cursorName;
      package = cursorPackage;
      size = cursorSize;
      gtk.enable = true;
      x11 = {
        enable = true;
        defaultCursor = cursorName;
      };
    };
    language.base = "zh_CN.UTF-8";
    file.".yarnrc.yml".text = ''
      npmRegistryServer: "https://npmreg.proxy.ustclug.org"
      enableTelemetry: false
    '';
  };

  gtk.cursorTheme = {
    name = cursorName;
    size = cursorSize;
  };

  xdg = {
    userDirs = {
      enable = true;
      createDirectories = true;
      templates = null;
      publicShare = null;
      desktop = null;
    };
    mimeApps = {
      enable = true;
      defaultApplications =
        let
          browser = [ "librewolf.desktop" ];
          image = [ "org.gnome.Loupe.desktop" ];
        in
        {
          "text/html" = browser;
          "application/pdf" = browser;
          "x-scheme-handler/http" = browser;
          "x-scheme-handler/https" = browser;
          "image/jpeg" = image;
          "image/png" = image;
          "image/gif" = image;
          "image/webp" = image;
          "image/tiff" = image;
          "image/bmp" = image;
          "image/vnd-ms.dds" = image;
          "image/vnd.microsoft.icon" = image;
          "image/vnd.radiance" = image;
          "image/x-exr" = image;
          "image/x-dds" = image;
          "image/x-tga" = image;
          "image/x-portable-bitmap" = image;
          "image/x-portable-graymap" = image;
          "image/x-portable-pixmap" = image;
          "image/x-portable-anymap" = image;
          "image/x-qoi" = image;
          "image/svg+xml" = image;
          "image/svg+xml-compressed" = image;
          "image/avif" = image;
          "image/heic" = image;
          "image/jxl" = image;
        };
      associations.removed = {
        "application/x-zerosize" = "org.gnome.TextEditor.desktop";
        "x-content/unix-software" = "nautilus-autorun-software.desktop";
        "x-scheme-handler/unknown" = "chromium-browser.desktop";
        "x-scheme-handler/mailto" = "chromium-browser.desktop";
        "x-scheme-handler/webcal" = "chromium-browser.desktop";
        "x-scheme-handler/about" = "chromium-browser.desktop";
        "x-scheme-handler/rlogin" = "ktelnetservice6.desktop";
        "x-scheme-handler/ssh" = "ktelnetservice6.desktop";
        "x-scheme-handler/telnet" = "ktelnetservice6.desktop";
        "audio/x-mod" = "io.github.celluloid_player.Celluloid.desktop";
      };
    };
    desktopEntries = {
      fish = {
        name = "fish";
        noDisplay = true;
      };
      "org.fcitx.Fcitx5" = {
        name = "org.fcitx.Fcitx5";
        noDisplay = true;
      };
      "org.fcitx.fcitx5-migrator" = {
        name = "org.fcitx.fcitx5-migrator";
        noDisplay = true;
      };
      htop = {
        name = "htop";
        noDisplay = true;
      };
      kbd-layout-viewer5 = {
        name = "kbd-layout-viewer5";
        noDisplay = true;
      };
      cups = {
        name = "cups";
        noDisplay = true;
      };
    };
    configFile = {
      "nixpkgs/config.nix".text = ''
        {
          allowUnfree = true;
          android_sdk.accept_license = true;
        }
      '';
      "pip/pip.conf".text = ''
        [global]
        index-url = https://mirror.nju.edu.cn/pypi/web/simple
      '';
      "variety/variety.conf".text = lib.generators.toINIWithGlobalSection { } {
        globalSection = {
          change_on_start = "True";
          change_enabled = "False";
          change_interval = 86400;
          internet_enabled = "True";
          wallpaper_display_mode = "smart";
        };
        sections.sources.src10 = "True|wallhaven|anime girls";
      };
    };
  };

  programs = {
    man.generateCaches = false;
    nix-index = {
      enableBashIntegration = false;
      enableFishIntegration = false;
    };
    atuin = {
      enable = true;
      flags = [ "--disable-up-arrow" ];
      settings = {
        auto_sync = false;
        update_check = false;
        show_help = false;
        enter_accept = true;
        prefers_reduced_motion = true;
      };
    };
    ripgrep = {
      enable = true;
      arguments = [ "--ignore-case" ];
    };
    bun = {
      enable = false;
      settings = {
        smol = true;
        telemetry = false;
        install.registry = "https://npmreg.proxy.ustclug.org";
        run.bun = true;
      };
    };
    broot = {
      enable = true;
      settings.default_flags = "-ih";
    };
    fd = {
      enable = true;
      hidden = true;
      ignores = [
        ".git/"
        # Dependency directories
        "node_modules/"
        # Caches
        ".ipynb_checkpoints/"
        ".cache/"
        ".next/"
        # Python
        ".venv/"
        "__pycache__/"
      ];
      extraOptions = [
        "--no-ignore-vcs"
        "--full-path"
      ];
    };
    eza = {
      enable = true;
      icons = "auto";
      git = true;
      colors = "auto";
      extraOptions = [
        "--group-directories-first"
        "--all"
      ];
    };
    helix = {
      enable = true;
      defaultEditor = true;
      settings = {
        theme = "fleet_dark";
        editor = {
          middle-click-paste = false;
          file-picker.hidden = false;
          soft-wrap.enable = true;
          indent-guides.render = true;
        };
      };
    };
    git = {
      enable = true;
      lfs.skipSmudge = true;
      ignores = [
        # Environments
        ".env"
        ".env.local"
        ".env.*.local"
        # Dependency directories
        "node_modules/"
        # IDEs and Editors
        ## JetBrains IDEs
        ".idea/"
        # Logs and runtime files
        "*.log"
        "*.seed"
        "*.temp"
        ".cmp"
        ".ipynb_checkpoints/"
        ".cache/"
        ".next/"
        # Operating System
        ".DS_Store"
        # Node
        ".npm"
        ".eslintcache"
        ".stylelintcache"
        # Python
        ".venv/"
        ".Python"
        "*.py[cod]"
        "__pycache__/"
        "pyvenv.cfg"
        "pip-selfcheck.json"
        # CMake
        "CMakeFiles/"
        "CMakeScripts/"
        "CMakeCache.txt"
        "*.cmake"
        # Maven
        "pom.xml.tag"
        "pom.xml.releaseBackup"
        "pom.xml.versionsBackup"
        # Databases
        "*.db"
        "*.sqlite3-journal"
      ];
      attributes = [ "*.age diff=nodiff" ];
      settings.alias = {
        ca = "commit --amend --no-edit --reset-author --no-date";
        pf = "push --force";
      };
      signing.format = "openpgp";
    };
    delta = {
      enable = true;
      options.side-by-side = false;
      enableGitIntegration = true;
    };
    uv = {
      enable = true;
      settings.pip.index-url = "https://mirror.nju.edu.cn/pypi/web/simple";
    };
    alacritty = {
      enable = true;
      settings = {
        general = {
          import = [ "${pkgs.alacritty-theme}/dracula_plus.toml" ];
          live_config_reload = false;
        };
        terminal.shell.program = "fish";
        window = {
          padding = {
            x = 6;
            y = 6;
          };
          dimensions = {
            columns = 120;
            lines = 26;
          };
          startup_mode = "Windowed";
          decorations_theme_variant = "Dark";
        };
        font = {
          normal = {
            family = "Sarasa Mono SC";
            style = "Regular";
          };
          italic = {
            family = "Sarasa Mono Slab SC";
            style = "Italic";
          };
          bold_italic = {
            family = "Sarasa Mono Slab SC";
            style = "Bold Italic";
          };
          size = 20;
        };
        debug = {
          log_level = "Off";
          prefer_egl = true;
        };
        keyboard.bindings = [
          {
            key = "Return";
            mods = "Control|Shift";
            action = "SpawnNewInstance";
          }
        ];
      };
    };
    ruff = {
      enable = true;
      settings = {
        preview = true;
        unsafe-fixes = true;
        format.docstring-code-format = true;
      };
    };
    vscode = {
      enable = true;
      package = pkgs.vscodium;
      profiles.default.extensions = with pkgs.vscode-extensions; [
        ms-ceintl.vscode-language-pack-zh-hans
        formulahendry.code-runner
        redhat.vscode-yaml
        ms-python.python
        charliermarsh.ruff
        foxundermoon.shell-format
        myriad-dreamin.tinymist
        tomoki1207.pdf
        jnoortheen.nix-ide
        rooveterinaryinc.roo-cline
        # timonwong.shellcheck
        # tamasfe.even-better-toml
        # llvm-vs-code-extensions.vscode-clangd
        # golang.go
        # github.codespaces
        # bmalehorn.vscode-fish
        # yzhang.markdown-all-in-one
        # ms-vscode.cpptools
        # redhat.vscode-xml
        # rust-lang.rust-analyzer
      ];
    };
    go = {
      enable = false;
      telemetry.mode = "off";
    };
    chromium = {
      enable = true;
      package = pkgs.ungoogled-chromium;
      commandLineArgs = [
        "--process-per-site"
        #  "--disable-reading-from-canvas"
        "--disable-breakpad"
        "--disable-crash-reporter"
        "--no-default-browser-check"
        "--enable-gpu-rasterization"
        "--enable-zero-copy"
        "--ignore-gpu-blocklist"
        "--use-cmd-decoder=passthrough"
        "--enable-quic"
        "--enable-smooth-scrolling"
        "--enable-webrtc-pipewire-capturer"
        "--disable-features=ChromeLabs,LensOverlay,ShowSuggestionsOnAutofocus"
        "--enable-features=VaapiVideoDecodeLinuxGL,VaapiVideoEncoder,VaapiVideoDecoder,VaapiIgnoreDriverChecks,CanvasOopRasterization,ParallelDownloading,WebContentsCaptureHiDPI,WebRtcHideLocalIpsWithMdns,UseGpuSchedulerDfs,BackForwardCache,FontationsFontBackend,GlobalMediaControlsUpdatedUI,WebRtcPipeWireCamera,OverlayScrollbar,WebRTCPipeWireCapturer,UseOzonePlatform,WaylandWindowDecorations"
        "--ozone-platform-hint=auto"
        "--enable-wayland-ime"
        "--wayland-text-input-version=3"
      ];
      extensions = [
        # { id = "cjpalhdlnbpafiamejdnhcphjbkeiagm"; } # ublock origin
        # { id = "nngceckbapebfimnlniiiahkandclblb"; } # Bitwarden
        # { id = "jinjaccalgkegednnccohejagnlnfdag"; } # violentmonkey
        # { id = "bdiifdefkgmcblbcghdlonllpjhhjgof"; } # kiss-translator
        # { id = "djflhoibgkdhkhhcedjiklpkjnoahfmg"; } # user-agent-switcher
        # { id = "jpbjcnkcffbooppibceonlgknpkniiff"; } # global-speed
        # { id = "gbkeegbaiigmenfmjfclcdgdpimamgkj"; } # Google docs
        # { id = "ghbmnnjooekpmoecnnnilnnbdlolhkhi"; } # Google docs off-line
        # {
        #   id = "ocaahdebbfolfmndjeplogmgcagdmblk";
        #   updateUrl = "https://raw.githubusercontent.com/NeverDecaf/chromium-web-store/master/updates.xml";
        # }
      ];
    };
    obs-studio = {
      enable = false;
      plugins = with pkgs.obs-studio-plugins; [
        obs-pipewire-audio-capture
        obs-vaapi
        obs-vkcapture
      ];
    };
  };

  manual.manpages.enable = false;

  news.display = "silent";

  systemd.user = {
    sessionVariables = {
      QT_AUTO_SCREEN_SCALE_FACTOR = 1;
      QT_ENABLE_HIGHDPI_SCALING = 1;
      QT_FONT_DPI = 120;
    };
    startServices = "sd-switch";
  };
}
