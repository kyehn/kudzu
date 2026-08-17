from __future__ import annotations

import json
import re
from pathlib import Path

from reasonix_config.fetcher import MODELS_DEV_USER_AGENT, OPENCODE_VERSION

# 仓库根: .github/reasonix-config/tests/../../.. = 仓库根
REPO_ROOT = Path(__file__).resolve().parents[3]
ALIGNMENT_PATCH = REPO_ROOT / "overlays" / "reasonix" / "alignment.patch"
ZEN_CAPTURE = REPO_ROOT / "overlays" / "reasonix" / "opencode" / "POST_zen_v1_chat_completions.json"
DSH_SIM = REPO_ROOT / "overlays" / "dsh" / "opencode-sim" / "opencode-sim.mjs"

PATCH_UA_RE = re.compile(r'opencodeUserAgent\s*=\s*"opencode/([0-9]+\.[0-9]+\.[0-9]+)')
CAPTURE_UA_RE = re.compile(r"opencode/([0-9]+\.[0-9]+\.[0-9]+)")
DSH_SIM_UA_RE = re.compile(r'OPENCODE_USER_AGENT\s*=\s*"opencode/([0-9]+\.[0-9]+\.[0-9]+)')


class TestOpenCodeVersionConsistency:
    """opencode 模拟的版本多源互锁, 漂移即视为模拟失配:

    1. fetcher 抓取 models.dev / zen models 时携带的 UA (MODELS_DEV_USER_AGENT)
    2. overlays/reasonix/alignment.patch 中 opencodeUserAgent 常量
       (reasonix 打包补丁注入 zen 请求的 UA, opencode/1.18.18 ai-sdk/...)
    3. overlays/reasonix/opencode/POST_zen_v1_chat_completions.json 抓包里
       真实 opencode CLI 发出的 UA 版本
    4. overlays/dsh/opencode-sim/opencode-sim.mjs 中 OPENCODE_USER_AGENT 常量
       (dsh 打包注入 zen 请求的 UA)

    任一升版都必须同步全部来源, 否则测试失败。
    """

    def test_fetcher_ua_matches_open_code_version(self) -> None:
        assert f"opencode/prod/{OPENCODE_VERSION}/cli" == MODELS_DEV_USER_AGENT

    def test_patch_ua_version_matches(self) -> None:
        assert ALIGNMENT_PATCH.exists(), f"miss: {ALIGNMENT_PATCH}"
        m = PATCH_UA_RE.search(ALIGNMENT_PATCH.read_text())
        assert m is not None, "alignment.patch 中找不到 opencodeUserAgent 常量"
        assert m.group(1) == OPENCODE_VERSION, (
            f"alignment.patch UA 版本 {m.group(1)} 与 fetcher {OPENCODE_VERSION} 不一致"
        )

    def test_capture_ua_version_matches(self) -> None:
        assert ZEN_CAPTURE.exists(), f"miss: {ZEN_CAPTURE}"
        data = json.loads(ZEN_CAPTURE.read_text())
        ua = data["request"]["headers"]["User-Agent"]
        m = CAPTURE_UA_RE.search(ua)
        assert m is not None, f"抓包样本 UA 无法解析: {ua!r}"
        assert m.group(1) == OPENCODE_VERSION, (
            f"抓包样本 UA 版本 {m.group(1)} 与 fetcher {OPENCODE_VERSION} 不一致"
        )

    def test_dsh_sim_ua_matches(self) -> None:
        assert DSH_SIM.exists(), f"miss: {DSH_SIM}"
        m = DSH_SIM_UA_RE.search(DSH_SIM.read_text())
        assert m is not None, "opencode-sim.mjs 中找不到 OPENCODE_USER_AGENT 常量"
        assert m.group(1) == OPENCODE_VERSION, (
            f"opencode-sim.mjs UA 版本 {m.group(1)} 与 fetcher {OPENCODE_VERSION} 不一致"
        )

    def test_capture_has_fingerprint_benchmark(self) -> None:
        """抓包基准必须带 ClientHello 指纹 (dsh/reasonix TLS 模拟的目标值)."""
        data = json.loads(ZEN_CAPTURE.read_text())
        fp = data["client_fingerprint"]
        assert re.fullmatch(r"[0-9a-f]{32}", fp["ja3"])
        assert fp["ja4"].startswith("i")
