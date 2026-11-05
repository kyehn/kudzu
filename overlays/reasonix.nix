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
  version = "2.57.0";

  src = fetchFromGitHub {
    owner = "esengine";
    repo = "DeepSeek-Reasonix";
    tag = "v${finalAttrs.version}";
    hash = "sha256-orwyRnp216RPmXOimGnHnVnfn0oYkrDg9+zgjo+bMfo=";
  };

  vendorHash = "sha256-LdqLUrgrn5BYhb1ikzKshE3AiFwFM+QxPvxx4dfWMFI=";

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
