from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest
import yaml

from dsh_config.builder import (
    _build_override,
    _is_chat_model,
    _selection_still_valid,
    build_all,
    get_free_zen_model_ids,
    get_nvidia_providers,
    get_opencode_zen_free_providers,
    write_config,
)
from dsh_config.fetcher import ZEN_CACHE
from dsh_config.models import ProviderProfile

EXPECTED_PROVIDER_COUNT = 2
CREDENTIALS_FILE_PERMS = 0o600  # 凭据文件含密钥, 仅属主可读写


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
            pytest.skip("zen cache not found at /tmp/dsh-models/opencode_zen_models.json")
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


class TestProviderProfile:
    def test_to_profile_multi_model(self) -> None:
        cfg = ProviderProfile(
            name="test",
            base_url="https://api.test.com/v1",
            models=[_m("a"), _m("b"), _m("c")],
            default="a",
            api_key_env="TEST_KEY",
        )
        d = cfg.to_profile()
        assert d["displayName"] == "test"
        assert d["baseURL"] == "https://api.test.com/v1"
        assert d["apiKeyEnv"] == "TEST_KEY"
        assert d["api"] == "openai-completions"
        assert [m["id"] for m in d["models"]] == ["a", "b", "c"]

    def test_to_profile_single_model(self) -> None:
        cfg = ProviderProfile(
            name="test",
            base_url="https://api.test.com/v1",
            models=[_m("a")],
        )
        d = cfg.to_profile()
        assert len(d["models"]) == 1
        assert d["models"][0]["id"] == "a"


def _m(mid: str) -> ProviderProfile:
    # 占位, 实际用 ModelEntry
    from dsh_config.models import ModelEntry

    return ProviderProfile.model_validate({})


class TestSelectionStillValid:
    def test_valid_preserved(self) -> None:
        providers = [ProviderProfile(name="test", base_url="https://x.com", models=[_entry("a"), _entry("b")])]
        assert _selection_still_valid({"provider": "test", "model": "a"}, providers)

    def test_invalid_model_repaired(self) -> None:
        providers = [ProviderProfile(name="test", base_url="https://x.com", models=[_entry("a"), _entry("b")])]
        assert not _selection_still_valid({"provider": "test", "model": "nonexistent"}, providers)

    def test_unknown_provider_repaired(self) -> None:
        providers = [ProviderProfile(name="test", base_url="https://x.com", models=[_entry("a")])]
        assert not _selection_still_valid({"provider": "other", "model": "a"}, providers)


def _entry(mid: str):
    from dsh_config.models import ModelEntry

    return ModelEntry(id=mid)


