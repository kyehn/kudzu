{ inputs, ... }:

final: prev: {
  nix =
    if prev.stdenv.hostPlatform.isLinux then
      inputs.nix.packages."${prev.stdenv.hostPlatform.system}".default
    else
      prev.nixVersions.latest;
  fast-nix-gc = prev.callPackage ./fast-nix-gc.nix { };
  reasonix-config = prev.callPackage ./reasonix-config.nix { };
  reasonix = prev.callPackage ./reasonix.nix { };
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
