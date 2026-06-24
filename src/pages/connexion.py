import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

NAME = "Connexion"

register_page(
    __name__,
    path="/connexion",
    title="Connexion | decp.info",
    name=NAME,
    description="Se connecter à decp.info.",
)

ERROR_MESSAGES = {
    "invalid_credentials": "Identifiants invalides.",
    "email_not_verified": "Vérifiez d'abord votre adresse email (consultez votre boîte de réception).",
    "oauth_cancelled": "Connexion LinkedIn annulée.",
    "oauth_failed": "Échec de la connexion via LinkedIn. Réessayez.",
}

INFO_MESSAGES = {
    "pending_verification": (
        "Compte créé. Un email de vérification a été envoyé. "
        "Cliquez sur le lien reçu avant de vous connecter."
    ),
    "verified": "Adresse email vérifiée. Vous pouvez maintenant vous connecter.",
    "password_changed": "Mot de passe mis à jour. Connectez-vous avec le nouveau.",
}


def linkedin_button():
    return html.A(
        "Connexion avec LinkedIn",
        href="/auth/linkedin",
        className="btn w-100 mb-2",
        style={"backgroundColor": "rgb(10, 102, 194)", "color": "white"},
    )


def layout(error: str | None = None, email: str | None = None, **kwargs):
    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    for flag, msg in INFO_MESSAGES.items():
        if kwargs.get(flag) == "1":
            alerts.append(dbc.Alert(msg, color="info"))

    next_url = kwargs.get("next", "")

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "500px"},
        children=[
            html.H2("Connexion"),
            *alerts,
            html.Form(
                method="POST",
                action="/auth/login",
                children=[
                    dcc.Input(
                        type="hidden",
                        id={"type": "csrf-input", "index": "login"},
                        name="csrf_token",
                    ),
                    dcc.Input(type="hidden", name="next", value=next_url),
                    dbc.Label("Adresse email"),
                    dbc.Input(
                        type="email",
                        name="email",
                        required=True,
                        value=email or "",
                        className="mb-3",
                    ),
                    dbc.Label("Mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        className="mb-3",
                    ),
                    dbc.Button("Se connecter", type="submit", color="primary"),
                ],
            ),
            html.Div("ou", className="text-center text-muted my-2"),
            linkedin_button(),
            html.Hr(),
            html.Div(
                [
                    dcc.Link("Créer un compte", href="/inscription"),
                    html.Span(" · "),
                    dcc.Link("Mot de passe oublié ?", href="/mot-de-passe-oublie"),
                ]
            ),
        ],
    )
