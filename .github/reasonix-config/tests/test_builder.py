from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import ClassVar, Self

import httpx
import pytest

from reasonix_config import __main__ as main_module
from reasonix_config import builder as builder_module
from reasonix_config import fetcher as fetcher_module
from reasonix_config.builder import (
    MODEL_FIELD_HANDLED,
    MODEL_FIELD_IGNORED,
    PROVIDER_FIELD_HANDLED,
    PROVIDER_FIELD_IGNORED,
    _build_override,
    _is_chat_model,
    _is_free,
    _price_of,
    _repair_default_model,
    _wire_kind,
    build_all,
    build_nvidia,
    build_opencode,
    ensure_env_placeholder,
    write_config,
)
from reasonix_config.fetcher import fetch_models_dev, fetch_official_models
from reasonix_config.models import ProviderConfig

ENV_FILE_PERMS = 0o600  # .env 含密钥, 仅属主可读写
DEFAULT_OUTPUT_TOKENS = 4096  # _md_model 夹具的 limit.output
SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "reasonix_config"


def _md_model(**kw: object) -> dict:
    """最小 models.dev 模型条目 (默认可聊天、无价格、非 deprecated)."""
    base: dict = {
        "id": "org/m",
        "limit": {"context": 128000, "output": 4096},
        "modalities": {"input": ["text"], "output": ["text"]},
        "cost": {"input": 0, "output": 0},
    }
    base.update(kw)
    return base


def _md_entry(pid: str, models: dict, **kw: object) -> dict:
    """合成 models.dev provider 条目: 身份字段故意与真实值不同, 证派生."""
    base: dict = {
        "id": pid,
        "name": f"Fake {pid}",
        "npm": "@fake/compat",
        "api": f"https://fake-{pid}.example/v9",
        "env": [f"FAKE_{pid.upper()}_KEY"],
        "doc": "https://example.invalid",
        "models": models,
    }
    base.update(kw)
    return base


def _md_data(entries: dict[str, dict]) -> dict:
    return dict(entries)


_DOWN = OSError("down")


def _raise_down(*args: object, **kwargs: object) -> object:
    raise _DOWN


class TestIsChatModel:
    def test_chat_model(self) -> None:
        assert _is_chat_model("org/m", _md_model()) is True

    def test_embedding_excluded(self) -> None:
        m = _md_model(modalities={"input": ["text"], "output": ["embedding"]})
        assert _is_chat_model("org/e", m) is False

    def test_name_alone_never_excludes(self) -> None:
        # 无名字 blocklist: 可疑名字只要派生检查通过就收录
        assert _is_chat_model("tts-voice-clone-3000", _md_model()) is True

    def test_none_containers_tolerated(self) -> None:
        m = _md_model(limit=None, modalities=None)
        assert _is_chat_model("org/m", m) is False  # context 缺失 -> 0 < 阈值

    def test_small_context_excluded(self) -> None:
        m = _md_model(limit={"context": 4096, "output": 1024})
        assert _is_chat_model("org/m", m) is False

    def test_non_text_output_excluded(self) -> None:
        m = _md_model(modalities={"input": ["text"], "output": ["image"]})
        assert _is_chat_model("org/m", m) is False

    def test_tool_call_false_excluded(self) -> None:
        assert _is_chat_model("org/m", _md_model(tool_call=False)) is False

    def test_tool_call_true_or_absent_allowed(self) -> None:
        assert _is_chat_model("org/m", _md_model(tool_call=True)) is True
        assert _is_chat_model("org/m", _md_model()) is True


class TestFieldCoverage:
    """HANDLED 加 IGNORED 必须覆盖两 provider 下每个真实出现的 key."""

    def test_model_field_coverage(self) -> None:
        md_data = fetch_models_dev()
        seen: set[str] = set()
        for pid in ("opencode", "nvidia"):
            for m in md_data[pid]["models"].values():
                if isinstance(m, dict):
                    seen.update(m.keys())
        uncovered = seen - MODEL_FIELD_HANDLED - MODEL_FIELD_IGNORED
        assert not uncovered, f"models.dev 新增模型字段未归类: {sorted(uncovered)}"

    def test_provider_field_coverage(self) -> None:
        md_data = fetch_models_dev()
        seen: set[str] = set()
        for pid in ("opencode", "nvidia"):
            seen.update(md_data[pid].keys())
        uncovered = seen - PROVIDER_FIELD_HANDLED - PROVIDER_FIELD_IGNORED
        assert not uncovered, f"models.dev 新增 provider 字段未归类: {sorted(uncovered)}"

    def test_billing_currency_set(self) -> None:
        assert builder_module.BILLING_CURRENCY == "USD"


