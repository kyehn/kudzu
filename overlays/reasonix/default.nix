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
  version = "1.29.0";

  src = fetchFromGitHub {
    owner = "esengine";
    repo = "DeepSeek-Reasonix";
    tag = "v${finalAttrs.version}";
    hash = "sha256-yEBNU/JYZkG2oSRaN4trLnbnQF5Fl05LCltLBUuRlNA=";
  };

  # Single multi-commit patch (git format-patch from v1.29.0, applied in order):
  #   1. vendor: opencode wire alignment (UA, TLS, ids)
  #   2. agent: enforce the configured window; converge must-free folds below it
  #   3. control/acp: force yolo approval and run unbounded (overlay defaults)
  patches = [ ./reasonix-v1.29.0.patch ];

  vendorHash = "sha256-j3CNUEbNarFKQr+fTyf+2oM2FjOF1WnBMSPJHgcz72E=";

  subPackages = [ "cmd/reasonix" ];

  nativeBuildInputs = [
    makeBinaryWrapper
  ];

  env.CGO_ENABLED = "0";

  ldflags = [
    "-s"
    "-w"
    "-X main.version=v${finalAttrs.version}"
  ];

  doCheck = false;

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