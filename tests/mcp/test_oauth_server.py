from flask import Flask

from src.mcp.oauth import server


def test_create_authorization_server(monkeypatch, tmp_path):
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "u.sqlite"))
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x"
    srv = server.create_authorization_server(app)
    assert srv is not None