class TestNoHardcodedProviderIdentity:
    """provider 身份字面量禁令: 身份只能来自 models.dev 条目.

    允许: CLI 选择键 ("opencode"/"nvidia")、协议分支常量 RESPONSES_SDK_PACKAGE
    的单一定点 (opencode SDK→wire 协议知识, 非身份)、注释/文档提及.
    """

    BANNED: ClassVar[list[str]] = [
        "https://opencode.ai/zen/v1",
        "https://integrate.api.nvidia.com",
        "OPENCODE_API_KEY",
        "NVIDIA_API_KEY",
        "OpenCode Zen",
        "opencode-responses",
        "big-pickle",
        "@ai-sdk/openai-compatible",
        "@ai-sdk/anthropic",
        "@ai-sdk/google",
    ]

    def _code_lines(self, name: str) -> list[str]:
        text = (SRC_DIR / name).read_text()
        # 去掉注释与 docstring 行: 允许文档提及, 禁止代码使用
        out: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", '"""', "'''")):
                continue
            out.append(line)
        return out

    def test_no_identity_literals_in_src(self) -> None:
        for name in ("builder.py", "fetcher.py", "__main__.py"):
            for i, line in enumerate(self._code_lines(name), 1):
                if "RESPONSES_SDK_PACKAGE" in line:
                    continue  # 协议分支定点, 见 test_responses_discriminator_documented
                for lit in self.BANNED:
                    assert lit not in line, f"{name}:{i} 含身份字面量 {lit!r}: {line.strip()}"

    def test_responses_discriminator_documented(self) -> None:
        text = (SRC_DIR / "builder.py").read_text()
        assert text.count('"@ai-sdk/openai"') == 1, "协议分支常量必须有且仅有一处定义点"


class TestProviderDerivation:
    """合成异形 provider 条目 → 输出身份字段必须跟随条目 (派生证明)."""

    def test_identity_follows_entry(self) -> None:
        entry = _md_entry("opencode", {"m1": _md_model()})
        md = _md_data({"opencode": entry})
        official = {"data": [{"id": "m1"}]}
        (cfg,) = build_opencode("opencode", md, official, "https://fake/v9/models")
        assert cfg.base_url == "https://fake-opencode.example/v9"
        assert cfg.api_key_env == "FAKE_OPENCODE_KEY"
        assert cfg.name == "opencode"

    def test_nvidia_identity_follows_entry(self) -> None:
        entry = _md_entry("nvidia", {"n1": _md_model()})
        md = _md_data({"nvidia": entry})
        official = {"data": [{"id": "n1"}]}
        cfg = build_nvidia("nvidia", md, official, "https://fake/v9/models")
        assert cfg.base_url == "https://fake-nvidia.example/v9"
        assert cfg.api_key_env == "FAKE_NVIDIA_KEY"
        assert cfg.headers == {"NVCF-POLL-SECONDS": "3600"}

    def test_split_name_derived(self) -> None:
        entry = _md_entry(
            "opencode",
            {
                "chat": _md_model(),
                "resp": _md_model(provider={"npm": "@ai-sdk/openai"}),
            },
        )
        md = _md_data({"opencode": entry})
        official = {"data": [{"id": "chat"}, {"id": "resp"}]}
        cfgs = {c.name: c for c in build_opencode("opencode", md, official, "u")}
        assert set(cfgs) == {"opencode", "opencode-responses"}
        assert cfgs["opencode-responses"].kind == "responses"
        assert cfgs["opencode"].kind == "openai"
        # responses 桶无状态续接, chat 桶不设该字段
        assert cfgs["opencode-responses"].responses_mode == "stateless"
        assert cfgs["opencode"].responses_mode is None


