from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import ClassVar

import pytest

from reasonix_config import builder as builder_module
from reasonix_config.builder import (
    CONFIG_VERSION,
    _build_override,
    _is_chat_model,
    _repair_default_model,
    _wire_kind,
    build_all,
    build_nvidia,
    build_opencode,
    get_free_zen_model_ids,
    write_config,
)
from reasonix_config.fetcher import MODELS_DEV_CACHE, ZEN_CACHE, fetch_models_dev, fetch_zen_models
from reasonix_config.models import ProviderConfig

EXPECTED_PROVIDER_COUNT = 3  # opencode + opencode-responses + nvidia
# muse-spark-1.2-contributor-free 的 models.dev limit (2026-08 快照)
MUSE_SPARK_CONTEXT = 1_048_576
MUSE_SPARK_OUTPUT = 131_072
ENV_FILE_PERMS = 0o600  # .env 含密钥, 仅属主可读写


def _load_zen_cache() -> dict:
    if not ZEN_CACHE.exists():
        pytest.skip("zen cache not found at /tmp/reasonix-models/opencode_zen_models.json")
    return json.loads(ZEN_CACHE.read_text())


def _load_md_cache() -> dict:
    if not MODELS_DEV_CACHE.exists():
        pytest.skip("models.dev cache not found at /tmp/reasonix-models/models_dev_api.json")
    return json.loads(MODELS_DEV_CACHE.read_text())


class TestIsChatModel:
    def test_chat_model(self) -> None:
        assert _is_chat_model("nvidia/nemotron-3-ultra-550b-a55b", {"limit": {"context": 1000000}})

    def test_embedding_excluded(self) -> None:
        assert not _is_chat_model("nvidia/nv-embed-v1", {"limit": {"context": 32768}})

    def test_small_context_excluded(self) -> None:
        assert not _is_chat_model("tiny-model", {"limit": {"context": 1024}})

    def test_non_text_output_excluded(self) -> None:
        """纯图像/视频/音频生成器 (flux/cosmos) 即便名字漏过 skip 也不应入选."""
        assert not _is_chat_model(
            "nvidia/cosmos-predict",
            {"limit": {"context": 1000000}, "modalities": {"output": ["image"]}},
        )
        assert not _is_chat_model(
            "flux-pro",
            {"limit": {"context": 1000000}, "modalities": {"output": ["image", "video"]}},
        )

    def test_text_output_allowed(self) -> None:
        # 显式含 text 的输出模态保留
        assert _is_chat_model(
            "nvidia/llama-3.1-nemotron-70b-instruct",
            {"limit": {"context": 1000000}, "modalities": {"output": ["text"]}},
        )
        # 缺失 modalities 视为聊天模型 (历史条目无该字段)
        assert _is_chat_model("legacy-model", {"limit": {"context": 1000000}})

    def test_tool_call_false_excluded(self) -> None:
        """agent 需要工具调用; 显式 tool_call=False 的非 agent 模型必须剔除."""
        assert not _is_chat_model(
            "nvidia/bge-m3",
            {"limit": {"context": 32768}, "tool_call": False},
        )
        assert not _is_chat_model(
            "nvidia/paligemma",
            {"limit": {"context": 1000000}, "tool_call": False},
        )

    def test_tool_call_true_or_absent_allowed(self) -> None:
        assert _is_chat_model("m", {"limit": {"context": 1000000}, "tool_call": True})
        # 缺省字段视为允许 (历史条目未暴露 tool_call)
        assert _is_chat_model("m", {"limit": {"context": 1000000}})


