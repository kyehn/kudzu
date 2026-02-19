{ inputs, ... }:

final: prev: {
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
  opencode = prev.opencode.overrideAttrs (oldAttrs: {
    installPhase =
      prev.lib.replaceStrings
        [
          "wrapProgram $out/bin/opencode"
        ]
        [
          "wrapProgram $out/bin/opencode --set OPENCODE_DISABLE_DEFAULT_PLUGINS true --set OPENCODE_DISABLE_LSP_DOWNLOAD true"
        ]
        oldAttrs.installPhase;
  });
}
