{
  buildGoModule,
  fetchFromGitHub,
  versionCheckHook,
}:

buildGoModule (finalAttrs: {
  pname = "opencode2api";
  version = "1.5.1-unstable-2026-11-27";

  src = fetchFromGitHub {
    owner = "jasonxu114514";
    repo = "opencode2api";
    rev = "79277140324df779c1179c79aea81b9df46b4ea1";
    hash = "sha256-cBRcTJn8Z0AivavRG9sLwYElBSA9416OlkjFtwQfQ60=";
  };

  vendorHash = "sha256-aUaU0T9WF/6jMnrujCyVy2ElH5rm/rHhPS0vD1/pKL8=";

  subPackages = [ "cmd/opencode2api" ];

  env.CGO_ENABLED = "0";

  ldflags = [
    "-s"
    "-w"
    "-X main.version=${finalAttrs.version}"
  ];

  meta.mainProgram = "opencode2api";
})
