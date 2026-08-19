from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from dsh_config import fetcher
from dsh_config.fetcher import (
    MODELS_DEV_API,
    MODELS_DEV_USER_AGENT,
    ZEN_API,
    fetch_zen_models,
)


class TestFetchCaches:
    def test_zen_cache_hit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = tmp_path / "zen.json"
        cache.write_text('{"data": [{"id": "gpt-4o"}]}')
        monkeypatch.setattr(fetcher, "ZEN_CACHE", cache)

        def _get(*args: object, **kwargs: object) -> None:
            msg = "network must not be touched on cache hit"
            raise AssertionError(msg)

        monkeypatch.setattr(fetcher.httpx, "get", _get)
        assert fetcher.fetch_zen_models() == {"data": [{"id": "gpt-4o"}]}

    def test_zen_fetch_populates_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache = tmp_path / "zen.json"
        monkeypatch.setattr(fetcher, "ZEN_CACHE", cache)

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"data": [{"id": "deepseek-v4-flash-free"}]}

        def _get(url: str, timeout: float, headers: dict) -> FakeResponse:
            assert url == ZEN_API
            assert isinstance(timeout, int)
            assert headers == {"User-Agent": MODELS_DEV_USER_AGENT}
            return FakeResponse()

        monkeypatch.setattr(fetcher.httpx, "get", _get)
        fetch_zen_models()
        assert cache.read_text() != ""

    def test_models_dev_cache_hit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cache = tmp_path / "models.json"
        cache.write_text('{"nvidia": {"models": {}}}')
        monkeypatch.setattr(fetcher, "MODELS_DEV_CACHE", cache)

        def _get(*args: object, **kwargs: object) -> None:
            msg = "network must not be touched on cache hit"
            raise AssertionError(msg)

        monkeypatch.setattr(fetcher.httpx, "get", _get)
        assert fetcher.fetch_models_dev() == {"nvidia": {"models": {}}}

    def test_http_error_propagates(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fetcher, "MODELS_DEV_CACHE", tmp_path / "missing.json")

        def _get(url: str, **kwargs: object) -> httpx.Response:
            assert url == MODELS_DEV_API
            return httpx.Response(500, request=httpx.Request("GET", url))

        monkeypatch.setattr(fetcher.httpx, "get", _get)
        with pytest.raises(httpx.HTTPStatusError):
            fetcher.fetch_models_dev()
