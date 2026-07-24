{
  lib,
  runCommand,
  makeBinaryWrapper,
  pi-coding-agent,
  rust-analyzer,
  ktlint,
  nixd,
  ruff,
  bun,
  openspec,
}:

runCommand "pi"
  {
    buildInputs = [ makeBinaryWrapper ];
  }
  ''
    mkdir --parents $out/bin
    ${lib.replaceStrings
      [
        "wrapProgram $out/bin/pi"
      ]
      [
        "makeWrapper ${lib.getExe' pi-coding-agent ".pi-wrapped"} $out/bin/pi --prefix PATH : ${
          lib.makeBinPath [
            rust-analyzer
            ktlint
            nixd
            ruff
            bun
            openspec
          ]
        }"
      ]
      pi-coding-agent.postFixup
    }
  ''