class TestStatusFailClosed:
    def test_unknown_status_raises(self) -> None:
        entry = _md_entry("opencode", {"m1": _md_model(status="expired")})
        md = _md_data({"opencode": entry})
        with pytest.raises(SystemExit, match="unknown status"):
            build_opencode("opencode", md, {"data": [{"id": "m1"}]}, "u")

    def test_deprecated_excluded(self) -> None:
        entry = _md_entry("opencode", {"m1": _md_model(status="deprecated")})
        md = _md_data({"opencode": entry})
        with pytest.raises(SystemExit, match="No free opencode"):
            build_opencode("opencode", md, {"data": [{"id": "m1"}]}, "u")

    def test_missing_entry_fail_closed(self) -> None:
        with pytest.raises(SystemExit, match="no 'nope' provider"):
            build_opencode("nope", {}, {"data": []}, "u")

    def test_entry_missing_keys_fail_closed(self) -> None:
        entry = _md_entry("opencode", {})
        del entry["api"]
        with pytest.raises(SystemExit, match="no usable 'api'"):
            build_opencode("opencode", _md_data({"opencode": entry}), {"data": []}, "u")


class TestOfficialIntersection:
    def test_official_only_excluded(self) -> None:
        """官方有而 models.dev 未收录: 无法证明免费与能力, 排除."""
        entry = _md_entry("opencode", {"m1": _md_model()})
        md = _md_data({"opencode": entry})
        official = {"data": [{"id": "m1"}, {"id": "ghost"}]}
        (cfg,) = build_opencode("opencode", md, official, "u")
        assert cfg.models == ["m1"]

    def test_paid_excluded_cost_rule(self) -> None:
        m = _md_model(cost={"input": 1, "output": 2})
        entry = _md_entry("opencode", {"m1": m})
        md = _md_data({"opencode": entry})
        with pytest.raises(SystemExit, match="No free opencode"):
            build_opencode("opencode", md, {"data": [{"id": "m1"}]}, "u")

    def test_missing_cost_not_free(self) -> None:
        # 缺 cost/缺分项一律不算免费 (paid-leak 方向 fail-closed)
        for cost in (None, {}, {"input": 0}, {"output": 0}):
            m = _md_model() if cost is None else _md_model(cost=cost)
            if cost is None:
                del m["cost"]
            entry = _md_entry("opencode", {"m1": m})
            md = _md_data({"opencode": entry})
            with pytest.raises(SystemExit, match="No free opencode"):
                build_opencode("opencode", md, {"data": [{"id": "m1"}]}, "u")

    def test_official_shape_fail_closed(self) -> None:
        entry = _md_entry("opencode", {"m1": _md_model()})
        md = _md_data({"opencode": entry})
        with pytest.raises(SystemExit, match="unexpected shape"):
            build_opencode("opencode", md, {"items": []}, "u")

    def test_official_entry_without_id_fail_closed(self) -> None:
        entry = _md_entry("opencode", {"m1": _md_model()})
        md = _md_data({"opencode": entry})
        with pytest.raises(SystemExit, match="without id"):
            build_opencode("opencode", md, {"data": [{}]}, "u")


class TestWireKind:
    def test_responses_package(self) -> None:
        m = _md_model(provider={"npm": "@ai-sdk/openai"})
        assert _wire_kind(m, "@fake/compat") == "responses"

    def test_provider_default_chat(self) -> None:
        m = _md_model(provider=None)
        assert _wire_kind(m, "@fake/compat") == "openai"

    def test_other_packages_default_to_chat(self) -> None:
        assert (
            _wire_kind(_md_model(provider={"npm": "@ai-sdk/anthropic"}), "@fake/compat") == "openai"
        )

    def test_missing_metadata_defaults_to_chat(self) -> None:
        assert _wire_kind({}, "@fake/compat") == "openai"


