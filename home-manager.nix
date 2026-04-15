{
  inputs,
  pkgs,
  lib,
  config,
  ...
}:

{
  imports = [ inputs.nix-index-database.homeModules.nix-index ];

  home = {
    enableNixpkgsReleaseCheck = false;
    stateVersion = lib.trivial.release;
    shell = {
      enableIonIntegration = false;
      enableZshIntegration = false;
      enableNushellIntegration = false;
    };
    language.base = "zh_CN.UTF-8";
    activation.setupTermuxConfig =
      let
        font = "${
          pkgs.maple-mono.Normal-NF-CN.overrideAttrs (_: {
            installPhase = ''
              runHook preInstall

              install MapleMonoNormal-NF-CN-Medium.ttf -D --target-directory $out/share/fonts/truetype

              runHook postInstall
            '';
          })
        }/share/fonts/truetype/MapleMonoNormal-NF-CN-Medium.ttf";
        termux-properties = lib.generators.toINIWithGlobalSection { } {
          globalSection = {
            enforce-char-based-input = true;
          };
        };
      in
      lib.hm.dag.entryAfter [ "writeBoundary" ] ''
        install -D --mode=0644 ${font} ${config.home.homeDirectory}/.termux/termux.properties
        install -D --mode=0644 ${pkgs.writeText "termux.properties" termux-properties} ${config.home.homeDirectory}/.termux/termux.properties
      '';
  };

  xdg.configFile = {
    "nixpkgs/config.nix".text = ''
      {
        allowUnfree = true;
      }
    '';
    "pip/pip.conf".text = ''
      [global]
      index-url = https://mirror.nju.edu.cn/pypi/web/simple
    '';
  };

  programs = {
    man.generateCaches = false;
    nix-index = {
      enable = true;
      enableBashIntegration = false;
      enableFishIntegration = false;
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
    fish = {
      enable = true;
      interactiveShellInit = ''
        set -g fish_greeting
        set -U fish_history_max 10000
        set -gx fish_prompt_pwd_dir_length 0
        fish_config theme choose 'Tomorrow Night Bright'
        fish_config prompt choose simple
      ''
      + lib.optionalString config.programs.bun.enable ''
        set -x BUN_INSTALL $HOME/.bun
        set -x PATH $PATH $BUN_INSTALL/bin
      '';
      shellAbbrs = {
        nix-wipe = "nix profile wipe-history --older-than 1d && ${lib.getExe pkgs.home-manager} expire-generations 0days";
        nix-gc = "nix-collect-garbage --delete-older-than 7d";
      };
    };
    nix-your-shell.enable = true;
    broot = {
      enable = false;
      settings.default_flags = "-ih";
    };
    htop = {
      enable = true;
      settings = {
        fields = [
          0
          48
          20
          49
          39
          40
          111
          46
          47
          1
        ];
        hide_userland_threads = 1;
        show_thread_names = 1;
        show_program_path = 0;
        highlight_base_name = 1;
        strip_exe_from_cmdline = 1;
        show_merged_command = 0;
        screen_tabs = 1;
        cpu_count_from_one = 1;
        show_cpu_frequency = 1;
        show_cpu_temperature = 1;
        color_scheme = 6;
        column_meters_0 = [
          "CPU"
          "Memory"
          "Swap"
        ];
        column_meter_modes_0 = [
          1
          1
          1
        ];
        column_meters_1 = [
          "Tasks"
          "DiskIO"
          "NetworkIO"
        ];
        column_meter_modes_1 = [
          2
          2
          2
        ];
        tree_view = 0;
        sort_key = 47;
        sort_direction = -1;
      };
    };
    yazi = {
      enable = true;
      settings = {
        opener.edit = [
          {
            run = "$\{EDITOR:-hx\} \"$@\"";
            block = true;
            for = "unix";
          }
        ];
        mgr = {
          show_hidden = true;
          sort_dir_first = true;
        };
        preview.wrap = "yes";
      };
      theme = {
        icon = {
          globs = [ ];
          dirs = [ ];
          files = [ ];
          exts = [ ];
          conds = [ ];
        };
        status = {
          sep_left = {
            open = "";
            close = "";
          };
          sep_right = {
            open = "";
            close = "";
          };
        };
      };
    };
    bat = {
      enable = true;
      config = {
        style = "header-filename,header-filesize,grid";
        paging = "never";
        theme = "Dracula";
      };
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
      icons = "never";
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
      settings = {
        user = {
          name = "jane";
          email = "jane@computer.local";
        };
        core = {
          autocrlf = "input";
          askpass = "";
          quotepath = false;
        };
        init.defaultBranch = "main";
        push = {
          autoSetupRemote = true;
          default = "current";
        };
        difftool.prompt = false;
        diff.nodiff.command = "true";
        log.date = "iso";
        merge.conflictStyle = "zdiff3";
        core.fsmonitor = true;
        core.preloadIndex = "true";
        index.version = 4;
        core.untrackedCache = true;
        feature.manyFiles = true;
        alias = {
          ca = "commit --amend --no-edit --reset-author --no-date";
          pf = "push --force";
        };
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
      settings = {
        python-downloads = "never";
        python-preference = "only-system";
        torch-backend = "cpu";
        upgrade = true;
        pip = {
          torch-backend = "auto";
          index-url = "https://mirror.nju.edu.cn/pypi/web/simple";
        };
      };
    };
    ruff = {
      enable = true;
      settings = {
        fix = true;
        preview = true;
        target-version = "py312";
        unsafe-fixes = true;
        analyze.preview = true;
        lint = {
          select = [ "ALL" ];
          ignore = [
            "INP001"
            "ANN201"
            "FBT002"
            "ANN001"
            "CPY001"
            "D100"
            "D101"
            "D102"
            "D103"
            "D104"
            "D105"
            "D106"
            "D107"
            "D203"
            "D213"
            "COM812"
            "ISC001"
            "G004"
            "TRY003"
            "EM101"
            "EM102"
            "S101"
            "ERA001"
            "RET504"
            "EXE003"
            "S404"
            "S603"
            "S607"
            "S310"
            "PLW1510"
            "PLR2004"
            "FBT001"
            "E501"
            "E402"
            "FBT003"
            "N806"
            "D205"
            "DOC201"
            "RUF002"
          ];
        };
        format = {
          docstring-code-format = true;
          preview = true;
        };
      };
    };
    opencode = {
      enable = true;
      settings = {
        autoshare = false;
        autoupdate = false;
        share = "disabled";
        lsp = false;
        permission = {
          bash = {
            "nix-build *" = "deny";
            "nix build *" = "deny";
            "git pull *" = "deny";
          };
          lsp = "deny";
          read."*.age" = "deny";
          doom_loop = "allow";
          external_directory = "allow";
        };
        formatter = {
          shfmt = {
            command = [
              (lib.getExe pkgs.shfmt)
              "-w"
              "$FILE"
            ];
            extensions = [
              "*.sh"
              "*.bash"
              "*.envrc"
              "*.envrc.*"
            ];
          };
          taplo = {
            command = [
              (lib.getExe pkgs.taplo)
              "format"
              "$FILE"
            ];
            extensions = [ "*.toml" ];
          };
          yamlfmt = {
            command = [
              (lib.getExe pkgs.yamlfmt)
              "$FILE"
            ];
            extensions = [
              "*.yaml"
              "*.yml"
            ];
          };
          nixfmt = {
            command = [
              (lib.getExe pkgs.nixfmt)
              "$FILE"
            ];
            extensions = [ ".nix" ];
          };
          rustfmt = {
            command = [
              (lib.getExe pkgs.rustfmt)
              "--config"
              "skip_children=true"
              "$FILE"
            ];
            extensions = [ ".rs" ];
          };
        };
      };
    };
    television = {
      enable = true;
      enableBashIntegration = false;
      enableFishIntegration = false;
      package = pkgs.television.withPackages (p: [ p.bash ]);
      settings = {
        tick_rate = 100;
        default_channel = "text";
        history_size = 0;
        ui = {
          use_nerd_font_icons = false;
          orientation = "portrait";
          theme = "onedark";
          input_bar.border_type = "none";
          results_panel.border_type = "none";
          preview_panel.border_type = "none";
        };
      };
    };
  };

  manual.manpages.enable = false;

  news.display = "silent";

  systemd.user.enable = false;
}
