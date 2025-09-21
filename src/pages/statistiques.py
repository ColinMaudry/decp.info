from dash import dcc, html, register_page

from src.figures import get_barchart_sources, get_map_count_marches
from src.utils import lf

title = "Statistiques"

register_page(
    __name__, path="/statistiques", title=f"decp.info - {title}", name=title, order=3
)


layout = [
    html.Div(
        className="container",
        children=[
            html.H2(title),
            dcc.Loading(
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                id="loading-statistques",
                type="default",
                children=[
                    html.Div(
                        children=[
                            dcc.Markdown("""
                            La publication de données essentielles de marchés publics (DECP) est souvent effectuée par
                            les plateformes de marchés publics (profils d'acheteurs). Cependant, certaines plateformes ne publient pas,
                            ou publient d'une manière qui rend la récupération des données compliquée. Les données présentées sur ce site
                            ne représentent donc pas tous les marchés attribués en France, seulement une partie significative.

                            L'ajout de nouvelles plateformes [est en cours](https://github.com/ColinMaudry/decp-processing/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22source%20de%20donn%C3%A9es%22),
                            toutes les [contributions](/a-propos#contribuer) sont les bienvenues pour atteindre l'exhaustivité.
                            """),
                            dcc.Graph(figure=get_map_count_marches(lf)),
                            dcc.Graph(
                                figure=get_barchart_sources(lf, "dateNotification")
                            ),
                            dcc.Graph(
                                figure=get_barchart_sources(
                                    lf, "datePublicationDonnees"
                                )
                            ),
                        ],
                    )
                ],
            ),
        ],
    )
]
