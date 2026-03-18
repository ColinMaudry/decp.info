from datetime import datetime, timedelta

import dash_bootstrap_components as dbc
import polars as pl
import polars.selectors as cs
from dash import ALL, Input, Output, callback, ctx, dcc, html, register_page

from src.figures import (
    get_barchart_sources,
    get_duplicate_matrix,
    get_geographic_maps,
    make_card,
    make_donut,
)
from src.utils import (
    departements,
    df,
    format_number,
    get_enum_values_as_dict,
    meta_content,
)

name = "Observatoire"

register_page(
    __name__,
    path="/observatoire",
    title="Observatoire | decp.info",
    name=name,
    description="Visualisez l'état de la publication des données essentielles des marchés publics en France.",
    image_url=meta_content["image_url"],
    order=3,
)
options_years = {}
for year in reversed(range(2017, datetime.now().year + 1)):
    year = str(year)
    options_years[year] = year

options_departements = {}
for code, obj in departements.items():
    options_departements[code] = f"{obj['departement']} ({code})"


layout = [
    dcc.Store(id="dashboard-filters"),
    dcc.Location(id="dashboard_url"),
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Montants")),
            dbc.ModalBody(
                [
                    dcc.Markdown(
                        """
Les données saisies et publiées par les acheteurs comportent de nombreux montants farfelus qui sabotent les statistiques, au lieu de montants estimés avec rigueur. On parle de montant atteignant parfois les millions de milliards. Certains réutilisateurs mettent de côté ces marchés ou bien modifient les montants selon des règles fatalement arbitraires. J'ai fait le choix de ne quasiment pas modifier les données* afin de visibiliser le problème.

Alors, on fait comment ?

\* Les montants composés de plus de 11 chiffres, sans les décimales, [sont ramenés](https://github.com/ColinMaudry/decp-processing/blob/main/src/tasks/clean.py#L63-L71) à 12 311 111 111, un nombre qui reste très élevé et qui est facilement reconnaissable.
"""
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button("Fermer", id="montant-modal-close", className="ms-auto")
            ),
        ],
        id="montant-modal",
        is_open=False,
    ),
    html.Div(
        className="container-fluid",
        children=[
            html.H2(name),
            dcc.Loading(
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                id="loading-statistques",
                type="default",
                children=[
                    dbc.Row(
                        [
                            dbc.Col(
                                xl=3,
                                lg=4,
                                id="filters",
                                children=[
                                    html.H5("Période d'attribution"),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_year",
                                                options=options_years,
                                                placeholder="12 derniers mois",
                                            ),
                                        ),
                                    ),
                                    html.H5("Acheteur"),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Input(
                                                id="dashboard_acheteur_id",
                                                placeholder="SIRET",
                                                style={"width": "100%"},
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_acheteur_categorie",
                                                options=get_enum_values_as_dict(
                                                    "acheteur_categorie"
                                                ),
                                                placeholder="Catégorie",
                                            )
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_acheteur_departement_code",
                                                searchable=True,
                                                multi=True,
                                                placeholder="Département",
                                                options=options_departements,
                                            ),
                                        ),
                                    ),
                                    html.H5("Titulaire"),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Input(
                                                id="dashboard_titulaire_id",
                                                placeholder="SIRET",
                                                style={"width": "100%"},
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_titulaire_categorie",
                                                placeholder="Catégorie",
                                                options=get_enum_values_as_dict(
                                                    "titulaire_categorie"
                                                ),
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_titulaire_departement_code",
                                                searchable=True,
                                                multi=True,
                                                placeholder="Département",
                                                options=options_departements,
                                            ),
                                        ),
                                    ),
                                    html.H5("Marché"),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_type",
                                                placeholder="Type",
                                                options=get_enum_values_as_dict("type"),
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_considerationsSociales",
                                                placeholder="Considérations sociales",
                                                options=get_enum_values_as_dict(
                                                    "considerationsSociales"
                                                ),
                                                multi=True,
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_considerationsEnvironnementales",
                                                placeholder="Considérations environnementales",
                                                multi=True,
                                                options=get_enum_values_as_dict(
                                                    "considerationsEnvironnementales"
                                                ),
                                            ),
                                        ),
                                    ),
                                ],
                            ),
                            dbc.Col(
                                width=12,
                                lg=8,
                                xl=9,
                                id="cards",
                                children=[],
                            ),
                        ]
                    )
                ],
            ),
        ],
    ),
]


