import importlib
import sys


def test_mcp_endpoint_guarded_and_csrf_exempt(monkeypatch, tmp_path):
    # DB éphémère + secrets requis par init_auth/init_subscriptions.
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.test.sqlite"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("DASH_MCP_ENABLED", "true")

    from src.auth import db as auth_db

    auth_db.reset_conn_for_tests()

    # Recharger src.app avec le flag activé ré-exécute la découverte use_pages,
    # qui REMPLACE les objets-modules src.pages.* dans sys.modules (Dash les
    # ré-exécute via exec_module). Sans restauration, un test ultérieur ayant
    # importé une fonction de page (ex. tests/test_grid.py: get_rows_tableau)
    # verrait son patch("src.pages.tableau.<x>") cibler un objet-module différent
    # de celui d'où provient la fonction importée → pollution inter-tests. On
    # snapshot les modules concernés puis on les restaure en fin de test.
    snapshot = {
        name: mod
        for name, mod in sys.modules.items()
        if name == "src.app" or name.startswith("src.pages")
    }
    try:
        import src.app as app_module

        app_module = importlib.reload(app_module)
        client = app_module.app.server.test_client()

        # Pas de jeton : le garde renvoie 401 (et NON une erreur CSRF 400/403),
        # ce qui prouve exemption CSRF + garde câblés sur /_mcp.
        resp = client.post("/_mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
        assert resp.status_code == 401
        assert resp.headers.get("WWW-Authenticate", "").startswith(
            'Bearer realm="colibre-mcp"'
        )
    finally:
        # Restaurer les objets-modules d'origine et purger ceux créés par le
        # reload, pour ne pas polluer les tests suivants.
        for name in [
            n for n in sys.modules if n == "src.app" or n.startswith("src.pages")
        ]:
            if name in snapshot:
                sys.modules[name] = snapshot[name]
            else:
                del sys.modules[name]
        auth_db.reset_conn_for_tests()


def test_oauth_wellknown_served_when_mcp_enabled(monkeypatch, tmp_path):
    # DB éphémère + secrets requis par init_auth/init_subscriptions.
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.test.sqlite"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    monkeypatch.setenv("DASH_MCP_ENABLED", "true")

    from src.auth import db as auth_db

    auth_db.reset_conn_for_tests()

    # Voir commentaire ci-dessus : reload de src.app pollue sys.modules pour
    # src.pages.* ; on snapshot/restaure de la même façon.
    snapshot = {
        name: mod
        for name, mod in sys.modules.items()
        if name == "src.app" or name.startswith("src.pages")
    }
    try:
        import src.app as app_module

        app_module = importlib.reload(app_module)
        client = app_module.app.server.test_client()

        resp = client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 200
        assert resp.get_json()["resource"] == "https://colibre.fr/_mcp"
    finally:
        for name in [
            n for n in sys.modules if n == "src.app" or n.startswith("src.pages")
        ]:
            if name in snapshot:
                sys.modules[name] = snapshot[name]
            else:
                del sys.modules[name]
        auth_db.reset_conn_for_tests()