class TestEffortsFromReasoningOptions:
    def test_effort_values(self) -> None:
        opts = [{"type": "effort", "values": ["low", "xhigh"]}]
        m = _md_model(reasoning=True, reasoning_options=opts)
        ov = _build_override(m)
        assert ov["supported_efforts"] == ["low", "xhigh"]
        assert ov["default_effort"] == "xhigh"

    def test_toggle_fallback(self) -> None:
        m = _md_model(reasoning=True, reasoning_options=[{"type": "toggle"}])
        ov = _build_override(m)
        assert ov["supported_efforts"] == ["high"]

    def test_no_options_single_high(self) -> None:
        # 无元数据不发明梯度: 单档 high, 误档由 NormalizeEffort 报错
        m = _md_model(reasoning=True, reasoning_options=[])
        ov = _build_override(m)
        assert ov["supported_efforts"] == ["high"]
        assert ov["default_effort"] == "high"

    def test_no_reasoning_no_efforts(self) -> None:
        m = _md_model(reasoning=False)
        ov = _build_override(m)
        assert "supported_efforts" not in ov
        assert "reasoning_protocol" not in ov


class TestProviderConfig:
    def test_to_toml_multi_model(self) -> None:
        p = ProviderConfig(name="t", base_url="https://x.example", models=["a", "b"])
        d = p.to_toml()
        assert d["models"] == ["a", "b"]
        assert "model" not in d

    def test_to_toml_single_model(self) -> None:
        p = ProviderConfig(name="t", base_url="https://x.example", models=["a"])
        assert p.to_toml()["model"] == "a"


class TestRepairDefaultModel:
    def test_valid_bare_model_preserved(self) -> None:
        existing: dict = {"default_model": "a", "providers": []}
        _repair_default_model(existing, [ProviderConfig(name="t", base_url="u", models=["a"])])
        assert existing["default_model"] == "a"

    def test_invalid_model_repaired(self) -> None:
        existing: dict = {"default_model": "gone", "providers": []}
        _repair_default_model(existing, [ProviderConfig(name="t", base_url="u", models=["a"])])
        assert existing["default_model"] == "a"


class TestTomlSchemaValidity:
    def test_provider_keys_valid(self) -> None:
        allowed = {
            "name",
            "kind",
            "base_url",
            "chat_url",
            "model",
            "models",
            "default",
            "api_key_env",
            "context_window",
            "max_output_tokens",
            "balance_url",
            "responses_mode",
            "price",
            "prices",
            "billing_currency",
            "model_overrides",
            "reasoning_protocol",
            "supported_efforts",
            "default_effort",
            "vision",
            "vision_models",
            "vision_detail",
            "thinking",
            "effort",
            "headers",
            "extra_body",
            "no_proxy",
        }
        entry = _md_entry("opencode", {"m1": _md_model()})
        cfgs = build_opencode(
            "opencode", _md_data({"opencode": entry}), {"data": [{"id": "m1"}]}, "u"
        )
        for cfg in cfgs:
            assert set(cfg.to_toml()) <= allowed

    def test_override_uses_max_output_tokens_not_max_output(self) -> None:
        ov = _build_override(_md_model())
        assert "max_output" not in ov
        assert ov["max_output_tokens"] == DEFAULT_OUTPUT_TOKENS

    def test_prices_have_usd_currency(self) -> None:
        m = _md_model(cost={"input": 1, "output": 2, "cache_read": 0.5})
        price = _price_of(m)
        assert price is not None
        assert price.currency == "USD"


class TestEnsureEnvPlaceholder:
    """占位键名必须由调用方传入 (派生), 函数内无字面量."""

    def test_creates_with_given_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(builder_module, "REASONIX_CONFIG", tmp_path / "config.toml")
        ensure_env_placeholder("FAKE_SYNTHETIC_KEY")
        content = (tmp_path / ".env").read_text()
        assert "FAKE_SYNTHETIC_KEY=public" in content
        assert (tmp_path / ".env").stat().st_mode & 0o777 == ENV_FILE_PERMS

    def test_preserves_existing_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(builder_module, "REASONIX_CONFIG", tmp_path / "config.toml")
        (tmp_path / ".env").write_text("FAKE_SYNTHETIC_KEY=user-real-key\n")
        ensure_env_placeholder("FAKE_SYNTHETIC_KEY")
        assert (tmp_path / ".env").read_text() == "FAKE_SYNTHETIC_KEY=user-real-key\n"


