from __future__ import annotations

from unittest import mock

import httpx
import pytest

from reasonix_config.fetcher import (
    MODELS_DEV_API,
    MODELS_DEV_USER_AGENT,
    ZEN_API,
    fetch_models_dev,
    fetch_zen_models,
)


def _no_cache(monkeypatch: pytest.MonkeyPatch, cache_attr: str) -> None:
    """把缓存文件 mock 成不存在, 强制走网络路径 (环境里可能有真实 /tmp 缓存)."""
    fake_cache = mock.Mock()
    fake_cache.exists.return_value = False
    monkeypatch.setattr(f"reasonix_config.fetcher.{cache_attr}", fake_cache)


class TestFetchZenModels:
    def test_uses_opencode_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """请求应携带与 opencode 一致的 UA (opencode/prod/<version>/cli)."""
        assert MODELS_DEV_USER_AGENT == "opencode/prod/1.18.14/cli"
        _no_cache(monkeypatch, "ZEN_CACHE")
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            mock_get.return_value = mock.Mock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"object": "list", "data": []},
            )
            fetch_zen_models()
            _, kwargs = mock_get.call_args
            assert kwargs["headers"]["User-Agent"] == MODELS_DEV_USER_AGENT

    def test_uses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """命中缓存时不发网络请求, 直接返回缓存内容."""
        fake_cache = mock.Mock()
        fake_cache.exists.return_value = True
        fake_cache.read_text.return_value = '{"cached": true}'
        monkeypatch.setattr("reasonix_config.fetcher.ZEN_CACHE", fake_cache)
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            data = fetch_zen_models()
            assert data == {"cached": True}
            mock_get.assert_not_called()

    def test_http_error_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """网络错误必须向上抛, 不静默吞掉 (用户要求: 不隐藏错误)."""
        _no_cache(monkeypatch, "ZEN_CACHE")
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "500",
                request=httpx.Request("GET", ZEN_API),
                response=httpx.Response(500, request=httpx.Request("GET", ZEN_API)),
            )
            with pytest.raises(httpx.HTTPStatusError):
                fetch_zen_models()


class TestFetchModelsDev:
    def test_uses_opencode_ua(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_cache(monkeypatch, "MODELS_DEV_CACHE")
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            mock_get.return_value = mock.Mock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"models": {}},
            )
            fetch_models_dev()
            args, kwargs = mock_get.call_args
            assert args[0] == MODELS_DEV_API
            assert kwargs["headers"]["User-Agent"] == MODELS_DEV_USER_AGENT

    def test_uses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_cache = mock.Mock()
        fake_cache.exists.return_value = True
        fake_cache.read_text.return_value = '{"cached": 1}'
        monkeypatch.setattr("reasonix_config.fetcher.MODELS_DEV_CACHE", fake_cache)
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            assert fetch_models_dev() == {"cached": 1}
            mock_get.assert_not_called()

    def test_http_error_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _no_cache(monkeypatch, "MODELS_DEV_CACHE")
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "500",
                request=httpx.Request("GET", MODELS_DEV_API),
                response=httpx.Response(500, request=httpx.Request("GET", MODELS_DEV_API)),
            )
            with pytest.raises(httpx.HTTPStatusError):
                fetch_models_dev()