class TestFieldCoverage:
    """models.dev 提供的每一个字段都必须被归类为 handled 或 ignored, 不允许遗漏.

    只要 opencode/nvidia 任一下游出现一个未归类的 key, 测试即失败——这强制
    任何新增字段都必须在 MODEL_FIELD_HANDLED / MODEL_FIELD_IGNORED (或 provider
    对应集合) 中显式归类, 实现 100% 字段覆盖率审计.
    """

    def test_model_field_coverage(self) -> None:
        md = _load_md_cache()
        known = builder_module.MODEL_FIELD_HANDLED | builder_module.MODEL_FIELD_IGNORED
        for prov in ("opencode", "nvidia"):
            for mid, m in md.get(prov, {}).get("models", {}).items():
                unknown = set(m.keys()) - known
                assert not unknown, f"{prov}/{mid} 含未归类字段: {unknown}"

    def test_provider_field_coverage(self) -> None:
        md = _load_md_cache()
        known = builder_module.PROVIDER_FIELD_HANDLED | builder_module.PROVIDER_FIELD_IGNORED
        for prov in ("opencode", "nvidia"):
            unknown = set(md.get(prov, {}).keys()) - known
            assert not unknown, f"{prov} provider 含未归类字段: {unknown}"

    def test_billing_currency_set(self) -> None:
        providers = build_all()
        for p in providers:
            assert p.billing_currency == "USD", f"{p.name} 缺少 provider 级 USD 币种标注"

    def test_override_maps_limit_and_reasoning(self) -> None:
        """回归: limit/reasoning 字段正确落到 override (不依赖 live 缓存)."""
        m = {
            "limit": {"context": 200000, "output": 128000},
            "reasoning": True,
            "reasoning_options": [{"type": "effort", "values": ["low", "high", "max"]}],
            "modalities": {"input": ["text"]},
            "attachment": False,
        }
        assert _build_override(m) == {
            "context_window": 200000,
            "max_output_tokens": 128000,
            "reasoning_protocol": "openai",
            "supported_efforts": ["low", "high", "max"],
            "default_effort": "max",
        }


class TestFreeZenIds:
    def test_returns_free_ids(self) -> None:
        md_models = _load_md_cache().get("opencode", {}).get("models", {})
        ids = get_free_zen_model_ids(_load_zen_cache(), md_models)
        assert "deepseek-v4-flash-free" in ids  # zen 免费层命名约定
        assert "big-pickle" in ids  # models.dev 标价为 0
        for mid in ids:
            if "-free" in mid:
                continue
            # 非 -free id 必须有元数据且双项零标价: 空洞的 get 兑底会让
            # 未知元数据的 id 空过本循环 (round-2 finding 1).
            assert mid in md_models
            cost = (md_models.get(mid) or {}).get("cost") or {}
            assert not cost.get("input")
            assert not cost.get("output")

    def test_zero_cost_no_suffix_included(self) -> None:
        """big-pickle 无 "-free" 后缀, 仅凭 models.dev 零标价入选 (原硬编码特判已删)."""
        md_models = _load_md_cache().get("opencode", {}).get("models", {})
        ids = get_free_zen_model_ids(_load_zen_cache(), md_models)
        assert "big-pickle" in ids
        cost = (md_models.get("big-pickle") or {}).get("cost") or {}
        assert not cost.get("input")
        assert not cost.get("output")

    def test_excludes_paid(self) -> None:
        md_models = _load_md_cache().get("opencode", {}).get("models", {})
        ids = get_free_zen_model_ids(_load_zen_cache(), md_models)
        assert "gpt-5-nano" not in ids  # models.dev 标价 > 0, 非 -free 命名
        assert "claude-sonnet-4-6" not in ids