@callback(
    Output("cards", "children"),
    Input("dashboard_year", "value"),
    Input("dashboard_acheteur_id", "value"),
    Input("dashboard_acheteur_categorie", "value"),
    Input("dashboard_acheteur_departement_code", "value"),
    Input("dashboard_titulaire_id", "value"),
    Input("dashboard_titulaire_categorie", "value"),
    Input("dashboard_titulaire_departement_code", "value"),
    Input("dashboard_marche_type", "value"),
    Input("dashboard_marche_considerationsSociales", "value"),
    Input("dashboard_marche_considerationsEnvironnementales", "value"),
)
def udpate_dashboard_cards(
    dashboard_year,
    dashboard_acheteur_id,
    dashboard_acheteur_categorie,
    dashboard_acheteur_departement_code,
    dashboard_titulaire_id,
    dashboard_titulaire_categorie,
    dashboard_titulaire_departement_code,
    dashboard_marche_type,
    dashboard_marche_considerations_sociales,
    dashboard_marche_considerations_environnementales,
):
    lff: pl.LazyFrame = df.lazy()
    lff = lff.select(
        "uid",
        cs.starts_with("acheteur"),
        cs.starts_with("titulaire"),
        "dateNotification",
        "montant",
        "considerationsSociales",
        "considerationsEnvironnementales",
        "sourceDataset",
        "type",
    )

    # Application des filtres

    ## Période

    if dashboard_year:
        lff = lff.filter(pl.col("dateNotification").dt.year() == int(dashboard_year))
    else:
        lff = lff.filter(
            pl.col("dateNotification") > (datetime.now() - timedelta(days=365))
        )

    ## Acheteur

    if dashboard_acheteur_id:
        lff = lff.filter(pl.col("acheteur_id").str.contains(dashboard_acheteur_id))
    else:
        if dashboard_acheteur_categorie:
            lff = lff.filter(
                pl.col("acheteur_categorie") == dashboard_acheteur_categorie
            )

        if dashboard_acheteur_departement_code:
            lff = lff.filter(
                pl.col("acheteur_departement_code").is_in(
                    dashboard_acheteur_departement_code
                )
            )

    ## Titulaire

    if dashboard_titulaire_id:
        lff = lff.filter(pl.col("titulaire_id").str.contains(dashboard_titulaire_id))
    else:
        if dashboard_titulaire_categorie:
            lff = lff.filter(
                pl.col("titulaire_categorie") == dashboard_titulaire_categorie
            )

        if dashboard_titulaire_departement_code:
            lff = lff.filter(
                pl.col("titulaire_departement_code").is_in(
                    dashboard_titulaire_departement_code
                )
            )

    ## Marché

    if dashboard_marche_type:
        lff = lff.filter(pl.col("type") == dashboard_marche_type)

    if dashboard_marche_considerations_sociales:
        lff = lff.filter(
            pl.col("considerationsSociales")
            .str.split(", ")
            .list.set_intersection(dashboard_marche_considerations_sociales)
            .list.len()
            > 0
        )

    if dashboard_marche_considerations_environnementales:
        lff = lff.filter(
            pl.col("considerationsEnvironnementales")
            .str.split(", ")
            .list.set_intersection(dashboard_marche_considerations_environnementales)
            .list.len()
            > 0
        )

    # Génération des métriques
    dff = lff.collect(engine="streaming")

    # À transformer en fonction
    nb_acheteurs = dff.select("acheteur_id").n_unique()
    nb_titulaires = dff.select("titulaire_id", "titulaire_typeIdentifiant").n_unique()

    df_per_uid = (
        dff.select("uid", "montant").group_by("uid").agg(pl.col("montant").first())
    )

    total_montant = int(df_per_uid.select(pl.col("montant").sum()).item())
    nb_marches = df_per_uid.height

    cards = []

    card_basic_counts = [
        html.P(["Nombre de marchés : ", html.Strong(str(format_number(nb_marches)))]),
        html.P(
            ["Nombre d'acheteurs : ", html.Strong(str(format_number(nb_acheteurs)))]
        ),
        html.P(
            ["Nombre de titulaires : ", html.Strong(str(format_number(nb_titulaires)))]
        ),
        html.P(
            [
                "Montant total (",
                html.Span(
                    "?",
                    id={"type": "modal-trigger", "index": "montant"},
                    style={"cursor": "pointer", "textDecoration": "underline dotted"},
                ),
                ") : ",
                html.Strong(format_number(total_montant) + " €"),
            ]
        ),
    ]

    cards.append(make_card(title="Résumé", paragraphs=card_basic_counts))

    donut_acheteur_categorie = make_donut(
        lff, "acheteur_categorie", nulls="Autres", per_uid=True
    )
    cards.append(
        make_card(
            title="Catégorie d'acheteur", fig=donut_acheteur_categorie, lg=12, xl=8
        )
    )

    donut_titulaire_categorie = make_donut(
        lff, "titulaire_categorie", per_uid=False, nulls="?"
    )
    cards.append(
        make_card(title="Catégorie d'entreprise", fig=donut_titulaire_categorie)
    )

    donut_marche_type = make_donut(lff, "type", per_uid=True, nulls="?")
    cards.append(make_card(title="Type d'achat", fig=donut_marche_type))

    geographic_maps: list[dbc.Col] = get_geographic_maps(dff)

    other_cards = []

    sources_barchart = get_barchart_sources(lff, type_date="dateNotification")
    other_cards.append(
        make_card(title="Sources de données", fig=sources_barchart, lg=12, xl=8)
    )

    duplicate_matrix = get_duplicate_matrix()
    other_cards.append(
        make_card(
            title="Matrice de doublons entre sources de données",
            subtitle="Ce graphique illustre les doublons de marchés publics entre sources, c'est-à-dire la proportion de marchés publiés par plus d'une source.",
            fig=duplicate_matrix,
            lg=12,
            xl=8,
        )
    )

    return dbc.Row(children=cards + geographic_maps + other_cards)


@callback(
    Output("montant-modal", "is_open"),
    Input({"type": "modal-trigger", "index": ALL}, "n_clicks"),
    Input("montant-modal-close", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_montant_modal(n_triggers, _close):
    return isinstance(ctx.triggered_id, dict) and any(n_triggers)
