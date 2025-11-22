{ lib, pkgs, ... }:

{
  environment = {
    systemPackages =
      (with pkgs.gnomeExtensions; [
        appindicator
        kimpanel
        caffeine
        battery-health-charging
        light-style
        removable-drive-menu
        system-monitor
        screenshot-window-sizer
        auto-move-windows
      ])
      ++ (with pkgs; [
        dconf-editor
        refine
      ]);
    gnome.excludePackages = with pkgs; [
      decibels
      evince
      orca
      gnome-tour
      gnome-menus
      baobab
      epiphany
      gnome-connections
      gnome-console
      yelp
      gnome-terminal
      geary
      gnome-calendar
      simple-scan
      totem
      file-roller
      seahorse
      gnome-contacts
      gnome-initial-setup
      gnome-music
      gnome-clocks
      gnome-characters
      gnome-maps
      gnome-weather
      gnome-software
      tali
      iagno
      hitori
      atomix
      gnome-text-editor
    ];
  };
  services = {
    hardware.bolt.enable = false;
    gnome = {
      at-spi2-core.enable = lib.mkForce false;
      gnome-user-share.enable = false;
      gnome-online-accounts.enable = false;
      gnome-browser-connector.enable = false;
      gnome-initial-setup.enable = false;
      games.enable = false;
      tinysparql.enable = false;
      localsearch.enable = false;
      rygel.enable = false;
      gnome-remote-desktop.enable = false;
      evolution-data-server.enable = lib.mkForce false;
    };
    desktopManager.gnome.enable = true;
  };
  systemd.user.services = {
    "org.gnome.SettingsDaemon.Sharing".enable = false;
    "org.gnome.SettingsDaemon.Smartcard".enable = false;
    "org.gnome.SettingsDaemon.Wacom".enable = false;
  };
}
