import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask_login import current_user

NAME = "Mon compte"

register_page(
    __name__,
    path="/compte",
    title="Mon compte | decp.info",
    name=NAME,
    description="Page de gestion de compte.",
)

ERROR_MESSAGES = {
    "invalid_current_password": "Le mot de passe actuel est incorrect.",
    "password_too_short": "Le nouveau mot de passe doit faire au moins 8 caractères.",
    "password_mismatch": "Les nouveaux mots de passe ne correspondent pas.",
}


def layout(error: str | None = None, password_changed: str | None = None, **_):
    if not current_user.is_authenticated:
        return dcc.Location(href="/connexion?next=/compte", id="compte-redirect")

    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    if password_changed == "1":
        alerts.append(dbc.Alert("Mot de passe mis à jour.", color="success"))

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "600px"},
        children=[
            html.H2("Mon compte"),
            html.P([html.Strong("Email : "), current_user.email]),
            *alerts,
            html.H4("Changer le mot de passe", className="mt-4"),
            html.Form(
                method="POST",
                action="/auth/change-password",
                children=[
                    dcc.Input(
                        type="hidden",
                        id={"type": "csrf-input", "index": "change"},
                        name="csrf_token",
                    ),
                    dbc.Label("Mot de passe actuel"),
                    dbc.Input(
                        type="password",
                        name="current_password",
                        required=True,
                        className="mb-3",
                    ),
                    dbc.Label("Nouveau mot de passe (8 caractères minimum)"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Label("Confirmer le nouveau mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password_confirm",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Button("Changer", type="submit", color="primary"),
                ],
            ),
            html.Hr(className="mt-5"),
            html.Form(
                method="POST",
                action="/auth/logout",
                children=[
                    dcc.Input(
                        type="hidden",
                        id={"type": "csrf-input", "index": "logout"},
                        name="csrf_token",
                    ),
                    dbc.Button("Déconnexion", type="submit", color="secondary"),
                ],
            ),
        ],
    )
