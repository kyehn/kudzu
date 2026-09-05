from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, Self

import httpx
import pytest

from reasonix_config import fetcher as fetcher_module


def _fake_get_factory(payload: object, record: dict, exc: Exception | None = None):
    def fake_get(url: str, timeout: float, headers: dict) -> object:
        record["url"] = url
        record["headers"] = headers
        if exc is not None:
            raise exc

        class Resp:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> object:
                return payload

        return Resp()

    return fake_get


class TestFetchModelsDev:
    def test_uses_opencode_ua(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        record: dict = {}
        monkeypatch.setattr(fetcher_module.httpx, "get", _fake_get_factory({"a": 1}, record))
        monkeypatch.setattr(fetcher_module, "MODELS_DEV_CACHE", tmp_path / "md.json")
        assert fetcher_module.fetch_models_dev() == {"a": 1}
        assert record["headers"]["User-Agent"].startswith("opencode/")

    def test_uses_cache(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cache = tmp_path / "md.json"
        cache.write_text(json.dumps({"cached": True}))
        monkeypatch.setattr(fetcher_module, "MODELS_DEV_CACHE", cache)
        # 缓存新鲜时不触网 (httpx.get 被换成必炸函数)
        monkeypatch.setattr(
            fetcher_module.httpx,
            "get",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("net")),
        )
        assert fetcher_module.fetch_models_dev() == {"cached": True}

    def test_http_error_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(fetcher_module, "MODELS_DEV_CACHE", tmp_path / "md.json")
        monkeypatch.setattr(
            fetcher_module.httpx,
            "get",
            _fake_get_factory({}, {}, httpx.ConnectError("down")),
        )
        with pytest.raises(httpx.HTTPError):
            fetcher_module.fetch_models_dev()


class TestFetchOfficialModels:
    """官方名单 URL 必须由 provider 条目 api 派生 (零硬编码证明)."""

    ENTRY: ClassVar[dict] = {
        "id": "opencode",
        "name": "Fake",
        "npm": "@fake/compat",
        "api": "https://fake.example/v9",
        "env": ["FAKE_KEY"],
        "models": {},
    }

    def test_url_derived_from_entry(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        record: dict = {}
        monkeypatch.setattr(fetcher_module.httpx, "get", _fake_get_factory({"data": []}, record))
        monkeypatch.setattr(
            fetcher_module, "OFFICIAL_LIST_CACHE", tmp_path / "official_{pid}_models.json"
        )
        out = fetcher_module.fetch_official_models(dict(self.ENTRY), "opencode")
        assert out == {"data": []}
        assert record["url"] == "https://fake.example/v9/models"
        assert "Authorization" not in record["headers"]

    def test_api_key_sent_when_given(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        record: dict = {}
        monkeypatch.setattr(fetcher_module.httpx, "get", _fake_get_factory({"data": []}, record))
        monkeypatch.setattr(
            fetcher_module, "OFFICIAL_LIST_CACHE", tmp_path / "official_{pid}_models.json"
        )
        fetcher_module.fetch_official_models(dict(self.ENTRY), "opencode", "secret")
        assert record["headers"]["Authorization"] == "Bearer secret"

    def test_bad_shape_fail_closed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(fetcher_module.httpx, "get", _fake_get_factory({"items": []}, {}))
        monkeypatch.setattr(
            fetcher_module, "OFFICIAL_LIST_CACHE", tmp_path / "official_{pid}_models.json"
        )
        with pytest.raises(SystemExit, match="unexpected shape"):
            fetcher_module.fetch_official_models(dict(self.ENTRY), "opencode")

    def test_http_error_fail_closed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(
            fetcher_module.httpx,
            "get",
            _fake_get_factory({}, {}, httpx.ConnectError("down")),
        )
        monkeypatch.setattr(
            fetcher_module, "OFFICIAL_LIST_CACHE", tmp_path / "official_{pid}_models.json"
        )
        with pytest.raises(SystemExit, match="official model list unavailable"):
            fetcher_module.fetch_official_models(dict(self.ENTRY), "opencode")

    def test_missing_api_fail_closed(self) -> None:
        with pytest.raises(SystemExit, match="no usable 'api'"):
            fetcher_module.fetch_official_models({"id": "x"}, "x")

    def test_cache_file_keyed_by_pid(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        # 不同 pid 落不同缓存文件 (entry.get("id") 恒 unknown 的旧 bug 会撞车)
        monkeypatch.setattr(fetcher_module.httpx, "get", _fake_get_factory({"data": []}, {}))
        monkeypatch.setattr(
            fetcher_module, "OFFICIAL_LIST_CACHE", tmp_path / "official_{pid}_models.json"
        )
        entry = dict(self.ENTRY)
        fetcher_module.fetch_official_models(entry, "aaa")
        fetcher_module.fetch_official_models(entry, "bbb")
        assert (tmp_path / "official_aaa_models.json").exists()
        assert (tmp_path / "official_bbb_models.json").exists()

    def test_no_cache_read_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # use_cache=False 时即使有新鲜缓存也实时拉取
        cache = tmp_path / "official_opencode_models.json"
        cache.write_text(json.dumps({"data": [{"id": "stale"}]}))
        record: dict = {}
        monkeypatch.setattr(fetcher_module.httpx, "get", _fake_get_factory({"data": []}, record))
        monkeypatch.setattr(
            fetcher_module, "OFFICIAL_LIST_CACHE", tmp_path / "official_{pid}_models.json"
        )
        out = fetcher_module.fetch_official_models(dict(self.ENTRY), "opencode", use_cache=False)
        assert out == {"data": []}
        assert record["url"] == "https://fake.example/v9/models"


class TestProbeNvidiaLive:
    def test_only_404_marks_dead(self, monkeypatch: pytest.MonkeyPatch) -> None:
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

            def post(self, url: str, headers: dict[str, str], json: dict) -> FakeResp:
                assert url == "https://fake.example/v9/chat/completions"
                return FakeResp(404 if json["model"] == "gone" else 200)

        monkeypatch.setattr(fetcher_module.httpx, "Client", FakeClient)
        dead = fetcher_module.probe_nvidia_live(["gone", "ok"], "k", "https://fake.example/v9")
        assert dead == {"gone"}
