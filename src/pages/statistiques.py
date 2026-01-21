from datetime import datetime

from dash import dcc, html, register_page

from src.figures import (
    get_barchart_sources,
    get_duplicate_matrix,
    get_map_count_marches,
    get_yearly_statistics,
)
from src.utils import df, format_number, get_statistics, meta_content

name = "Statistiques"

register_page(
    __name__,
    path="/statistiques",
    title="Statistiques | decp.info",
    name=name,
    description="Visualisez l'état de la publication des données essentielles des marchés publics en France.",
    image_url=meta_content["image_url"],
    order=3,
)

statistics: dict = get_statistics()
today_str = datetime.fromisoformat(statistics["datetime"]).strftime("%d/%m/%Y")

layout = [
    html.Div(
        className="container",
        children=[
            html.H2(name),
            dcc.Loading(
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                id="loading-statistques",
                type="default",
                children=[
                    html.Div(
                        children=[
                            dcc.Markdown(f"""
                            La publication de données essentielles de marchés publics (DECP) est souvent effectuée par
                            les plateformes de marchés publics (profils d'acheteurs). Cependant, certaines plateformes ne publient pas,
                            ou publient d'une manière qui rend la récupération des données compliquée. Les données présentées sur ce site
                            ne représentent donc pas tous les marchés attribués en France, seulement une partie significative.

                            L'ajout de nouvelles plateformes [est en cours](https://github.com/ColinMaudry/decp-processing/issues?q=is%3Aissue%20label%3A%22source%20de%20donn%C3%A9es%22),
                            toutes les [contributions](/a-propos#contribuer) sont les bienvenues pour atteindre l'exhaustivité.

                            Les statistiques publiées sur cette page ont été produites automatiquement à partir des données les plus récentes ({today_str}).
                            """),
                            dcc.Graph(figure=get_map_count_marches(df)),
                            html.H3(
                                "Statistiques générales sur les marchés",
                                id="marches",
                            ),
                            html.P(
                                "À noter qu'une fois un marché attribué ses données essentielles peuvent malheureusement mettre plusieurs mois à être publiées par l'acheteur."
                            ),
                            html.H4("Statistiques cumulées"),
                            dcc.Markdown(f"""
                            - Nombre de marchés publics et accord-cadres : {format_number(statistics["nb_marches"])}
                            - Nombre d'acheteurs publics (SIRET) : {format_number(statistics["nb_acheteurs_uniques"])}
                            - Nombre de titulaires (SIRET) : {format_number(statistics["nb_titulaires_uniques"])}

                            Je ne publie pas encore de statistiques sur les montants de marchés car je n'ai pas encore trouvé la bonne formule pour traiter les trop nombreux montants fantaisistes qui polluent les calculs.
                                                        """),
                            html.H4("Statistiques par année"),
                            get_yearly_statistics(statistics, today_str),
                            get_duplicate_matrix(),
                            html.H3("Nombre de marchés par source dans le temps"),
                            dcc.Graph(
                                figure=get_barchart_sources(df, "dateNotification")
                            ),
                            dcc.Graph(
                                figure=get_barchart_sources(
                                    df, "datePublicationDonnees"
                                )
                            ),
                        ],
                    )
                ],
            ),
        ],
    )
]