class TestFreeZenClassification:
    """合成夹具直接钉死分类契约, 不依赖 live 缓存."""

    def test_unknown_metadata_non_free_excluded(self) -> None:
        # models.dev 未收录的非 -free id 一律排除, 即使 zen 在售:
        # 元数据缺失时无法证明免费.
        zen = {"data": [{"id": "brand-new-paid"}, {"id": "tag-free"}]}
        assert get_free_zen_model_ids(zen, {}) == {"tag-free"}

    def test_zero_cost_included_without_suffix(self) -> None:
        zen = {"data": [{"id": "alpha"}, {"id": "beta"}]}
        md = {
            "alpha": {"cost": {"input": 0, "output": 0}},
            "beta": {"cost": {"input": 1, "output": 2}},
        }
        assert get_free_zen_model_ids(zen, md) == {"alpha"}

    def test_partial_zero_cost_excluded(self) -> None:
        """单项零标价不够: input/output 必须同时为零."""
        zen = {"data": [{"id": "delta"}]}
        md = {"delta": {"cost": {"input": 0, "output": 2}}}
        assert get_free_zen_model_ids(zen, md) == set()

    def test_paid_model_named_like_free_is_excluded(self) -> None:
        """钉死无硬编码: 即使模型名与历史特判对象同名, 有标价即排除."""
        zen = {"data": [{"id": "big-pickle"}]}
        md = {"big-pickle": {"cost": {"input": 5, "output": 5}}}
        assert get_free_zen_model_ids(zen, md) == set()

    def test_missing_cost_fields_treated_free(self) -> None:
        # cost 键/字段缺失按 0 处理, 与 pi-opencode isFreeModel 对齐.
        zen = {"data": [{"id": "gamma"}]}
        md = {"gamma": {"reasoning": True}}
        assert get_free_zen_model_ids(zen, md) == {"gamma"}


class TestProviderConfig:
    def test_to_toml_multi_model(self) -> None:
        cfg = ProviderConfig(
            name="test",
            base_url="https://api.test.com/v1",
            models=["a", "b", "c"],
            default="a",
            api_key_env="TEST_KEY",
            context_window=100000,
        )
        d = cfg.to_toml()
        assert d["name"] == "test"
        assert d["models"] == ["a", "b", "c"]
        assert "model" not in d
        assert d["default"] == "a"

    def test_to_toml_single_model(self) -> None:
        cfg = ProviderConfig(
            name="test",
            base_url="https://api.test.com/v1",
            models=["a"],
            context_window=100000,
        )
        d = cfg.to_toml()
        assert d["model"] == "a"
        assert "models" not in d


class TestRepairDefaultModel:
    def test_valid_bare_model_preserved(self) -> None:
        providers = [ProviderConfig(name="test", base_url="https://x.com", models=["a", "b"])]
        existing = {"default_model": "a"}
        _repair_default_model(existing, providers)
        assert existing["default_model"] == "a"

    def test_valid_provider_name_preserved(self) -> None:
        providers = [ProviderConfig(name="test", base_url="https://x.com", models=["a", "b"])]
        existing = {"default_model": "test"}
        _repair_default_model(existing, providers)
        assert existing["default_model"] == "test"

    def test_valid_provider_model_format_preserved(self) -> None:
        providers = [ProviderConfig(name="test", base_url="https://x.com", models=["a", "b"])]
        existing = {"default_model": "test/b"}
        _repair_default_model(existing, providers)
        assert existing["default_model"] == "test/b"

    def test_invalid_model_repaired(self) -> None:
        providers = [ProviderConfig(name="test", base_url="https://x.com", models=["a", "b"])]
        existing = {"default_model": "nonexistent"}
        _repair_default_model(existing, providers)
        assert existing["default_model"] == "a"

    def test_missing_default_not_touched(self) -> None:
        providers = [ProviderConfig(name="test", base_url="https://x.com", models=["a", "b"])]
        existing: dict = {}
        _repair_default_model(existing, providers)
        assert "default_model" not in existing

    def test_kept_provider_model_preserved(self) -> None:
        """default_model 指向保留的旧 provider 的模型时不能被误判为无效."""
        providers = [ProviderConfig(name="zen", base_url="https://x.com", models=["a", "b"])]
        existing = {
            "default_model": "local/llama",
            "providers": [{"name": "local", "model": "llama"}],
        }
        _repair_default_model(existing, providers)
        assert existing["default_model"] == "local/llama"

    def test_replaced_provider_model_repaired(self) -> None:
        """default_model 指向即将被替换的同名旧 provider 的模型时应重置."""
        providers = [ProviderConfig(name="zen", base_url="https://x.com", models=["a", "b"])]
        existing = {
            "default_model": "zen/stale",
            "providers": [{"name": "zen", "model": "stale"}],
        }
        _repair_default_model(existing, providers)
        assert existing["default_model"] == "a"


