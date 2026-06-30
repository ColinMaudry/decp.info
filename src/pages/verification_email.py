import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

NAME = "Vérification email"

register_page(
    __name__,
    path="/verification-email",
    title="Vérification email | colibre",
    name=NAME,
    description="Vérification de l'adresse email.",
)


def layout(error: str | None = None, token: str | None = None, **_):
    if error == "invalid_token":
        return dbc.Container(
            className="py-4",
            style={"maxWidth": "500px"},
            children=[
                html.H2("Lien invalide ou expiré"),
                dbc.Alert(
                    "Le lien de vérification est invalide ou a expiré. "
                    "Connectez-vous pour demander un nouveau lien.",
                    color="danger",
                ),
                dcc.Link("Aller à la connexion", href="/connexion"),
            ],
        )

    return dcc.Location(href="/connexion", id="verif-redirect")
