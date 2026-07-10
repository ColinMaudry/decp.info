import os

from flask import Flask, jsonify, request

from src.api import tokens_db
from src.subscriptions.db import has_active_subscription
from src.utils import TOUS_ABONNES


def _unauthorized():
    resp = jsonify(
        {"error": "unauthorized", "message": "Jeton MCP absent ou invalide."}
    )
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Bearer realm="colibre-mcp"'
    return resp


def _forbidden():
    resp = jsonify(
        {
            "error": "no_active_subscription",
            "message": "Un abonnement colibre actif est requis pour le connecteur MCP.",
        }
    )
    resp.status_code = 403
    return resp


def _authenticate_mcp():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return _unauthorized()
    token = header[len("Bearer ") :].strip()
    if not token:
        return _unauthorized()

    db_path = os.environ["USERS_DB_PATH"]
    row = tokens_db.get_token_by_plaintext(db_path, token)
    if row is None or row["revoked_at"] is not None or row["kind"] != "mcp":
        return _unauthorized()

    user_id = row["user_id"]
    if user_id is None:
        return _forbidden()
    if not (TOUS_ABONNES or has_active_subscription(user_id)):
        return _forbidden()

    tokens_db.increment_usage(db_path, row["id"])
    return None


def init_mcp_auth(server: Flask) -> None:
    """Enregistre le garde d'authentification du serveur MCP (/_mcp)."""

    @server.before_request
    def _guard_mcp():
        if request.path == "/_mcp" or request.path.startswith("/_mcp/"):
            return _authenticate_mcp()
        return None