class TestYamlSchemaValidity:
    """生成的 settings.yaml 字段必须与 llm-pi-ai 的 profile / modelProfile schema
    完全一致, 否则字段会被静默忽略.

    白名单来源: @deepseek-ai/dsh-llm-pi-ai lib/index.js:
      profile: apiKeyEnv displayName api baseURL models modelOverrides compat
        defaultContextWindow defaultMaxTokens headers reasoning thinkingBudgets
        cacheRetention transport timeoutMs websocketConnectTimeoutMs
        streamIdleTimeoutMs retryPolicy
      modelProfile: id name contextWindow maxTokens reasoningEfforts compat
    """

    PROFILE_KEYS: ClassVar[set[str]] = {
        "apiKeyEnv", "displayName", "api", "baseURL", "models", "modelOverrides",
        "compat", "defaultContextWindow", "defaultMaxTokens", "headers",
        "reasoning", "thinkingBudgets", "cacheRetention", "transport",
        "timeoutMs", "websocketConnectTimeoutMs", "streamIdleTimeoutMs",
        "retryPolicy",
    }
    MODEL_KEYS: ClassVar[set[str]] = {
        "id", "name", "contextWindow", "maxTokens", "reasoningEfforts", "compat",
    }

    def test_provider_keys_valid(self) -> None:
        providers = build_all()
        for p in providers:
            d = p.to_profile()
            unknown = set(d) - self.PROFILE_KEYS
            assert not unknown, f"{p.name} 含无效字段: {unknown}"

    def test_model_keys_valid(self) -> None:
        providers = build_all()
        for p in providers:
            for m in p.models:
                d = m.to_entry()
                unknown = set(d) - self.MODEL_KEYS
                assert not unknown, f"{p.name}/{m.id} 含无效字段: {unknown}"

    def test_models_use_camel_case_entries(self) -> None:
        """llm-pi-ai 的模型条目用 camelCase (contextWindow/maxTokens), 非 snake_case."""
        providers = build_all()
        for p in providers:
            for m in p.models:
                d = m.to_entry()
                assert "context_window" not in d, f"{p.name}/{m.id} 用了无效字段 context_window"
                assert "max_tokens" not in d, f"{p.name}/{m.id} 用了无效字段 max_tokens"

    def test_build_override_output_shape(self) -> None:
        m = {
            "limit": {"context": 200000, "output": 128000},
            "reasoning": True,
            "reasoning_options": [{"type": "effort", "values": ["low", "high", "max"]}],
        }
        assert _build_override(m) == {
            "context_window": 200000,
            "max_tokens": 128000,
            "reasoning_efforts": ["low", "high", "max"],
        }

    def test_build_override_toggle_reasoning(self) -> None:
        """reasoning_options 为 toggle 格式时无 efforts."""
        m = {
            "limit": {"context": 1000000, "output": 131072},
            "reasoning": True,
            "reasoning_options": [{"type": "toggle"}],
        }
        assert _build_override(m) == {
            "context_window": 1000000,
            "max_tokens": 131072,
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
        for m in p.models:
            assert "-free" in m.id or m.id == "big-pickle"
        # opencode 头部 (User-Agent / x-opencode-*) 由 overlays/dsh 的
        # opencode-fetch 在 HTTP 层动态生成, 配置里不再静态写入, 避免重复.
        assert p.headers is None

    def test_nvidia_has_chat_models(self) -> None:
        providers = get_nvidia_providers()
        assert len(providers) == 1
        p = providers[0]
        assert p.api_key_env == "NVIDIA_API_KEY"
        assert len(p.models) > 0


class TestWriteConfig:
    def test_writes_settings_and_credentials(self, tmp_path: Path) -> None:
        providers = [ProviderProfile(name="test", base_url="https://x.com", models=[_entry("a"), _entry("b")])]
        result = write_config(providers, dsh_home=str(tmp_path))
        assert result.settings == tmp_path / "settings.yaml"
        assert result.credentials == tmp_path / ".credentials.yaml"

        settings = yaml.safe_load(result.settings.read_text())
        assert settings["llm-pi-ai"]["providers"]["test"]["baseURL"] == "https://x.com"
        assert settings["agent-default-model"] == {"provider": "test", "model": "a"}

        creds = yaml.safe_load(result.credentials.read_text())
        assert creds == {"OPENCODE_API_KEY": "public"}
        assert (result.credentials.stat().st_mode & 0o777) == CREDENTIALS_FILE_PERMS

    def test_writes_into_dsh_home_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DSH_HOME", str(tmp_path))
        providers = [ProviderProfile(name="test", base_url="https://x.com", models=[_entry("a")])]
        result = write_config(providers)
        assert result.settings == tmp_path / "settings.yaml"

    def test_preserves_valid_default_model(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text(
            yaml.safe_dump({"agent-default-model": {"provider": "test", "model": "b"}})
        )
        providers = [ProviderProfile(name="test", base_url="https://x.com", models=[_entry("a"), _entry("b")])]
        write_config(providers, dsh_home=str(tmp_path))
        settings = yaml.safe_load((tmp_path / "settings.yaml").read_text())
        assert settings["agent-default-model"] == {"provider": "test", "model": "b"}

    def test_repairs_invalid_default_model(self, tmp_path: Path) -> None:
        (tmp_path / "settings.yaml").write_text(
            yaml.safe_dump({"agent-default-model": {"provider": "test", "model": "stale"}})
        )
        providers = [ProviderProfile(name="test", base_url="https://x.com", models=[_entry("a"), _entry("b")])]
        write_config(providers, dsh_home=str(tmp_path))
        settings = yaml.safe_load((tmp_path / "settings.yaml").read_text())
        assert settings["agent-default-model"] == {"provider": "test", "model": "a"}

    def test_credentials_preserve_other_entries_and_tighten_perms(
        self, tmp_path: Path,
    ) -> None:
        creds = tmp_path / ".credentials.yaml"
        creds.write_text(yaml.safe_dump({"OTHER_KEY": "secret"}))
        creds.chmod(0o644)  # 模拟宽松权限的既有文件
        providers = [ProviderProfile(name="test", base_url="https://x.com", models=[_entry("a")])]
        write_config(providers, dsh_home=str(tmp_path))
        content = yaml.safe_load(creds.read_text())
        assert content["OPENCODE_API_KEY"] == "public"  # 已添加
        assert content["OTHER_KEY"] == "secret"  # 保留其他凭据
        assert (creds.stat().st_mode & 0o777) == CREDENTIALS_FILE_PERMS  # 权收复紧
