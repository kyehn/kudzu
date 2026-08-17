from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import ClassVar

import pytest

from reasonix_config.builder import (
    CONFIG_VERSION,
    _build_override,
    _is_chat_model,
    _repair_default_model,
    build_all,
    get_free_zen_model_ids,
    get_nvidia_providers,
    get_opencode_zen_free_providers,
    write_config,
)
from reasonix_config.fetcher import ZEN_CACHE
from reasonix_config.models import ProviderConfig

EXPECTED_PROVIDER_COUNT = 2
ENV_FILE_PERMS = 0o600  # .env 含密钥, 仅属主可读写


def _load_zen_cache() -> dict | None:
    if not ZEN_CACHE.exists():
        return None
    return json.loads(ZEN_CACHE.read_text())


class TestIsChatModel:
    def test_chat_model(self) -> None:
        assert _is_chat_model("nvidia/nemotron-3-ultra-550b-a55b", {"limit": {"context": 1000000}})

    def test_embedding_excluded(self) -> None:
        assert not _is_chat_model("nvidia/nv-embed-v1", {"limit": {"context": 32768}})

    def test_small_context_excluded(self) -> None:
        assert not _is_chat_model("tiny-model", {"limit": {"context": 1024}})


class TestFreeZenIds:
    def test_returns_free_ids(self) -> None:
        zen = _load_zen_cache()
        if zen is None:
            pytest.skip("zen cache not found at /tmp/reasonix-models/opencode_zen_models.json")
        ids = get_free_zen_model_ids(zen)
        assert "deepseek-v4-flash-free" in ids
        assert "big-pickle" in ids
        for mid in ids:
            assert "-free" in mid or mid == "big-pickle"

    def test_excludes_paid(self) -> None:
        zen = _load_zen_cache()
        if zen is None:
            pytest.skip("zen cache not found")
        ids = get_free_zen_model_ids(zen)
        assert "gpt-4o" not in ids
        assert "claude-sonnet-4-6" not in ids


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

    白名单来源: reasonix internal/config/config.go (v1.21.2):
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


class TestIntegration:
    def test_build_all_returns_providers(self) -> None:
        providers = build_all()
        assert len(providers) >= EXPECTED_PROVIDER_COUNT
        names = {p.name for p in providers}
        assert "opencode-zen" in names
        assert "nvidia-nim" in names

    def test_build_all_filter_opencode_only(self) -> None:
        providers = build_all(providers_filter=["opencode-zen"])
        assert len(providers) == 1
        assert providers[0].name == "opencode-zen"

    def test_build_all_filter_nvidia_only(self) -> None:
        providers = build_all(providers_filter=["nvidia-nim"])
        assert len(providers) == 1
        assert providers[0].name == "nvidia-nim"

    def test_opencode_zen_has_free_models(self) -> None:
        providers = get_opencode_zen_free_providers()
        assert len(providers) == 1
        p = providers[0]
        assert p.api_key_env == "OPENCODE_API_KEY"
        assert len(p.models) > 0
        for mid in p.models:
            assert "-free" in mid or mid == "big-pickle"
        # opencode 头部 (User-Agent / x-opencode-*) 由 reasonix 源码检测
        # opencode-zen 后动态生成, 配置里不再静态写入, 避免与源码重复.
        assert p.headers is None

    def test_nvidia_has_chat_models(self) -> None:
        providers = get_nvidia_providers()
        assert len(providers) == 1
        p = providers[0]
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
