from dash import dcc, html, register_page

from src.utils import departements

name = "Départements"

register_page(
    __name__,
    path="/departements",
    title="Marchés par département | decp.info",
    name="Départements",
    description="Tous les marchés publics, classés par départements",
)

layout = html.Div(
    [
        html.P(dcc.Link(d["departement"], href=f"/departements/{k}"))
        for k, d in departements.items()
    ]
)
