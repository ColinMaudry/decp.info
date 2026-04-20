import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html, register_page
from flask_wtf.csrf import generate_csrf

NAME = "Mot de passe oublié"

register_page(
    __name__,
    path="/mot-de-passe-oublie",
    title="Mot de passe oublié | decp.info",
    name=NAME,
    description="Réinitialiser votre mot de passe decp.info.",
)

ERROR_MESSAGES = {
    "email_send_failed": "Erreur technique lors de l'envoi de l'email. Réessayez plus tard.",
}


def layout(
    error: str | None = None, pending: str | None = None, email: str | None = None, **_
):
    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    if pending == "1":
        alerts.append(
            dbc.Alert(
                "Si un compte existe avec cet email, un lien de réinitialisation vient d'être envoyé. "
                "Vérifiez votre boîte de réception.",
                color="info",
            )
        )

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "500px"},
        children=[
            html.H2("Mot de passe oublié"),
            *alerts,
            html.P(
                "Saisissez votre adresse email. Si un compte existe, "
                "vous recevrez un lien pour choisir un nouveau mot de passe."
            ),
            html.Form(
                method="POST",
                action="/auth/request-password-reset",
                children=[
                    dcc.Input(type="hidden", id="csrf-forgot", name="csrf_token"),
                    dbc.Label("Adresse email"),
                    dbc.Input(
                        type="email",
                        name="email",
                        required=True,
                        value=email or "",
                        className="mb-3",
                    ),
                    dbc.Button("Envoyer le lien", type="submit", color="primary"),
                ],
            ),
            html.Hr(),
            dcc.Link("Retour à la connexion", href="/connexion"),
        ],
    )


@callback(Output("csrf-forgot", "value"), Input("csrf-forgot", "id"))
def _fill_csrf(_):
    return generate_csrf()
