{
  lib,
  buildGoModule,
  fetchFromGitHub,
  makeBinaryWrapper,
  versionCheckHook,
  writableTmpDirAsHomeHook,
  ast-grep,
  bash,
  codegraph,
  ripgrep,
}:

buildGoModule (finalAttrs: {
  pname = "reasonix";
  version = "1.25.1";

  src = fetchFromGitHub {
    owner = "esengine";
    repo = "DeepSeek-Reasonix";
    tag = "v${finalAttrs.version}";
    hash = "sha256-uI9YIuhIQlr+sJffgcP1pB7ePMgf86LufHSogTVxOTk=";
  };

  patches = [
    ./alignment.patch
    ./resume-recovery.patch
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
    ast-grep run \
      -p 'for step := 0; state.runMaxSteps <= 0 || step < state.runMaxSteps || state.graceRound || state.recoveryGraceRound; step++ { $$$BODY }' \
      -r 'for step := 0; ; step++ { $$$BODY }' \
      internal/agent/run_loop.go \
      --update-all
    substituteInPlace internal/agent/run_loop.go \
      --replace-fail $'if state.runMaxSteps > 0 && step+1 >= state.runMaxSteps {\n\t\ta.armFinalizationRound(state, landCause{kind: "max_steps", detail: fmt.Sprintf(\n\t\t\t"budget (%s=%d) exhausted: one grace round to finalize", state.runMaxStepsKey, state.runMaxSteps)})\n\t}\n' ""
  '';

  vendorHash = "sha256-tUX+uHFkBtMG2z+DVqdhMj68074srZz1ceC78LX2MbQ=";

  subPackages = [ "cmd/reasonix" ];

  nativeBuildInputs = [
    makeBinaryWrapper
    ast-grep
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