class TestTomlSchemaValidity:
    """生成的 TOML 字段必须与 reasonix ProviderEntry / ProviderModelOverride 的
    toml tag 完全一致, 否则字段会被静默忽略.

    白名单来源: reasonix internal/config/config.go (v1.33.0):
      ProviderEntry: name kind base_url chat_url model models models_url default
        api_key_env preset_id preset_version headers extra_body auth_header
        responses_mode responses_stateful balance_url context_window
        max_output_tokens price prices thinking effort vision vision_models
        vision_detail web_search reasoning_protocol supported_efforts
        default_effort model_overrides no_proxy cache_ttl_minutes
      ProviderModelOverride: reasoning_protocol supported_efforts default_effort
        vision context_window max_output_tokens
    """

    PROVIDER_KEYS: ClassVar[set[str]] = {
        "name",
        "kind",
        "base_url",
        "chat_url",
        "model",
        "models",
        "models_url",
        "default",
        "api_key_env",
        "preset_id",
        "preset_version",
        "headers",
        "extra_body",
        "auth_header",
        "responses_mode",
        "responses_stateful",
        "balance_url",
        "context_window",
        "max_output_tokens",
        "price",
        "prices",
        "thinking",
        "effort",
        "vision",
        "vision_models",
        "vision_detail",
        "web_search",
        "reasoning_protocol",
        "supported_efforts",
        "default_effort",
        "model_overrides",
        "no_proxy",
        "cache_ttl_minutes",
        "billing_currency",
    }
    OVERRIDE_KEYS: ClassVar[set[str]] = {
        "reasoning_protocol",
        "supported_efforts",
        "default_effort",
        "vision",
        "context_window",
        "max_output_tokens",
    }

    def test_provider_keys_valid(self) -> None:
        providers = build_all()
        for p in providers:
            d = p.to_toml()
            unknown = set(d) - self.PROVIDER_KEYS
            assert not unknown, f"{p.name} 含无效字段: {unknown}"

    def test_override_keys_valid(self) -> None:
        providers = build_all()
        for p in providers:
            overrides = p.model_overrides or {}
            for mid, ov in overrides.items():
                d = ov.model_dump(exclude_none=True)
                unknown = set(d) - self.OVERRIDE_KEYS
                assert not unknown, f"{p.name}/{mid} 含无效 override 字段: {unknown}"

    def test_override_uses_max_output_tokens_not_max_output(self) -> None:
        """输出预算字段必须是 max_output_tokens (max_output 会被 reasonix 忽略)."""
        providers = build_all()
        for p in providers:
            overrides = p.model_overrides or {}
            for mid, ov in overrides.items():
                d = ov.model_dump(exclude_none=True)
                assert "max_output" not in d, f"{p.name}/{mid} 用了无效字段 max_output"
                assert "thinking" not in d, f"{p.name}/{mid} 用了无效字段 thinking"

    def test_prices_have_usd_currency(self) -> None:
        providers = build_all()
        for p in providers:
            prices = p.prices or {}
            for mid, price in prices.items():
                assert price.currency == "USD", f"{p.name}/{mid} 价格缺少 USD 币种标注"

    def test_build_override_output_shape(self) -> None:
        m = {
            "limit": {"context": 200000, "output": 128000},
            "reasoning": True,
            "reasoning_options": [{"type": "effort", "values": ["low", "high", "max"]}],
            "modalities": {"input": ["text"]},
            "attachment": False,
        }
        assert _build_override(m) == {
            "context_window": 200000,
            "max_output_tokens": 128000,
            "reasoning_protocol": "openai",
            "supported_efforts": ["low", "high", "max"],
            "default_effort": "max",
        }

    def test_build_override_toggle_reasoning(self) -> None:
        """reasoning_options 为 toggle 格式时只声明 reasoning_protocol."""
        m = {
            "limit": {"context": 1000000, "output": 131072},
            "reasoning": True,
            "reasoning_options": [{"type": "toggle"}],
            "modalities": {"input": ["text"]},
            "attachment": False,
        }
        assert _build_override(m) == {
            "context_window": 1000000,
            "max_output_tokens": 131072,
            "reasoning_protocol": "openai",
        }


