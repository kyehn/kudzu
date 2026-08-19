from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from dsh_config import builder
from dsh_config.builder import (
    DEFAULT_MODEL,
    HOME_PATCH_TEMPLATE,
    NVIDIA_NIM_PROVIDER,
    OPENCODE_ZEN_PROVIDER,
    _is_chat_model,
    available_models,
    ensure_home_patch,
    ensure_opencode_public_key,
    get_free_zen_model_ids,
    read_current_default_model,
    resolve_default_model,
)

CREDENTIALS_FILE_PERMS = 0o600

ZEN_FIXTURE = {
    "data": [
        {"id": "deepseek-v4-flash-free"},
        {"id": "deepseek-v4-pro"},
        {"id": "big-pickle"},
    ]
}

MODELS_DEV_FIXTURE = {
    "opencode": {
        "models": {
            "deepseek-v4-flash-free": {"limit": {"context": 1000000, "output": 256000}},
            "big-pickle": {"status": "deprecated", "limit": {"context": 1000000}},
        }
    },
    "nvidia": {
        "models": {
            "nvidia/deepseek-v4-flash": {"limit": {"context": 1000000, "output": 256000}},
            "nvidia/nv-embed-v1": {"limit": {"context": 32768}},
            "nvidia/tiny-chat": {"limit": {"context": 1024}},
        }
    },
}


def use_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builder, "fetch_zen_models", lambda: ZEN_FIXTURE)
    monkeypatch.setattr(builder, "fetch_models_dev", lambda: MODELS_DEV_FIXTURE)


def use_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[[], Path]:
    monkeypatch.setattr(builder, "dsh_home", lambda: tmp_path)
    return lambda: tmp_path


class TestIsChatModel:
    def test_chat_model(self) -> None:
        assert _is_chat_model("nvidia/nemotron-3-ultra-550b-a55b", {"limit": {"context": 1000000}})

    def test_embedding_excluded(self) -> None:
        assert not _is_chat_model("nvidia/nv-embed-v1", {"limit": {"context": 32768}})

    def test_small_context_excluded(self) -> None:
        assert not _is_chat_model("tiny-model", {"limit": {"context": 1024}})


class TestFreeZenIds:
    def test_returns_free_ids(self) -> None:
        ids = get_free_zen_model_ids(ZEN_FIXTURE)
        assert "deepseek-v4-flash-free" in ids
        assert "big-pickle" in ids
        for mid in ids:
            assert "-free" in mid or mid == "big-pickle"

    def test_excludes_paid(self) -> None:
        ids = get_free_zen_model_ids(ZEN_FIXTURE)
        assert "deepseek-v4-pro" not in ids


class TestAvailableModels:
    def test_deprecated_filtered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        use_fixtures(monkeypatch)
        zen = available_models()[OPENCODE_ZEN_PROVIDER]
        assert zen == ["deepseek-v4-flash-free"]

    def test_nvidia_chat_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        use_fixtures(monkeypatch)
        nvidia = available_models()[NVIDIA_NIM_PROVIDER]
        assert nvidia == ["nvidia/deepseek-v4-flash"]

    def test_empty_zen_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(builder, "fetch_zen_models", lambda: {"data": [{"id": "gpt-4o"}]})
        monkeypatch.setattr(
            builder,
            "fetch_models_dev",
            lambda: {"opencode": {"models": {}}, "nvidia": {"models": {}}},
        )
        with pytest.raises(SystemExit):
            available_models()


class TestDefaultModel:
    def test_keeps_valid(self) -> None:
        zen = ["deepseek-v4-flash-free", "big-pickle"]
        assert resolve_default_model(zen, "big-pickle") == "big-pickle"

    def test_prefers_flash_free(self) -> None:
        zen = ["deepseek-v4-flash-free", "big-pickle"]
        assert resolve_default_model(zen, "claude-sonnet-4-6") == DEFAULT_MODEL

    def test_falls_back_to_first(self) -> None:
        assert resolve_default_model(["big-pickle"], "claude-sonnet-4-6") == "big-pickle"


class TestHomePatch:
    def test_writes_template_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_home(monkeypatch, tmp_path)
        patch = ensure_home_patch(["deepseek-v4-flash-free"], None)
        content = patch.read_text()
        assert f"    model: {DEFAULT_MODEL}" in content
        assert "provider: opencode-zen" in content
        assert "mode: danger-full-access" in content
        assert "policy: never" in content

    def test_refreshes_model_line_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_home(monkeypatch, tmp_path)
        patch = tmp_path / "cordis.patch.yml"
        patch.write_text(HOME_PATCH_TEMPLATE.format(model="stale-model") + "\n- id: user-thing\n")
        ensure_home_patch(["deepseek-v4-flash-free"], "stale-model")
        content = patch.read_text()
        assert f"model: {DEFAULT_MODEL}" in content
        assert "stale-model" not in content
        assert "- id: user-thing" in content  # 用户行保留

    def test_appends_section_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_home(monkeypatch, tmp_path)
        patch = tmp_path / "cordis.patch.yml"
        patch.write_text("- id: user-thing\n")
        ensure_home_patch(["deepseek-v4-flash-free"], None)
        content = patch.read_text()
        assert "- id: agent-default-model" in content
        assert f"model: {DEFAULT_MODEL}" in content

    def test_read_current_default_model_present_and_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_home(monkeypatch, tmp_path)
        patch = tmp_path / "cordis.patch.yml"
        patch.write_text(
            "- id: agent-default-model\n"
            "  config:\n"
            "    provider: opencode-zen\n"
            "    model: my-model\n"
        )
        assert read_current_default_model() == "my-model"

        monkeypatch.setattr(builder, "dsh_home", lambda: tmp_path / "missing")
        assert read_current_default_model() is None


class TestCredentials:
    def test_ensures_public_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        use_home(monkeypatch, tmp_path)
        ensure_opencode_public_key()
        creds = yaml.safe_load((tmp_path / ".credentials.yaml").read_text())
        assert creds == {"OPENCODE_API_KEY": "public"}
        assert (tmp_path / ".credentials.yaml").stat().st_mode & 0o777 == CREDENTIALS_FILE_PERMS

    def test_preserves_existing_credentials(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_home(monkeypatch, tmp_path)
        (tmp_path / ".credentials.yaml").write_text(yaml.safe_dump({"NVIDIA_API_KEY": "abc"}))
        ensure_opencode_public_key()
        creds = yaml.safe_load((tmp_path / ".credentials.yaml").read_text())
        assert creds == {"NVIDIA_API_KEY": "abc", "OPENCODE_API_KEY": "public"}
