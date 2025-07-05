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
            dcc.Markdown("""
            À savoir, les données suivantes existent mais sont en cours d'intégration dans ce projet :

            - les données publiées dans le [format DECP 2019 (période 2018-2022)](https://www.data.gouv.fr/fr/datasets/donnees-essentielles-de-la-commande-publique-fichiers-consolides/#/resources/16962018-5c31-4296-9454-5998585496d2)
            - les données [collectées par l'AIFE](https://github.com/ColinMaudry/decp-processing/issues/68) (API DUME, notamment achatpublic.info)
            - les données [des plateformes Atexo](https://github.com/ColinMaudry/decp-processing/issues/57)
            """),
            dcc.Loading(
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                id="loading-1",
                type="default",
                children=[
                    html.Div(
                        children=[
                            dcc.Loading(
                                overlay_style={
                                    "visibility": "visible",
                                    "filter": "blur(2px)",
                                },
                                id="loading-stats",
                                type="default",
                                children=[
                                    dcc.Graph(figure=get_map_count_marches(lf)),
                                    dcc.Graph(
                                        figure=get_barchart_sources(
                                            lf, "dateNotification"
                                        )
                                    ),
                                    dcc.Graph(
                                        figure=get_barchart_sources(
                                            lf, "datePublicationDonnees"
                                        )
                                    ),
                                ],
                            )
                        ]
                    ),
                ],
            ),
        ],
    )
]
