{
  inputs,
  lib,
  pkgs,
  config,
  ...
}:

let
  username = "uymi";
  hostname = "noirriko";
  uid = 1000;
in
{
  imports = [
    inputs.home-manager.nixosModules.home-manager
    inputs.nix-index-database.nixosModules.nix-index
    inputs.nixos-hardware.nixosModules.common-cpu-amd
    inputs.nixos-hardware.nixosModules.common-cpu-amd-pstate
    inputs.nixos-hardware.nixosModules.common-pc-laptop
    inputs.nixos-hardware.nixosModules.common-pc-laptop-ssd
    ./hardware-configuration.nix
    ../modules/dae.nix
    ../modules/nvidia.nix
    ../modules/gnome.nix
    ../modules/fcitx5.nix
    ../modules/chromium.nix
  ];

  nixpkgs = {
    config = {
      allowUnfree = true;
      allowAliases = false;
      warnUndeclaredOptions = true;
      microsoftVisualStudioLicenseAccepted = true;
    };
    overlays = [
      inputs.firefox-addons.overlays.default
      (import ../../overlays { inherit inputs; })
    ];
  };

  hardware = {
    enableRedistributableFirmware = true;
    graphics.enable = true;
    bluetooth = {
      enable = true;
      disabledPlugins = [
        "bap"
        "bass"
        "mcp"
        "vcp"
        "micp"
        "ccp"
        "csip"
      ];
    };
  };

  boot = {
    loader = {
      systemd-boot = {
        enable = true;
        configurationLimit = 10;
        consoleMode = "auto";
      };
      timeout = 3;
    };
    kernelPackages = pkgs.linuxPackages_zen;
    kernelParams = [
      "amdgpu.vm_update_mode=3"
      "radeon.dpm=0"
      "acpi_backlight=native"
      "mitigations=off"
      "nowatchdog"
    ];
    kernelModules = [ "tcp_bbr" ];
    kernel = {
      sysfs.module.zswap.parameters = {
        enabled = true;
        zpool = "zsmalloc";
        compressor = "zstd";
      };
      sysctl = {
        "net.ipv4.tcp_fastopen" = 3;
        "net.ipv4.tcp_congestion_control" = "bbr";
        "net.core.default_qdisc" = "fq";

        "fs.suid_dumpable" = 0;
        "kernel.core_pattern" = "|${lib.getExe' pkgs.uutils-coreutils-noprefix "false"}";

        "kernel.sysrq" = 1;
        "net.ipv4.tcp_mtu_probing" = 1;

        "net.ipv4.tcp_keepalive_time" = "60";
        "net.ipv4.tcp_keepalive_intvl" = "10";
        "net.ipv4.tcp_keepalive_probes" = "6";
      };
    };
    extraModprobeConfig = ''
      blacklist sp5100_tco
      blacklist iTCO_wdt
    '';
    consoleLogLevel = 3;
    tmp.useTmpfs = true;
  };

  networking = {
    resolvconf.extraOptions = [
      "timeout:1"
      "attempts:1"
      "rotate"
      "single-request"
    ];
    hostName = hostname;
    firewall.enable = false;
    nameservers = [
      "223.6.6.6#dns.alidns.com"
      "8.8.8.8#dns.google"
    ];
    networkmanager = {
      enable = true;
      dns = "systemd-resolved";
      wifi = {
        backend = "iwd";
        powersave = true;
        macAddress = "stable-ssid";
      };
    };
  };

  users.users = {
    root = {
      initialHashedPassword = "$y$j9T$/qg2DYP0TOSZzSwlgs9mV/$uVAqBwhXEnwkMd0D4zKH9SSBQ4WzlGcnimnLrbyNwP4";
      shell = pkgs.brush;
    };
    "${username}" = {
      inherit uid;
      isNormalUser = true;
      initialHashedPassword = "$y$j9T$XOU8eqbT/uiYRkLNMVma91$FpP9C3IIhl1t/i9LH0k5LxqwnRKH9baVotniFxx7vG4";
      extraGroups = [
        "wheel"
        "users"
        "plugdev"
        "input"
        "video"
        "audio"
        "systemd-journal"
      ]
      ++ (lib.optional config.programs.git.enable "git")
      ++ (lib.optional config.networking.networkmanager.enable "networkmanager")
      ++ (lib.optional config.services.colord.enable "colord")
      ++ (lib.optional config.programs.adb.enable "adbusers")
      ++ (lib.optional config.programs.wireshark.enable "wireshark")
      ++ (lib.optional config.virtualisation.podman.enable "podman")
      ++ (lib.optional config.virtualisation.libvirtd.enable "libvirtd")
      ++ (lib.optional config.virtualisation.docker.enable "docker");
      shell = pkgs.brush;
      packages = with pkgs; [
        typst
        ruff
        nil
        variety
        sly
        celluloid
        bilibili
        materialgram
        (papirus-icon-theme.override { color = "adwaita"; })
        orchis-theme
        e-search
        navicat-premium
        (pkgs.writeShellScriptBin "navicat-reset" ''
          ${lib.getExe pkgs.dconf} reset -f /com/premiumsoft/
          ${lib.getExe pkgs.jq} 'with_entries(select(.key | length != 32))' ~/.config/navicat/Premium/preferences.json | ${lib.getExe' pkgs.moreutils "sponge"} ~/.config/navicat/Premium/preferences.json
        '')
      ];
    };
  };

  environment = {
    stub-ld.enable = false;
    shells = with pkgs; [
      brush
      fish
    ];
    variables = {
      EDITOR = "hx";
      NPM_CONFIG_GLOBALCONFIG = "/etc/npmrc";
    };
    etc.npmrc.text = "registry=https://npmreg.proxy.ustclug.org";
    sessionVariables = {
      NIX_REMOTE = "daemon";
      LESS = "-SR";
      MANPAGER = "sh -c 'col -bx | ${lib.getExe pkgs.bat} -l man -p'";
      MANROFFOPT = "-c";
      NIXOS_OZONE_WL = 1;
    };
    systemPackages = with pkgs; [
      nix-tree
      go-task
      nixfmt
      inputs.nix-alien.packages.${stdenv.hostPlatform.system}.nix-alien
      (lib.hiPrio uutils-coreutils-noprefix)
      (lib.hiPrio uutils-findutils)
      age
      helix
      eza
      fzf
      fd
      ripgrep
      lnav
      riffdiff
      rfv
      uv
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
  };

  nix = {
    package = pkgs.nix;
    daemonCPUSchedPolicy = lib.mkDefault "idle";
    daemonIOSchedClass = lib.mkDefault "idle";
    settings = {
      flake-registry = "";
      experimental-features = [
        "nix-command"
        "flakes"
        "cgroups"
      ];
      trusted-users = [ "@wheel" ];
      lazy-trees = true;
      always-allow-substitutes = true;
      builders-use-substitutes = true;
      use-cgroups = true;
      warn-dirty = false;
      substituters = [
        "https://mirrors.ustc.edu.cn/nix-channels/store"
        "https://nix-community.cachix.org"
        "https://cache.garnix.io"
        "https://seilunako.cachix.org"
      ];
      trusted-public-keys = [
        "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
        "cache.garnix.io:CTFPyKSLcx5RMJKfLo5EEPUObbA78b0YQ2DTCJXqr9g="
        "seilunako.cachix.org-1:e/aJJI1S5hPY/BPeiVZcuPjt5ZjBRRo9dlYHmvwXPFM="
      ];
    };
    channel.enable = false;
    gc = {
      automatic = true;
      dates = "weekly";
      options = "--delete-older-than 14d";
    };
  };

  time.timeZone = "Etc/GMT-8";

  fonts = {
    enableDefaultPackages = true;
    fontDir.enable = true;
    packages = with pkgs; [
      noto-fonts
      noto-fonts-cjk-sans-static
      noto-fonts-cjk-serif-static
      noto-fonts-color-emoji
      nerd-fonts.symbols-only
      sarasa-gothic
      source-han-mono
      source-han-serif
      source-han-sans
    ];
    fontconfig = {
      enable = true;
      defaultFonts = {
        serif = [ "Noto Serif CJK SC" ];
        sansSerif = [ "Sarasa UI SC" ];
        monospace = [ "Sarasa Mono SC" ];
        emoji = [ "Noto Color Emoji" ];
      };
    };
  };

  i18n = {
    defaultLocale = "zh_CN.UTF-8";
    supportedLocales = [
      "zh_CN.UTF-8/UTF-8"
      "en_US.UTF-8/UTF-8"
    ];
    inputMethod = {
      enable = true;
      type = "fcitx5";
      fcitx5 = {
        waylandFrontend = true;
        addons = with pkgs; [
          fcitx5-gtk
          kdePackages.fcitx5-chinese-addons
          fcitx5-pinyin-zhwiki
        ];
      };
    };
  };

  programs = {
    command-not-found.enable = false;
    bash.promptInit = ''
      PS1='\u@\h\[\e[32m\]\w\[\e[0m\] \\$ '
    '';
    fish = {
      enable = true;
      interactiveShellInit = ''
        set -g fish_greeting
        set -U fish_history_max 2500
        set -gx fish_prompt_pwd_dir_length 0
        fish_config theme choose 'Tomorrow Night Bright'
        fish_config prompt choose simple
        ${lib.getExe pkgs.any-nix-shell} fish --info-right | source
      '';
      shellAbbrs = {
        nix-history = "nix profile history --profile /nix/var/nix/profiles/system";
        nix-wipe = "sudo nix profile wipe-history --profile /nix/var/nix/profiles/system --older-than 1d && ${lib.getExe pkgs.home-manager} expire-generations 0days";
        nix-gc = "sudo nix-collect-garbage --delete-older-than 7d && nix-collect-garbage --delete-older-than 7d";
        nix-cc = "rm -rf ~/.cache/nix && sudo rm -rf /root/.cache/nix";
      };
    };
    nix-ld = {
      enable = true;
      libraries = with pkgs; [
        glib
        libGL
      ];
    };
    nix-index = {
      enable = true;
      enableBashIntegration = false;
      enableFishIntegration = false;
    };
    nix-index-database.comma.enable = true;
    adb.enable = true;
    direnv.enable = true;
    ssh.askPassword = lib.getExe pkgs.pinentry-gnome3;
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
      settings.yazi = {
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
    };
    bat = {
      enable = true;
      settings = {
        style = "header-filename,header-filesize,grid";
        paging = "never";
        theme = "Dracula";
      };
    };
    git = {
      enable = true;
      lfs.enable = true;
      config = {
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
      };
    };
    nautilus-open-any-terminal = {
      enable = true;
      terminal = "alacritty";
    };
    localsend.enable = true;
    steam = {
      enable = true;
      extraCompatPackages = with pkgs; [ proton-ge-bin ];
      protontricks.enable = true;
      extest.enable = true;
      gamescopeSession = {
        enable = true;
        env =
          lib.optionalAttrs
            (
              (lib.elem "nvidia" config.services.xserver.videoDrivers)
              && (config.hardware.nvidia.prime.offload.enable)
            )
            {
              __NV_PRIME_RENDER_OFFLOAD = "1";
              __NV_PRIME_RENDER_OFFLOAD_PROVIDER = "NVIDIA-G0";
              __GLX_VENDOR_LIBRARY_NAME = "nvidia";
              __VK_LAYER_NV_optimus = "NVIDIA_only";
            };
      };
    };
  };

  xdg = {
    terminal-exec = {
      enable = true;
      settings.default = [ "Alacritty.desktop" ];
    };
    portal = {
      enable = true;
      xdgOpenUsePortal = true;
    };
  };

  security.sudo-rs.enable = true;

  documentation = {
    nixos.enable = false;
    info.enable = false;
    doc.enable = false;
    man = {
      man-db.enable = false;
      mandoc.enable = true;
      generateCaches = false;
    };
  };

  services = {
    scx = {
      enable = true;
      scheduler = "scx_bpfland";
    };
    acpid.enable = true;
    upower = {
      enable = true;
      noPollBatteries = true;
    };
    power-profiles-daemon.enable = false;
    tlp.enable = false;
    auto-cpufreq = {
      enable = true;
      settings.charger = {
        governor = "schedutil";
        turbo = "auto";
      };
    };
    earlyoom = {
      enable = true;
      freeSwapThreshold = 5;
      freeMemThreshold = 5;
      extraArgs = [
        "-g"
        "--prefer"
        "(^|/)(nix-daemon|java|git|nil|chromium|librewolf|electron|codium)$"
      ];
    };
    fstrim.enable = true;
    btrfs.autoScrub.enable = if config.fileSystems."/".fsType == "btrfs" then true else false;
    dbus.implementation = "broker";
    avahi.enable = false;
    geoclue2.enable = false;
    journald.extraConfig = ''
      ForwardToConsole=no
      ForwardToKMsg=no
      ForwardToSyslog=no
      ForwardToWall=no
      SystemMaxFileSize=10M
      SystemMaxUse=100M
    '';
    psd.enable = true;
    resolved = {
      enable = true;
      dnsovertls = "true";
      domains = [ "~." ];
    };
    pipewire = {
      enable = true;
      audio.enable = true;
      alsa.enable = true;
      jack.enable = true;
      pulse.enable = true;
      wireplumber.enable = true;
    };
    kmscon = {
      enable = true;
      fonts = [
        {
          name = "Sarasa Mono SC";
          package = pkgs.sarasa-gothic;
        }
      ];
      extraConfig = "font-size=20";
      hwRender = true;
    };
    sunshine = {
      enable = true;
      autoStart = false;
      capSysAdmin = true;
    };
    libinput = {
      enable = true;
      mouse.accelProfile = "adaptive";
      touchpad = {
        tapping = true;
        naturalScrolling = true;
        accelProfile = "adaptive";
        disableWhileTyping = true;
      };
    };
    displayManager = {
      gdm.enable = true;
      autoLogin = {
        enable = true;
        user = username;
      };
    };
    xserver = {
      enable = true;
      videoDrivers = [ "amdgpu" ];
      desktopManager.xterm.enable = false;
      excludePackages = with pkgs; [ xterm ];
      wacom.enable = false;
    };
    # flatpak.enable = true;
  };

  systemd = {
    oomd.enable = false;
    coredump.extraConfig = ''
      Storage=none
      ProcessSizeMax=0
    '';
    sleep.extraConfig = "AllowHibernation=no";
    timers.suspend-then-shutdown = {
      wantedBy = [ "sleep.target" ];
      partOf = [ "sleep.target" ];
      onSuccess = [ "suspend-then-shutdown.service" ];
      timerConfig = {
        OnActiveSec = "2h";
        AccuracySec = "30m";
        RemainAfterElapse = false;
        WakeSystem = true;
      };
    };
    services = {
      nix-daemon.serviceConfig = {
        MemoryAccounting = true;
        MemoryMax = "80%";
        OOMScoreAdjust = lib.mkDefault 250;
      };
      nix-gc.serviceConfig = {
        CPUSchedulingPolicy = "batch";
        IOSchedulingClass = "idle";
        IOSchedulingPriority = 7;
      };
      suspend-then-shutdown = {
        description = "Shutdown after suspend";
        path = with pkgs; [ dbus ];
        environment = {
          DISPLAY = ":0";
          DBUS_SESSION_BUS_ADDRESS = "unix:path=/run/user/${toString uid}/bus";
          XDG_RUNTIME_DIR = "/run/user/${toString uid}";
        };
        script = ''
          sleep 1m
          current_timestamp=$(${lib.getExe' pkgs.uutils-coreutils-noprefix "date"} +%s)
          active_enter_timestamp=$(${lib.getExe' pkgs.uutils-coreutils-noprefix "date"} -d "$(${lib.getExe' pkgs.systemd "systemctl"} show -p ActiveEnterTimestamp sleep.target | cut -d= -f2)" +%s)
          if [ $((current_timestamp - active_enter_timestamp)) -ge 6000 ]; then
            ${lib.getExe' pkgs.gnome-session "gnome-session-quit"} --power-off
          fi
        '';
        serviceConfig = {
          Type = "simple";
          User = uid;
        };
      };
      systemd-gpt-auto-generator.enable = false;
      "getty@tty1".enable = false;
      "autovt@tty1".enable = false;
      alsa-store.enable = false;
      keyboard-brightness = {
        description = "Set keyboard brightness after resume";
        wantedBy = [
          "sleep.target"
          "suspend.target"
          "hibernate.target"
        ];
        serviceConfig = {
          Type = "oneshot";
          WorkingDirectory = "/sys/class/leds/platform::kbd_backlight/";
          ExecStart = "${lib.getExe pkgs.brush} -c \"cat brightness > /var/tmp/kbd_brightness_current && echo 0 > brightness\"";
          ExecStop = "${lib.getExe pkgs.brush} -c 'sleep 3s && cat /var/tmp/kbd_brightness_current > brightness && rm /var/tmp/kbd_brightness_current'";
        };
      };
      numlock-brightness = {
        description = "Set numlock Brightness";
        after = [
          "graphical.target"
          "sleep.target"
          "suspend.target"
          "hibernate.target"
        ];
        wantedBy = [
          "graphical.target"
          "sleep.target"
          "suspend.target"
          "hibernate.target"
        ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          WorkingDirectory = "/sys/class/leds/";
          ExecStart = "${lib.getExe pkgs.brush} -c 'sleep 3s && for dir in ./*::numlock*/; do [ -d \"$dir\" ] && echo 0 > \"$dir/brightness\"; done'";
          User = "root";
        };
      };
    };
  };

  system.stateVersion = lib.trivial.release;
}
