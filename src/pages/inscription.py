import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

from src.pages.connexion import linkedin_button

NAME = "Inscription"

register_page(
    __name__,
    path="/inscription",
    title="Inscription | colibre",
    name=NAME,
    description="Créer un compte colibre.",
)

ERROR_MESSAGES = {
    "invalid_email": "Adresse email invalide.",
    "password_too_short": "Le mot de passe doit faire au moins 8 caractères.",
    "password_mismatch": "Les mots de passe ne correspondent pas.",
    "email_taken": "Un compte existe déjà avec cet email.",
    "email_send_failed": "Erreur technique lors de l'envoi de l'email. Réessayez plus tard.",
}


def layout(error: str | None = None, email: str | None = None, **_):
    alert = None
    if error and error in ERROR_MESSAGES:
        alert = dbc.Alert(ERROR_MESSAGES[error], color="danger")

    linkedin_next = "/compte/abonnement"

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "500px"},
        children=[
            html.H2("Créer un compte"),
            alert,
            html.Form(
                method="POST",
                action="/auth/signup",
                children=[
                    dcc.Input(
                        type="hidden",
                        id={"type": "csrf-input", "index": "signup"},
                        name="csrf_token",
                    ),
                    dbc.Label("Adresse email"),
                    dbc.Input(
                        type="email",
                        name="email",
                        required=True,
                        value=email or "",
                        className="mb-3",
                    ),
                    dbc.Label("Mot de passe (8 caractères minimum)"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Label("Confirmer le mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password_confirm",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    html.P(
                        "Votre essai gratuit de 3 jours démarre dès la "
                        "validation de votre adresse email. Aucune carte "
                        "bancaire n'est demandée.",
                        className="text-muted small mb-3",
                    ),
                    dbc.Button("Créer le compte", type="submit", color="secondary"),
                ],
            ),
            html.Div("ou", className="text-center text-muted my-2"),
            linkedin_button(linkedin_next),
            html.Hr(),
            dcc.Link("Déjà un compte ? Se connecter", href="/connexion"),
        ],
    )
