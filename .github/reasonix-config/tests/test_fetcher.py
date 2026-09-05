from __future__ import annotations

import time
from unittest import mock

import httpx
import pytest  # type: ignore[importNotFound]

from reasonix_config.fetcher import (
    CACHE_TTL_SECONDS,
    MODELS_DEV_API,
    MODELS_DEV_USER_AGENT,
    ZEN_API,
    fetch_models_dev,
    fetch_zen_models,
)


def _no_cache(monkeypatch: pytest.MonkeyPatch, cache_attr: str) -> None:
    """把缓存文件 mock 成不存在, 强制走网络路径 (环境里可能有真实 /tmp 缓存)."""
    fake_cache = mock.Mock()
    fake_cache.stat.side_effect = FileNotFoundError(cache_attr)
    monkeypatch.setattr(f"reasonix_config.fetcher.{cache_attr}", fake_cache)


def _fresh_cache(payload: str) -> mock.Mock:
    """存在且 mtime 在 TTL 内的缓存文件 mock."""
    fake_cache = mock.Mock()
    fake_cache.exists.return_value = True
    fake_cache.read_text.return_value = payload
    fake_cache.stat.return_value.st_mtime = time.time()
    return fake_cache


def _stale_cache(payload: str) -> mock.Mock:
    """存在但 mtime 已超过 TTL 的缓存文件 mock."""
    fake_cache = _fresh_cache(payload)
    fake_cache.stat.return_value.st_mtime = time.time() - CACHE_TTL_SECONDS - 1
    return fake_cache


class TestFetchZenModels:
    def test_uses_opencode_user_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """请求应携带与 opencode 一致的 UA (opencode/prod/<version>/cli)."""
        assert MODELS_DEV_USER_AGENT.startswith("opencode/prod/")
        assert MODELS_DEV_USER_AGENT.endswith("/cli")
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
        """命中新鲜缓存(TTL 内)时不发网络请求, 直接返回缓存内容."""
        monkeypatch.setattr("reasonix_config.fetcher.ZEN_CACHE", _fresh_cache('{"cached": true}'))
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            data = fetch_zen_models()
            assert data == {"cached": True}
            mock_get.assert_not_called()

    def test_stale_cache_refetches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """缓存超过 TTL 必须重新拉取: 旧快照会让 deprecated 过滤失效
        (实例: deepseek-v4-flash-free 免费推广结束后 models.dev 才标 deprecated)."""
        monkeypatch.setattr("reasonix_config.fetcher.ZEN_CACHE", _stale_cache('{"stale": true}'))
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            mock_get.return_value = mock.Mock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"object": "list", "data": [{"id": "x-preview-f-free"}]},
            )
            data = fetch_zen_models()
            assert data == {"object": "list", "data": [{"id": "x-preview-f-free"}]}
            mock_get.assert_called_once()

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
        monkeypatch.setattr(
            "reasonix_config.fetcher.MODELS_DEV_CACHE", _fresh_cache('{"cached": 1}')
        )
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            assert fetch_models_dev() == {"cached": 1}
            mock_get.assert_not_called()

    def test_stale_cache_refetches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """models.dev 缓存过期同样必须重拉 (deprecated 状态依赖此数据)."""
        monkeypatch.setattr(
            "reasonix_config.fetcher.MODELS_DEV_CACHE", _stale_cache('{"stale": 1}')
        )
        with mock.patch("reasonix_config.fetcher.httpx.get") as mock_get:
            mock_get.return_value = mock.Mock(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {"fresh": True},
            )
            assert fetch_models_dev() == {"fresh": True}
            mock_get.assert_called_once()

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
