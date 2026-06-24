import json

import httpx
import pytest

from src.utils import data as data_mod

VALID = {"fields": [{"name": "uid", "title": "UID"}, {"name": "objet"}]}


class FakeResp:
    def __init__(self, payload, ok=True, bad_json=False):
        self._payload = payload
        self._ok = ok
        self._bad_json = bad_json

    def raise_for_status(self):
        if not self._ok:
            raise httpx.HTTPError("boom")
        return self

    def json(self):
        if self._bad_json:
            raise json.JSONDecodeError("bad", "", 0)
        return self._payload


def test_remote_ok_returns_schema_and_writes_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.cache.json"
    monkeypatch.setenv("DATA_SCHEMA_PATH", "http://x")
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    monkeypatch.setattr(data_mod, "get", lambda *a, **k: FakeResp(VALID))
    result = data_mod.get_data_schema()
    assert "uid" in result
    assert json.loads(cache.read_text())["fields"][0]["name"] == "uid"


def test_remote_http_error_falls_back_to_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.cache.json"
    cache.write_text(json.dumps(VALID))
    monkeypatch.setenv("DATA_SCHEMA_PATH", "http://x")
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    monkeypatch.setattr(data_mod, "get", lambda *a, **k: FakeResp(None, ok=False))
    assert "uid" in data_mod.get_data_schema()


def test_remote_malformed_falls_back_to_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.cache.json"
    cache.write_text(json.dumps(VALID))
    monkeypatch.setenv("DATA_SCHEMA_PATH", "http://x")
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    monkeypatch.setattr(data_mod, "get", lambda *a, **k: FakeResp({"nope": 1}))
    assert "uid" in data_mod.get_data_schema()


def test_no_url_uses_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.cache.json"
    cache.write_text(json.dumps(VALID))
    monkeypatch.delenv("DATA_SCHEMA_PATH", raising=False)
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    assert "uid" in data_mod.get_data_schema()


def test_no_source_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_SCHEMA_PATH", raising=False)
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(tmp_path / "missing.json"))
    with pytest.raises(RuntimeError):
        data_mod.get_data_schema()


def test_cache_write_failure_is_non_blocking(tmp_path, monkeypatch):
    # parent inexistant => l'écriture du cache échoue, mais le schéma est renvoyé
    cache = tmp_path / "nodir" / "schema.cache.json"
    monkeypatch.setenv("DATA_SCHEMA_PATH", "http://x")
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    monkeypatch.setattr(data_mod, "get", lambda *a, **k: FakeResp(VALID))
    assert "uid" in data_mod.get_data_schema()