class TestWriteConfig:
    def test_requires_existing_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(builder_module, "REASONIX_CONFIG", tmp_path / "nonexistent.toml")
        with pytest.raises(SystemExit, match="does not exist"):
            write_config([ProviderConfig(name="t", base_url="https://x.example", models=["a"])])

    def test_preserves_valid_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('config_version = 5\ndefault_model = "a"\n')
        monkeypatch.setattr(builder_module, "REASONIX_CONFIG", cfg)
        write_config([ProviderConfig(name="t", base_url="https://x.example", models=["a"])])
        with cfg.open("rb") as f:
            assert tomllib.load(f)["default_model"] == "a"


class TestBuildAllAuthRetry:
    """无认证失败后带 key 重试 (NIM 路径), 仍无 key 则 fail-closed."""

    def test_retry_with_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[bool] = []

        def fake_fetch(entry: dict, pid: str, api_key: str = "") -> dict:
            calls.append(bool(api_key))
            if not api_key:
                msg = "unauthorized"
                raise SystemExit(msg)
            return {"data": []}

        monkeypatch.setattr(builder_module, "fetch_official_models", fake_fetch)
        monkeypatch.setenv("FAKE_K", "s")
        entry = _md_entry("opencode", {})
        entry["env"] = ["FAKE_K"]
        out = builder_module._fetch_official_list(entry, "opencode")
        assert out == {"data": []}
        assert calls == [False, True]

    def test_no_key_reraises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_fetch(entry: dict, pid: str, api_key: str = "", use_cache: bool = True) -> dict:
            msg = "unauthorized"
            raise SystemExit(msg)

        monkeypatch.setattr(builder_module, "fetch_official_models", fake_fetch)
        monkeypatch.delenv("FAKE_K", raising=False)
        entry = _md_entry("opencode", {})
        entry["env"] = ["FAKE_K"]
        with pytest.raises(SystemExit, match="needs FAKE_K"):
            builder_module._fetch_official_list(entry, "opencode")

    def test_no_key_skips_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 无 key 时不读缓存 (缓存可能是带 key 拉的旧名单, 读它等于绕过 key 门)
        seen: list[bool] = []

        def fake_fetch(entry: dict, pid: str, api_key: str = "", use_cache: bool = True) -> dict:
            seen.append(use_cache)
            assert pid == "opencode"
            return {"data": []}

        monkeypatch.setattr(builder_module, "fetch_official_models", fake_fetch)
        monkeypatch.delenv("FAKE_K", raising=False)
        entry = _md_entry("opencode", {})
        entry["env"] = ["FAKE_K"]
        out = builder_module._fetch_official_list(entry, "opencode")
        assert out == {"data": []}
        assert seen == [False]

    def test_keyed_path_may_use_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 有 key 时缓存可用 (key 门已过, 缓存命中省一次请求)
        seen: list[bool] = []

        def fake_fetch(entry: dict, pid: str, api_key: str = "", use_cache: bool = True) -> dict:
            seen.append(use_cache)
            return {"data": []}

        monkeypatch.setattr(builder_module, "fetch_official_models", fake_fetch)
        monkeypatch.setenv("FAKE_K", "s")
        entry = _md_entry("opencode", {})
        entry["env"] = ["FAKE_K"]
        out = builder_module._fetch_official_list(entry, "opencode")
        assert out == {"data": []}
        assert seen == [True]


class TestProbe:
    def test_only_404_marks_dead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        class FakeResp:
            def __init__(self, status: int) -> None:
                self.status_code = status

        class FakeClient:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            def __enter__(self) -> Self:
                return self

            def __exit__(self, *a: object) -> None:
                pass

            def post(self, url: str, headers: dict, json: dict) -> FakeResp:
                calls.append(json["model"])
                assert url == "https://fake.example/v9/chat/completions", url
                if json["model"] == "gone":
                    return FakeResp(404)
                if json["model"] == "flaky":
                    msg = "slow"
                    raise httpx.ReadTimeout(msg)
                return FakeResp(200)

        monkeypatch.setattr(fetcher_module.httpx, "Client", FakeClient)
        dead = fetcher_module.probe_nvidia_live(
            ["gone", "flaky", "ok"], "k", "https://fake.example/v9"
        )
        assert dead == {"gone"}


