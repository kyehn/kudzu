{ inputs, ... }:

final: prev: {
  uutils-tar = prev.callPackage ./uutils-tar.nix { };
  uutils-login = prev.callPackage ./uutils-login.nix { };
  uutils-hostname = prev.callPackage ./uutils-hostname.nix { };
  nix = inputs.nix.packages."${prev.stdenv.hostPlatform.system}".default;
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
}
