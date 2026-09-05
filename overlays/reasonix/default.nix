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
  version = "1.37.0";

  src = fetchFromGitHub {
    owner = "esengine";
    repo = "DeepSeek-Reasonix";
    tag = "v${finalAttrs.version}";
    hash = "sha256-3hnKfWdNFsnhg6Tz/EtOAjgpVZj6YBTxtd7VM77MBRw=";
  };

  patches = [ ./fix.patch ];

  vendorHash = "sha256-+0V+goT5XhpJcWteAuSjw8uslKcnzebT6UvgGPEaCE0=";

  subPackages = [ "cmd/reasonix" ];

  nativeBuildInputs = [ makeBinaryWrapper ];

  env.CGO_ENABLED = "0";

  ldflags = [
    "-s"
    "-w"
    "-X main.version=v${finalAttrs.version}"
  ];

  doCheck = true;

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
