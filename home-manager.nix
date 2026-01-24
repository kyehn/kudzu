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
    file.".termux/termux.properties".text = ''
      enforce-char-based-input=true
    '';
  };

  xdg = {
    configFile = {
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
  };

  programs = {
    man.generateCaches = false;
    nix-index = {
      enable = true;
      enableBashIntegration = false;
      enableFishIntegration = false;
    };
    atuin = {
      enable = false;
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
        push.autoSetupRemote = true;
        difftool.prompt = false;
        diff.nodiff.command = "true";
        log.date = "iso";
        merge.conflictStyle = "zdiff3";
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
      settings.pip.index-url = "https://mirror.nju.edu.cn/pypi/web/simple";
    };
    ruff = {
      enable = true;
      settings = {
        preview = true;
        unsafe-fixes = true;
        format.docstring-code-format = true;
      };
    };
  };

  manual.manpages.enable = false;

  news.display = "silent";

  systemd.user.enable = false;
}
