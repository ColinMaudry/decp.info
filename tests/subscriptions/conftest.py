import json as _json

import pytest


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    @property
    def text(self):
        return _json.dumps(self._payload)


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()


@pytest.fixture
def fake_httpx(monkeypatch):
    """Capture les appels httpx.request du client Frisbii et renvoie des réponses programmées."""
    from src.subscriptions import client

    calls = []
    queue = []

    def _fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        if queue:
            return queue.pop(0)
        return FakeResponse(200, {})

    monkeypatch.setenv("FRISBII_API_KEY", "priv_test")
    monkeypatch.setenv("FRISBII_API_BASE_URL", "https://api.test")
    monkeypatch.setattr(client.httpx, "request", _fake_request)
    return {"calls": calls, "queue": queue, "Response": FakeResponse}
