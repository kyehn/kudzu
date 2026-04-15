{ inputs, ... }:

final: prev: {
  nix = inputs.nix.packages."${prev.stdenv.hostPlatform.system}".default;
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
  putter = inputs.nix-on-droid.legacyPackages."${prev.stdenv.hostPlatform.system}".putter;
}
