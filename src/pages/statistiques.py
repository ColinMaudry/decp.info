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
