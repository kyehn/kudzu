{ lib, ... }:

{
  dconf.settings = {
    "ca/desrt/dconf-editor".show-warning = false;

    "org/gnome/desktop/interface" = {
      action-right-click-titlebar = "none";
      clock-show-date = true;
      clock-show-seconds = false;
      clock-show-weekday = true;
      cursor-size = 24;
      cursor-theme = "Bibata-Modern-Classic";
      disable-workarounds = true;
      document-font-name = "更纱黑体 UI SC 11";
      enable-animations = true;
      font-antialiasing = "rgba";
      font-hinting = "slight";
      font-name = "更纱黑体 UI SC 11";
      monospace-font-name = "等距更纱黑体 SC 11";
      gtk-enable-primary-paste = false;
      gtk-theme = "Orchis-Green-Compact-Nord";
      icon-theme = "Papirus";
      show-battery-percentage = true;
      text-scaling-factor = 1.25;
      toolkit-accessibility = false;
      accent-color = "green";
    };

    "org/gnome/desktop/screen-time-limits".history-enabled = false;

    "org/gnome/desktop/peripherals/keyboard".numlock-state = true;

    "org/gnome/desktop/peripherals/touchpad".two-finger-scrolling-enabled = true;

    "org/gnome/desktop/privacy" = {
      old-files-age = lib.hm.gvariant.mkUint32 3;
      recent-files-max-age = 1;
      remember-app-usage = false;
      remember-recent-files = false;
      remove-old-temp-files = true;
    };

    "org/gnome/desktop/screensaver" = {
      color-shading-type = "solid";
      lock-delay = lib.hm.gvariant.mkUint32 0;
      lock-enabled = false;
    };

    "org/gnome/desktop/search-providers".disable-external = true;

    "org/gnome/desktop/session".idle-delay = lib.hm.gvariant.mkUint32 300;

    "org/gnome/desktop/sound".allow-volume-above-100-percent = true;

    "org/gnome/desktop/wm/keybindings".activate-window-menu = [ "<Super>m" ];

    "org/gnome/desktop/wm/preferences" = {
      action-right-click-titlebar = "none";
      button-layout = "appmenu:minimize,maximize,close";
      disable-workarounds = true;
      num-workspaces = 1;
    };

    "org/gnome/desktop/a11y/interface".show-status-shapes = true;

    "org/gnome/gnome-system-monitor" = {
      cpu-stacked-area-chart = true;
      maximized = true;
      network-in-bits = false;
      network-total-in-bits = false;
      process-memory-in-iec = true;
      resources-memory-in-iec = true;
      show-dependencies = false;
      show-whose-processes = "user";
    };

    "org/gnome/gnome-system-monitor/disktreenew" = {
      col-0-visible = true;
      col-0-width = 212;
      col-1-visible = true;
      col-1-width = 258;
      col-2-visible = true;
      col-2-width = 167;
      col-4-visible = true;
      col-4-width = 80;
      col-5-visible = true;
      col-5-width = 132;
      col-6-visible = true;
      col-6-width = 0;
    };

    "org/gnome/gnome-system-monitor/proctree" = {
      col-0-visible = true;
      col-0-width = 260;
      col-12-visible = true;
      col-12-width = 136;
      col-14-visible = true;
      col-14-width = 653;
      col-15-visible = true;
      col-15-width = 106;
      col-16-visible = false;
      col-16-width = 48;
      col-17-visible = false;
      col-17-width = 55;
      col-18-visible = false;
      col-18-width = 88;
      col-19-visible = false;
      col-19-width = 41;
      col-2-visible = false;
      col-2-width = 37;
      col-20-visible = false;
      col-20-width = 59;
      col-21-visible = false;
      col-21-width = 59;
      columns-order = "[0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]";
      sort-col = 8;
      sort-order = 0;
    };

    "org/gnome/mutter" = {
      center-new-windows = true;
      dynamic-workspaces = true;
      edge-tiling = true;
      experimental-features = [ "xwayland-native-scaling" ];
    };

    "org/gnome/nautilus/compression".default-compression-format = "zip";

    "org/gnome/nautilus/preferences" = {
      recursive-search = "never";
      show-hidden-files = true;
    };

    "org/gnome/online-accounts".whitelisted-providers = [ ];

    "org/gnome/settings-daemon/plugins/color" = {
      night-light-enabled = true;
      night-light-schedule-automatic = false;
      night-light-schedule-from = 0.0;
      night-light-schedule-to = 0.0;
      night-light-temperature = lib.hm.gvariant.mkUint32 3613;
    };

    "org/gnome/settings-daemon/plugins/media-keys".custom-keybindings = [
      "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/"
    ];

    "org/gnome/settings-daemon/plugins/power" = {
      sleep-inactive-ac-type = "suspend";
      sleep-inactive-battery-type = "suspend";
      sleep-inactive-battery-timeout = 900;
      sleep-inactive-ac-timeout = 1800;
    };

    "org/gnome/shell" = {
      disabled-extensions = [
        "launch-new-instance@gnome-shell-extensions.gcampax.github.com"
        "native-window-placement@gnome-shell-extensions.gcampax.github.com"
        "workspace-indicator@gnome-shell-extensions.gcampax.github.com"
        "windowsNavigator@gnome-shell-extensions.gcampax.github.com"
        "window-list@gnome-shell-extensions.gcampax.github.com"
        "places-menu@gnome-shell-extensions.gcampax.github.com"
        "apps-menu@gnome-shell-extensions.gcampax.github.com"
        "status-icons@gnome-shell-extensions.gcampax.github.com"
      ];
      enabled-extensions = [
        "auto-move-windows@gnome-shell-extensions.gcampax.github.com"
        "appindicatorsupport@rgcjonas.gmail.com"
        "kimpanel@kde.org"
        "screenshot-window-sizer@gnome-shell-extensions.gcampax.github.com"
        "system-monitor@gnome-shell-extensions.gcampax.github.com"
        "drive-menu@gnome-shell-extensions.gcampax.github.com"
        "light-style@gnome-shell-extensions.gcampax.github.com"
        "Battery-Health-Charging@maniacx.github.com"
        "caffeine@patapon.info"
      ];
    };

    "org/gnome/shell/extensions/appindicator" = {
      remember-mount-password = true;
      tray-pos = "left";
    };

    "org/gnome/shell/extensions/Battery-Health-Charging".show-system-indicator = false;

    "org/gnome/shell/extensions/kimpanel".font = "更纱黑体 UI SC 14";

    "org/gnome/shell/extensions/caffeine" = {
      enable-fullscreen = false;
      screen-blank = "always";
      duration-timer-list = [
        2400
        4800
        7200
      ];
    };

    "org/gnome/shell/extensions/system-monitor" = {
      show-cpu = false;
      show-swap = false;
    };

    "org/gnome/system/location".enabled = false;

    "org/gnome/tweaks".show-extensions-notice = false;

    "org/gtk/gtk4/settings/file-chooser".show-hidden = true;

    "org/gtk/settings/file-chooser" = {
      show-hidden = true;
      sort-directories-first = true;
    };

    "org/gnome/desktop/notifications/application/chromium-browser".enable = false;
  };
}
