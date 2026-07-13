import os

from flask import Blueprint, jsonify

from src.mcp.oauth import metadata, server

oauth_bp = Blueprint("mcp_oauth", __name__)

_server = None  # AuthorizationServer, initialisé par init_oauth


def _base() -> str:
    return os.getenv("APP_BASE_URL", "").rstrip("/")


@oauth_bp.route("/.well-known/oauth-protected-resource")
@oauth_bp.route("/.well-known/oauth-protected-resource/_mcp")
def protected_resource():
    return jsonify(metadata.protected_resource_metadata(_base()))


@oauth_bp.route("/.well-known/oauth-authorization-server")
@oauth_bp.route("/.well-known/oauth-authorization-server/_mcp")
@oauth_bp.route("/.well-known/openid-configuration")
def as_metadata():
    return jsonify(metadata.authorization_server_metadata(_base()))


@oauth_bp.route("/oauth/register", methods=["POST"])
def register():
    return _server.create_endpoint_response("client_registration")


@oauth_bp.route("/oauth/revoke", methods=["POST"])
def revoke():
    return _server.create_endpoint_response("revocation")


def init_oauth(app) -> None:
    global _server
    _server = server.create_authorization_server(app)

    from src.mcp.oauth.authorize import authorize as _authorize  # Task 9
    from src.mcp.oauth.authorize import token as _token  # Task 9

    app.add_url_rule(
        "/oauth/authorize", "oauth_authorize", _authorize, methods=["GET", "POST"]
    )
    app.add_url_rule("/oauth/token", "oauth_token", _token, methods=["POST"])
    app.register_blueprint(oauth_bp)
