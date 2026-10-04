{ inputs, ... }:

final: prev: {
  nix =
    if prev.stdenv.hostPlatform.isLinux then
      inputs.nix.packages."${prev.stdenv.hostPlatform.system}".default
    else
      prev.nixVersions.latest;
  fast-nix-gc = prev.callPackage ./fast-nix-gc.nix { };
  maki = prev.callPackage ./maki { };
  maki-config = prev.callPackage ./maki-config.nix { };
  dsh-cordis-patch = prev.callPackage ./dsh-cordis-patch.nix { };
  opencode-config = prev.callPackage ./opencode-config.nix { };
  reasonix = prev.callPackage ./reasonix { };
  reasonix-config = prev.callPackage ./reasonix-config.nix { };
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
