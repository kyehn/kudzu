{ inputs, ... }:

final: prev: {
  nix = inputs.nix.packages."${prev.stdenv.hostPlatform.system}".default;
  openclaude = prev.callPackage ./openclaude { };
  opencode-bin = prev.callPackage ./opencode-bin.nix { };
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
