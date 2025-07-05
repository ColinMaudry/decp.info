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
            Si nous disposons de beaucoup de données pour certains départements, pour d'autres les sources de DECP doivent encore être identifiées et ajoutées.

            Par exemple, les données des plateformes Atexo [ne sont pas encore présentes](https://github.com/ColinMaudry/decp-processing/issues/57).
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
                                id="loading-1",
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