class TestNvidiaDeadLiveFailOpen:
    def test_no_key_skips_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entry = _md_entry("nvidia", {})
        monkeypatch.delenv("FAKE_NVIDIA_KEY", raising=False)
        assert main_module._nvidia_dead_live({}, entry) == set()

    def test_official_fetch_error_keeps_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entry = _md_entry("nvidia", {})
        monkeypatch.setenv("FAKE_NVIDIA_KEY", "k")
        monkeypatch.setattr(main_module, "_fetch_official_list", _raise_down)
        assert main_module._nvidia_dead_live({}, entry) == set()

    def test_probe_error_keeps_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entry = _md_entry("nvidia", {"n1": _md_model()})
        md = _md_data({"nvidia": entry})
        monkeypatch.setenv("FAKE_NVIDIA_KEY", "k")
        monkeypatch.setattr(
            main_module, "_fetch_official_list", lambda *a, **k: {"data": [{"id": "n1"}]}
        )
        monkeypatch.setattr(main_module, "probe_nvidia_live", _raise_down)
        assert main_module._nvidia_dead_live(md, entry) == set()


class TestLiveIntegration:
    """实网集成 (需网络; 缓存 TTL 内复用快照)."""

    def test_live_opencode_split(self) -> None:
        md_data = fetch_models_dev()
        entry = md_data["opencode"]
        official = fetch_official_models(entry, "opencode")
        cfgs = {
            c.name: c
            for c in build_opencode(
                "opencode", md_data, official, f"{entry['api'].rstrip('/')}/models"
            )
        }
        assert set(cfgs) == {"opencode", "opencode-responses"}
        assert cfgs["opencode"].base_url == entry["api"]
        assert cfgs["opencode"].api_key_env == entry["env"][0]
        sparks = [m for m in cfgs["opencode-responses"].models if "spark" in m]
        assert len(sparks) >= 1
        assert not (set(cfgs["opencode"].models) & set(cfgs["opencode-responses"].models))

    def test_live_nvidia_build(self) -> None:
        if not os.environ.get("NVIDIA_API_KEY", "").strip():
            pytest.skip("needs NVIDIA_API_KEY")
        md_data = fetch_models_dev()
        entry = md_data["nvidia"]
        official = fetch_official_models(entry, "nvidia", os.environ["NVIDIA_API_KEY"].strip())
        cfg = build_nvidia("nvidia", md_data, official, "u")
        assert cfg.base_url == entry["api"]
        assert len(cfg.models) > 0


class TestCrossPinVersion:
    """TS 的 OPENCODE_VERSION 必须与 fix.patch 的 UA 同源 (wire 指纹一致性)."""

    TS_PATH = Path(__file__).resolve().parent.parent.parent / "pi-opencode" / "index.ts"
    PATCH_PATH = (
        Path(__file__).resolve().parent.parent.parent.parent / "overlays" / "reasonix" / "fix.patch"
    )

    def test_opencode_version_matches_patch_ua(self) -> None:
        text = self.TS_PATH.read_text()
        match = re.search(r'OPENCODE_VERSION\s*=\s*"([^"]+)"', text)
        assert match
        patch = self.PATCH_PATH.read_text()
        assert f"opencode/beta/{match.group(1)}/cli" in patch


class TestIsFreeExplicit:
    """免费必须显式零值; 缺失一律不算 (paid-leak fail-closed)."""

    def test_explicit_zeros_free(self) -> None:
        assert _is_free({"cost": {"input": 0, "output": 0}}) is True

    def test_missing_cost_not_free(self) -> None:
        assert _is_free({}) is False
        assert _is_free({"cost": None}) is False

    def test_partial_cost_not_free(self) -> None:
        assert _is_free({"cost": {"input": 0}}) is False
        assert _is_free({"cost": {"output": 0}}) is False

    def test_paid_not_free(self) -> None:
        assert _is_free({"cost": {"input": 0.5, "output": 0}}) is False


