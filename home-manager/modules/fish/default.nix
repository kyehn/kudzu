{
  lib,
  config,
  ...
}:

{
  programs.fish = {
    enable = true;
    interactiveShellInit =
      (lib.optionalString false ''
        set_proxy_from_gsettings
      '')
      + (lib.optionalString config.programs.bun.enable ''
        set -x BUN_INSTALL $HOME/.bun
        set -x PATH $PATH $BUN_INSTALL/bin
      '');
    functions = {
      proxy_off = "set -ge all_proxy ALL_PROXY no_proxy NO_PROXY http_proxy HTTP_PROXY https_proxy HTTPS_PROXY ftp_proxy FTP_PROXY rsync_proxy RSYNC_PROXY socks_proxy SOCKS_PROXY";
      proxy_on_from_gsettings = builtins.readFile ./proxy_on_from_gsettings.fish;
      set_proxy_from_gsettings = ''
        if test "$TERM" = "alacritty"
            proxy_on_from_gsettings
        end
      '';
    };
  };
}
