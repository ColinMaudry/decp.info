from flask import Flask, g, jsonify

from src.api import tokens_db
from src.api.auth import require_token


def _make_app():
    app = Flask(__name__)

    @app.route("/protected")
    @require_token
    def protected():
        return jsonify({"token_id": g.token_id})

    return app


def test_missing_header_returns_401(temp_db):
    app = _make_app()
    resp = app.test_client().get("/protected")
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "missing_token"


def test_bearer_without_value_returns_401(temp_db):
    app = _make_app()
    resp = app.test_client().get("/protected", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "missing_token"


def test_invalid_token_returns_401(temp_db):
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": "Bearer colibre_unknown"}
    )
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "invalid_token"


def test_revoked_token_returns_401(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    tokens_db.revoke_token(temp_db, token_id)
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "revoked_token"


def test_valid_token_sets_g_and_calls_view(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["token_id"] == token_id
