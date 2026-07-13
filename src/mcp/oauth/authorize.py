from urllib.parse import urlencode

from flask import redirect, request
from flask_login import current_user

from src.mcp.oauth import consent


def _login_redirect():
    target = f"/oauth/authorize?{urlencode(request.args)}"
    return redirect(f"/connexion?next={target}")


def authorize():
    from src.mcp.oauth.routes import _server

    if not current_user.is_authenticated:
        return _login_redirect()

    if not consent.subscription_ok(int(current_user.id)):
        return consent.render_subscription_required(), 403

    if request.method == "GET":
        grant = _server.get_consent_grant(end_user=current_user)
        client = grant.client
        scope = grant.request.scope or "mcp"
        return consent.render_consent(
            client.client_metadata.get("client_name", client.get_client_id()),
            grant.request.redirect_uri or client.get_default_redirect_uri(),
            scope,
        )

    # POST
    if request.form.get("confirm") != "yes":
        return _server.create_authorization_response(grant_user=None)
    return _server.create_authorization_response(grant_user=int(current_user.id))


def token():
    from src.mcp.oauth.routes import _server

    return _server.create_token_response()
