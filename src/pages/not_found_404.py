"""Page affichée quand aucune page ne correspond au chemin demandé.

Dash repère cette page par son **nom de module** (`not_found_404`), pas par son
`path` : voir `dash/dash.py:2654`. Sans elle, le routeur retombe sur
`html.H1("404 - Page not found")`, en anglais et sans mise en forme.

Elle ne couvre que la navigation interne de la SPA, qui ne repasse pas par le
serveur. Les entrées directes (crawlers, liens externes, anciennes URL de
decp.info) sont interceptées en amont par `src.not_found`, qui répond
`src/assets/404.html` avec un vrai statut 404.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

register_page(
    __name__,
    path="/404",
    title="Page introuvable | colibre",
    name="Page introuvable",
    description="Cette adresse ne correspond à aucune page de colibre.",
)


layout = dbc.Row(
    dbc.Col(
        [
            html.H2("Page introuvable"),
            html.P(
                "Cette adresse ne correspond à aucune page de colibre. Elle a "
                "peut-être été supprimée, ou provient d'un lien devenu obsolète."
            ),
            html.P(
                [
                    dcc.Link("Rechercher un acheteur", href="/"),
                    html.Span(" · "),
                    dcc.Link("Explorer les marchés", href="/tableau"),
                ]
            ),
        ],
        md=8,
        lg=6,
    ),
    justify="center",
    className="mt-5 text-center",
)