class TestVisionMapping:
    def test_attachment_true(self) -> None:
        assert _build_override(_md_model(attachment=True))["vision"] is True

    def test_image_input(self) -> None:
        m = _md_model(modalities={"input": ["text", "image"], "output": ["text"]})
        assert _build_override(m)["vision"] is True

    def test_text_only_no_vision_key(self) -> None:
        assert "vision" not in _build_override(_md_model())


class TestPriceEdges:
    def test_free_has_no_price(self) -> None:
        assert _price_of({"cost": {"input": 0, "output": 0}}) is None

    def test_cache_write_ignored(self) -> None:
        # cache_write 无对应字段: 不进价格表…
        assert _price_of({"cost": {"cache_write": 1}}) is None
        # …且不算免费准入 (input/output 缺失)
        assert _is_free({"cost": {"cache_write": 1}}) is False

    def test_cache_read_maps_to_cache_hit(self) -> None:
        cache_read = 0.1
        price = _price_of({"cost": {"input": 0, "output": 0, "cache_read": cache_read}})
        assert price is not None
        assert price.cache_hit == cache_read


class TestBuildAllIsolation:
    """单家失败只记 errors, 不丢另一家的成功构建."""

    def _md(self) -> dict:
        return {
            "opencode": _md_entry("opencode", {"m1": _md_model()}),
            "nvidia": _md_entry("nvidia", {"n1": _md_model()}),
        }

    def _official(self) -> dict:
        return {"opencode": {"data": [{"id": "m1"}]}, "nvidia": {"data": [{"id": "n1"}]}}

    def test_both_ok_no_errors(self) -> None:
        providers, errors = build_all(md_data=self._md(), official=self._official())
        assert errors == []
        assert {p.name for p in providers} == {"opencode", "nvidia"}

    def test_bad_status_isolates_provider(self) -> None:
        md = self._md()
        md["opencode"]["models"]["m1"]["status"] = "expired"
        providers, errors = build_all(md_data=md, official=self._official())
        assert [p.name for p in providers] == ["nvidia"]
        assert len(errors) == 1
        assert "unknown status" in errors[0]

    def test_all_bad_returns_errors(self) -> None:
        md = self._md()
        md["opencode"]["models"]["m1"]["status"] = "expired"
        md["nvidia"]["models"]["n1"]["status"] = "weird"
        providers, errors = build_all(md_data=md, official=self._official())
        assert providers == []
        assert len(errors) == len(self._md())

    def test_provider_filter(self) -> None:
        providers, errors = build_all(
            providers_filter=["nvidia"], md_data=self._md(), official=self._official()
        )
        assert [p.name for p in providers] == ["nvidia"]
        assert errors == []


class TestMainErrors:
    """main 先写成功部分, 再凭 errors 非零退出."""

    def test_writes_good_then_exits_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = ProviderConfig(name="t", base_url="https://x.example", models=["a"])

        def _no_models() -> dict:
            return {}

        def _boom(**kwargs: object) -> tuple:
            return [cfg], ["boom"]

        monkeypatch.setattr(main_module, "fetch_models_dev", _no_models)
        monkeypatch.setattr(main_module, "build_all", _boom)
        written: list = []
        monkeypatch.setattr(main_module, "write_config", lambda ps: written.extend(ps) or "p")
        with pytest.raises(SystemExit) as exc:
            main_module.main(["--provider", "opencode"])
        assert exc.value.code == 1
        assert written == [cfg]

    def test_clean_run_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cfg = ProviderConfig(name="opencode", base_url="https://x.example", models=["a"])

        def _no_models() -> dict:
            return {}

        def _clean(**kwargs: object) -> tuple:
            return [cfg], []

        monkeypatch.setattr(main_module, "fetch_models_dev", _no_models)
        monkeypatch.setattr(main_module, "build_all", _clean)
        monkeypatch.setattr(main_module, "write_config", lambda ps: "p")
        monkeypatch.setattr(main_module, "ensure_env_placeholder", lambda k: None)
        main_module.main(["--provider", "opencode"])
        out = capsys.readouterr().out
        assert "Written 1 provider" in out
