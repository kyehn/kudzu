from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from reasonix_config.builder import (
    CONFIG_VERSION,
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
        assert p.headers is not None
        assert "User-Agent" in p.headers
        assert p.headers["User-Agent"].startswith("opencode/")
        assert "X-Opencode-Session" in p.headers
        assert p.headers["X-Opencode-Session"].startswith("ses_")

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
