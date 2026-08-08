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
  fetchpatch2,
}:

buildGoModule (finalAttrs: {
  pname = "reasonix";
  version = "1.21.3";

  src = fetchFromGitHub {
    owner = "esengine";
    repo = "DeepSeek-Reasonix";
    tag = "v${finalAttrs.version}";
    hash = "sha256-xRiYAcVXb+phAUq5khKVLFN+qANoHOPbMLTUPuVJcBA=";
  };

  patches = [
    (fetchpatch2 {
      url = "https://github.com/esengine/DeepSeek-Reasonix/commit/4128012e2e7750cdb9bac3edd074109077e68ce6.patch?full_index=1";
      hash = "sha256-jTNfsaM0Xq661jJnDw7nYB0SmCKpyutyiC9osJsUAsk=";
    })
    # Compaction runs with thinking disabled (fast, cheap summarization).
    # Applies to v1.21.3 sources; must be re-checked when bumping version.
    ../patches/reasonix-compact-no-think.patch
  ];

  postPatch = ''
    substituteInPlace internal/acp/service.go \
      --replace-fail "ctrl.EnableInteractiveApproval()" $'ctrl.EnableInteractiveApproval()\n\tctrl.SetToolApprovalMode(control.ToolApprovalYolo)' \
      --replace-fail "cfgState = withToolApprovalConfig(cfgState, control.ToolApprovalAsk)" "cfgState = withToolApprovalConfig(cfgState, control.ToolApprovalYolo)" \
      --replace-fail "toolApprovalMode: control.ToolApprovalAsk," "toolApprovalMode: control.ToolApprovalYolo," \
      --replace-fail "toolApprovalMode := normalizeACPToolApprovalMode(saved.ToolApprovalMode)" "toolApprovalMode := control.ToolApprovalYolo"
    substituteInPlace internal/control/approval.go \
      --replace-fail $'func (a *approvalManager) bypassAllowsLocked(tool, subject string, args json.RawMessage) bool {\n\tif requiresFreshApprovalTool(tool) {\n\t\treturn false\n\t}\n\tif a.toolApprovalMode == ToolApprovalYolo {\n\t\treturn true\n\t}' $'func (a *approvalManager) bypassAllowsLocked(tool, subject string, args json.RawMessage) bool {\n\tif a.toolApprovalMode == ToolApprovalYolo {\n\t\treturn true\n\t}\n\tif requiresFreshApprovalTool(tool) {\n\t\treturn false\n\t}' \
      --replace-fail $'if fresh {\n\t\treturn a.sessionGrantAllowsLocked(tool, subject)\n\t}\n\tif requireHuman {' $'if fresh {\n\t\tif a.toolApprovalMode == ToolApprovalYolo {\n\t\t\treturn true\n\t\t}\n\t\treturn a.sessionGrantAllowsLocked(tool, subject)\n\t}\n\tif requireHuman {'
  '';

  vendorHash = "sha256-Byt7/DbSHZ+PJ8evWARRQHds/kyuydTyYH98pFwAxNY=";

  subPackages = [ "cmd/reasonix" ];

  nativeBuildInputs = [ makeBinaryWrapper ];

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
