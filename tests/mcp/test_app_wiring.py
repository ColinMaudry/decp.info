import importlib


def test_mcp_endpoint_guarded_and_csrf_exempt(monkeypatch, tmp_path):
    # DB éphémère + secrets requis par init_auth/init_subscriptions.
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.test.sqlite"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("DASH_MCP_ENABLED", "true")

    from src.auth import db as auth_db

    auth_db.reset_conn_for_tests()

    import src.app as app_module

    app_module = importlib.reload(app_module)
    client = app_module.app.server.test_client()

    # Pas de jeton : le garde renvoie 401 (et NON une erreur CSRF 400/403),
    # ce qui prouve exemption CSRF + garde câblés sur /_mcp.
    resp = client.post("/_mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == 'Bearer realm="colibre-mcp"'

    auth_db.reset_conn_for_tests()
