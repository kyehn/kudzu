{ inputs, ... }:

final: prev: {
  nix =
    if (prev.stdenv.hostPlatform.isLinux && prev.stdenv.targetPlatform.isAarch64) then
      prev.lixPackageSets.latest.lix
    else if (prev.stdenv.hostPlatform.isLinux) then
      inputs.nix.packages."${prev.stdenv.hostPlatform.system}".default
    else
      prev.nixVersions.latest;
  fast-nix-gc = prev.callPackage ./fast-nix-gc.nix { };
  opencode-config = prev.callPackage ./opencode-config.nix { };
  maki = prev.callPackage ./maki.nix { };
  maki-config = prev.callPackage ./maki-config.nix { };
  dsh-cordis-patch = prev.callPackage ./dsh-cordis-patch.nix { };
  reasonix = prev.callPackage ./reasonix.nix { };
  reasonix-config = prev.callPackage ./reasonix-config.nix { };
  warp-go = prev.callPackage ./warp-go.nix { };
  pi-agent-settings = prev.callPackage ./pi-agent-settings.nix { };
  pi-agent-mcp = prev.callPackage ./pi-agent-mcp.nix { };
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