class TestWireKind:
    """provider.npm → wire 协议映射的合成契约 (不依赖 live 缓存)."""

    def test_responses_package(self) -> None:
        assert _wire_kind({"provider": {"npm": "@ai-sdk/openai"}}) == "responses"

    def test_other_packages_default_to_chat(self) -> None:
        assert _wire_kind({"provider": {"npm": "@ai-sdk/openai-compatible"}}) == "openai"
        assert _wire_kind({"provider": {"npm": "@ai-sdk/anthropic"}}) == "openai"
        assert _wire_kind({"provider": {"npm": "@ai-sdk/google"}}) == "openai"

    def test_missing_metadata_defaults_to_chat(self) -> None:
        # zen 有而 models.dev 未收录: 免费集实测 (big-pickle 等) 均走 chat.
        assert _wire_kind(None) == "openai"
        assert _wire_kind({}) == "openai"


class TestBuildOpencodeSplit:
    """muse-spark-1.2-contributor-free (Responses wire) 必须与 chat 模型拆分."""

    MD: ClassVar[dict[str, object]] = {
        "opencode": {
            "api": "https://opencode.ai/zen/v1",
            "env": ["OPENCODE_API_KEY"],
            "models": {
                "alpha-free": {
                    "limit": {"context": 128000, "output": 8192},
                    "cost": {"input": 0, "output": 0},
                },
                "muse-spark-1.2-contributor-free": {
                    "provider": {"npm": "@ai-sdk/openai"},
                    "limit": {"context": MUSE_SPARK_CONTEXT, "output": MUSE_SPARK_OUTPUT},
                    "cost": {"input": 0, "output": 0},
                    "reasoning": True,
                    "reasoning_options": [
                        {"type": "effort", "values": ["minimal", "low", "medium", "high", "xhigh"]}
                    ],
                    "attachment": True,
                    "modalities": {"input": ["text", "image"]},
                },
            },
        }
    }
    ZEN: ClassVar[dict] = {
        "data": [
            {"id": "alpha-free"},
            {"id": "muse-spark-1.2-contributor-free"},
        ]
    }

    def test_splits_into_two_providers(self) -> None:
        providers = {p.name: p for p in build_opencode(self.MD, self.ZEN)}
        assert set(providers) == {"opencode", "opencode-responses"}
        chat = providers["opencode"]
        resp = providers["opencode-responses"]
        assert chat.kind == "openai"
        assert chat.models == ["alpha-free"]
        assert resp.kind == "responses"
        assert resp.responses_mode == "stateless"
        assert resp.models == ["muse-spark-1.2-contributor-free"]
        # 共享同一网关 / key
        assert resp.base_url == chat.base_url == "https://opencode.ai/zen/v1"
        assert resp.api_key_env == chat.api_key_env == "OPENCODE_API_KEY"

    def test_responses_override_carries_muse_metadata(self) -> None:
        providers = {p.name: p for p in build_opencode(self.MD, self.ZEN)}
        ov = providers["opencode-responses"].model_overrides["muse-spark-1.2-contributor-free"]
        assert ov.model_dump(exclude_none=True) == {
            "context_window": 1048576,
            "max_output_tokens": 131072,
            "reasoning_protocol": "openai",
            "supported_efforts": ["minimal", "low", "medium", "high", "xhigh"],
            "default_effort": "xhigh",
            "vision": True,
        }

    def test_chat_only_zen_keeps_single_provider(self) -> None:
        providers = {p.name: p for p in build_opencode(self.MD, {"data": [{"id": "alpha-free"}]})}
        assert set(providers) == {"opencode"}
        assert providers["opencode"].models == ["alpha-free"]


