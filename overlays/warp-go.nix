{
  buildGoModule,
  fetchFromGitHub,
  go_1_27,
  versionCheckHook,
}:

buildGoModule (finalAttrs: {
  pname = "warp-go";
  version = "0.6.9";

  src = fetchFromGitHub {
    owner = "callacat";
    repo = "warp-go";
    tag = "v${finalAttrs.version}";
    hash = "sha256-pgwheSi3nw9nkGOxCqtFmb0nAAS09IdlMRE+hRxe5LU=";
  };

  vendorHash = "sha256-1nuD0iYVNjUfXp8Pj9WuJtxmhj0RHl85fGNDMZu7s/0=";

  subPackages = [ "." ];

  go = go_1_27;

  env.CGO_ENABLED = "0";

  ldflags = [
    "-s"
    "-w"
    "-X main.version=${finalAttrs.version}"
  ];

  doInstallCheck = true;

  nativeInstallCheckInputs = [ versionCheckHook ];

  versionCheckProgramArg = "-version";

  meta.mainProgram = "warp";
})
