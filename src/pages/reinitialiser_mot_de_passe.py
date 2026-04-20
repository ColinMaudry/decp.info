import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html, register_page
from flask_wtf.csrf import generate_csrf

from src.auth.tokens import validate_password_reset_token

NAME = "Réinitialiser le mot de passe"

register_page(
    __name__,
    path="/reinitialiser-mot-de-passe",
    title="Nouveau mot de passe | decp.info",
    name=NAME,
    description="Choisir un nouveau mot de passe.",
)

ERROR_MESSAGES = {
    "invalid_token": "Lien invalide ou expiré. Demandez un nouveau lien de réinitialisation.",
    "password_too_short": "Le mot de passe doit faire au moins 8 caractères.",
    "password_mismatch": "Les mots de passe ne correspondent pas.",
}


def layout(token: str | None = None, error: str | None = None, **_):
    if not token or validate_password_reset_token(token) is None:
        return dbc.Container(
            className="py-4",
            style={"maxWidth": "500px"},
            children=[
                html.H2("Lien invalide"),
                dbc.Alert(ERROR_MESSAGES["invalid_token"], color="danger"),
                dcc.Link("Demander un nouveau lien", href="/mot-de-passe-oublie"),
            ],
        )

    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "500px"},
        children=[
            html.H2("Choisir un nouveau mot de passe"),
            *alerts,
            html.Form(
                method="POST",
                action="/auth/reset-password",
                children=[
                    dcc.Input(type="hidden", id="csrf-reset", name="csrf_token"),
                    dcc.Input(type="hidden", name="token", value=token),
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
                    dbc.Button("Valider", type="submit", color="primary"),
                ],
            ),
        ],
    )


@callback(Output("csrf-reset", "value"), Input("csrf-reset", "id"))
def _fill_csrf(_):
    return generate_csrf()