class TestIntegration:
    def test_build_all_returns_providers(self) -> None:
        providers = build_all()
        assert len(providers) >= EXPECTED_PROVIDER_COUNT
        names = {p.name for p in providers}
        assert "opencode" in names
        assert "nvidia" in names

    def test_build_all_filter_opencode_only(self) -> None:
        providers = build_all(providers_filter=["opencode"])
        assert {p.name for p in providers} == {"opencode", "opencode-responses"}

    def test_build_all_filter_nvidia_only(self) -> None:
        providers = build_all(providers_filter=["nvidia"])
        assert len(providers) == 1
        assert providers[0].name == "nvidia"

    def test_opencode_zen_has_free_models(self) -> None:
        md_data = fetch_models_dev()
        providers = build_opencode(md_data, fetch_zen_models())
        assert len(providers) > 0
        p = providers[0]
        # 字段遵循 models.dev 的 opencode provider 条目.
        assert p.name == "opencode"
        assert p.base_url == "https://opencode.ai/zen/v1"
        assert p.api_key_env == "OPENCODE_API_KEY"
        assert len(p.models) > 0
        md_models = md_data["opencode"]["models"]
        for mid in p.models:
            if "-free" in mid:
                continue
            assert mid in md_models
            cost = (md_models.get(mid) or {}).get("cost") or {}
            assert not cost.get("input")
            assert not cost.get("output")
        # opencode 头部 (User-Agent / x-opencode-*) 由 reasonix 源码检测到该
        # provider 后动态生成, 配置里不再静态写入, 避免与源码重复.
        assert p.headers is None

    def test_muse_spark_responses_provider(self) -> None:
        """zen 在售的 muse-spark-1.2-contributor-free 必须走 Responses wire.

        models.dev provider.npm=@ai-sdk/openai 声明该模型是 Responses 模型,
        chat/completions 端点实测返回 HTTP 500, 只有 /responses 可用. 拆到
        kind=responses 的独立 provider (stateless) 后模型才真正可用.
        """
        md_data = fetch_models_dev()
        zen = fetch_zen_models()
        zen_ids = {m["id"] for m in zen.get("data", [])}
        if "muse-spark-1.2-contributor-free" not in zen_ids:
            pytest.skip("zen 暂未在售 muse-spark-1.2-contributor-free")
        providers = {p.name: p for p in build_opencode(md_data, zen)}
        assert "opencode-responses" in providers
        resp = providers["opencode-responses"]
        assert resp.kind == "responses"
        assert resp.responses_mode == "stateless"
        assert "muse-spark-1.2-contributor-free" in resp.models
        # chat provider 不得再包含 Responses 模型
        assert "muse-spark-1.2-contributor-free" not in providers["opencode"].models
        # 共享同一网关 / key
        assert resp.base_url == providers["opencode"].base_url
        assert resp.api_key_env == "OPENCODE_API_KEY"

    def test_muse_spark_responses_override(self) -> None:
        """muse 的 models.dev 元数据必须完整落到 model_overrides."""
        md_data = fetch_models_dev()
        m = md_data["opencode"]["models"]["muse-spark-1.2-contributor-free"]
        override = _build_override(m)
        assert override["reasoning_protocol"] == "openai"
        assert override["supported_efforts"] == ["minimal", "low", "medium", "high", "xhigh"]
        assert override["default_effort"] == "xhigh"
        assert override["context_window"] == MUSE_SPARK_CONTEXT
        assert override["max_output_tokens"] == MUSE_SPARK_OUTPUT
        assert override["vision"] is True

    def test_nvidia_has_chat_models(self) -> None:
        providers = [build_nvidia(fetch_models_dev())]
        assert len(providers) == 1
        p = providers[0]
        # 字段遵循 models.dev 的 nvidia provider 条目.
        assert p.name == "nvidia"
        assert p.base_url == "https://integrate.api.nvidia.com/v1"
        assert p.api_key_env == "NVIDIA_API_KEY"
        assert len(p.models) > 0

    def test_write_config_requires_existing_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        nonexistent = tmp_path / "nonexistent.toml"
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", nonexistent)
        with pytest.raises(SystemExit, match="does not exist"):
            write_config(
                [ProviderConfig(name="test", base_url="https://x.com", models=["a"])],
            )

    def test_write_config_preserves_valid_default_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('config_version = 5\ndefault_model = "a"\n')
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", cfg_file)
        providers = [ProviderConfig(name="test", base_url="https://x.com", models=["a", "b"])]
        write_config(providers)
        with cfg_file.open("rb") as f:
            data = tomllib.load(f)
        assert data["default_model"] == "a"
        assert data["config_version"] == CONFIG_VERSION

    def test_write_config_repairs_invalid_default_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('config_version = 5\ndefault_model = "old-model"\n')
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", cfg_file)
        providers = [ProviderConfig(name="test", base_url="https://x.com", models=["a", "b"])]
        write_config(providers)
        with cfg_file.open("rb") as f:
            data = tomllib.load(f)
        assert data["default_model"] == "a"

    def test_write_config_preserves_other_providers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            'config_version = 5\n\n[[providers]]\nname = "old-zen"\nbase_url = "x"\n'
            'model = "old"\napi_key_env = "OLD"\ncontext_window = 1000\n'
        )
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", cfg_file)
        providers = [ProviderConfig(name="test", base_url="https://x.com", models=["a", "b"])]
        write_config(providers)
        with cfg_file.open("rb") as f:
            data = tomllib.load(f)
        names = [p["name"] for p in data["providers"]]
        assert "old-zen" in names
        assert "test" in names


