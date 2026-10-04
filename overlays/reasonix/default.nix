{
  lib,
  buildGoModule,
  fetchFromGitHub,
  makeBinaryWrapper,
  versionCheckHook,
  writableTmpDirAsHomeHook,
  bash,
  codegraph,
  ripgrep,
}:

buildGoModule (finalAttrs: {
  pname = "reasonix";
  version = "2.27.0";

  src = fetchFromGitHub {
    owner = "esengine";
    repo = "DeepSeek-Reasonix";
    tag = "studio-v${finalAttrs.version}";
    hash = "sha256-ApvaHwsIARtYCU4Gs0dfBRwSIRvnPMtV2DLB1yTMu8Y=";
  };

  patches = [ ./fix.patch ];

  vendorHash = "sha256-EuCdkWvu+kvZcecEXBjruAJ0CEQmzZjQpDfuyW/23SE=";

  subPackages = [ "cmd/reasonix" ];

  nativeBuildInputs = [ makeBinaryWrapper ];

  env.CGO_ENABLED = "0";

  ldflags = [
    "-s"
    "-w"
    "-X main.version=v${finalAttrs.version}"
  ];

  doInstallCheck = true;

  nativeInstallCheckInputs = [
    versionCheckHook
    writableTmpDirAsHomeHook
  ];

  versionCheckKeepEnvironment = [ "HOME" ];

  postFixup = ''
    wrapProgram $out/bin/${finalAttrs.meta.mainProgram} \
      --prefix PATH : ${
        lib.makeBinPath [
          bash
          codegraph
          ripgrep
        ]
      }
  '';

  meta.mainProgram = "reasonix";
})