class TestEnsureOpencodePublicKey:
    """验证 .env 中 OPENCODE_API_KEY=public 的写入与权限 (.env 含密钥须为 0600)."""

    def test_creates_env_with_0600(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("config_version = 5\n\n")
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", cfg_file)
        assert not (tmp_path / ".env").exists()
        write_config(
            [ProviderConfig(name="test", base_url="https://x.com", models=["a"])],
        )
        env = tmp_path / ".env"
        assert env.exists()
        assert "OPENCODE_API_KEY=public" in env.read_text()
        assert (env.stat().st_mode & 0o777) == ENV_FILE_PERMS

    def test_updates_existing_env_and_tightens_perms(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("config_version = 5\n\n")
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", cfg_file)
        env = tmp_path / ".env"
        env.write_text("OTHER_KEY=secret\n")
        env.chmod(0o644)  # 模拟宽松权限的既有文件
        write_config(
            [ProviderConfig(name="test", base_url="https://x.com", models=["a"])],
        )
        content = env.read_text()
        assert "OPENCODE_API_KEY=public" in content  # 已添加
        assert "OTHER_KEY=secret" in content  # 保留其他凭证
        assert (env.stat().st_mode & 0o777) == ENV_FILE_PERMS  # 权收复紧


class TestEnsureOpencodePublicKeyDedup:
    """验证 .env 中重复的 OPENCODE_API_KEY 行被去重 (历史遗留重复行清理)."""

    def test_dedups_repeated_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("config_version = 5\n\n")
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", cfg_file)
        env = tmp_path / ".env"
        # 模拟历史遗留的重复行 + 其他真实凭证
        env.write_text(
            "OPENCODE_API_KEY=public\n"
            "OTHER_KEY=secret\n"
            "OPENCODE_API_KEY=public\n"
            "OPENCODE_API_KEY=public\n"
        )
        write_config(
            [ProviderConfig(name="test", base_url="https://x.com", models=["a"])],
        )
        content = env.read_text()
        assert content.count("OPENCODE_API_KEY=public") == 1, (
            f"应只剩 1 行, 实际 {content.count('OPENCODE_API_KEY=public')}"
        )
        assert "OTHER_KEY=secret" in content  # 其他凭证保留
        assert (env.stat().st_mode & 0o777) == ENV_FILE_PERMS


class TestEnsureOpencodeKeyPreserved:
    """用户已设置的 OPENCODE_API_KEY 必须原样保留.

    工具只负责在缺失时补 ``public`` (开箱即用); 把用户自己的 key 静默
    覆盖成共享匿名凭据会破坏付费模型认证与独立限流配额.
    """

    def test_existing_user_key_not_overwritten(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("config_version = 5\n\n")
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", cfg_file)
        env = tmp_path / ".env"
        env.write_text("OPENCODE_API_KEY=sk-user-own-key\nOTHER_KEY=secret\n")
        write_config(
            [ProviderConfig(name="test", base_url="https://x.com", models=["a"])],
        )
        content = env.read_text()
        assert "OPENCODE_API_KEY=sk-user-own-key" in content
        assert "OPENCODE_API_KEY=public" not in content
        assert "OTHER_KEY=secret" in content

    def test_dedup_keeps_first_real_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("config_version = 5\n\n")
        monkeypatch.setattr("reasonix_config.builder.REASONIX_CONFIG", cfg_file)
        env = tmp_path / ".env"
        env.write_text("OPENCODE_API_KEY=sk-real-key\nOPENCODE_API_KEY=public\n")
        write_config(
            [ProviderConfig(name="test", base_url="https://x.com", models=["a"])],
        )
        content = env.read_text()
        assert content.count("OPENCODE_API_KEY=") == 1
        assert "OPENCODE_API_KEY=sk-real-key" in content


class TestDeprecatedFilter:
    """models.dev 标记 deprecated 的模型必须被剔除.

    免费推广结束的模型 (如 deepseek-v4-flash-free) 仍会出现在 zen /models
    列表里, 只有 models.dev 的 status 元数据能识别; stale 缓存曾让该过滤
    失效, 这里用纯 mock 数据固定行为.
    """

    @staticmethod
    def _patch_fetch(
        monkeypatch: pytest.MonkeyPatch,
        zen_ids: list[str],
        md_models: dict,
    ) -> None:
        zen = {"object": "list", "data": [{"id": i} for i in zen_ids]}
        md = {
            "opencode": {
                "api": "https://opencode.ai/zen/v1",
                "env": ["OPENCODE_API_KEY"],
                "models": md_models,
            },
            "nvidia": {"models": {}},
        }
        monkeypatch.setattr(builder_module, "fetch_zen_models", lambda: zen)
        monkeypatch.setattr(builder_module, "fetch_models_dev", lambda: md)

    @staticmethod
    def _build_patched(
        monkeypatch: pytest.MonkeyPatch,
        zen_ids: list[str],
        md_models: dict,
    ) -> ProviderConfig:
        TestDeprecatedFilter._patch_fetch(monkeypatch, zen_ids, md_models)
        providers = build_opencode(
            builder_module.fetch_models_dev(), builder_module.fetch_zen_models()
        )
        # 这些夹具全是 chat 模型, 拆分后只有一个 opencode provider
        assert len(providers) == 1
        return providers[0]

    def test_deprecated_model_excluded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = self._build_patched(
            monkeypatch,
            ["alpha-free", "beta-free"],
            {
                "alpha-free": {
                    "status": "deprecated",
                    "limit": {"context": 200000, "output": 32000},
                },
                "beta-free": {"limit": {"context": 200000, "output": 32000}},
            },
        )
        assert p.models == ["beta-free"], "deprecated 模型必须被剔除"

    def test_unknown_model_kept_without_metadata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """zen 有而 models.dev 未收录的模型仍收录 (无元数据优于不可用)."""
        p = self._build_patched(monkeypatch, ["brand-new-free"], {})
        assert p.models == ["brand-new-free"]
        assert p.model_overrides is None

    def test_all_deprecated_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(SystemExit, match="No free OpenCode Zen models"):
            self._build_patched(
                monkeypatch,
                ["gone-free"],
                {"gone-free": {"status": "deprecated", "limit": {"context": 100000}}},
            )
