from datetime import datetime, timedelta

import dash_bootstrap_components as dbc
import polars as pl
import polars.selectors as cs
from dash import Input, Output, callback, dcc, html, register_page

from src.figures import get_geographic_maps, make_card, make_donut
from src.utils import (
    departements,
    df,
    format_number,
    get_enum_values_as_dict,
    meta_content,
)

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
                                        dcc.Dropdown(
                                            id="dashboard_year",
                                            options=options_years,
                                            placeholder="12 derniers mois",
                                        ),
                                    ),
                                    html.H5("Acheteur"),
                                    dbc.Row(
                                        dcc.Dropdown(
                                            id="dashboard_acheteur_categorie",
                                            options=get_enum_values_as_dict(
                                                "acheteur_categorie"
                                            ),
                                            placeholder="Catégorie",
                                        ),
                                    ),
                                    dbc.Row(
                                        dcc.Dropdown(
                                            id="dashboard_acheteur_departement_code",
                                            searchable=True,
                                            multi=True,
                                            placeholder="Code département acheteur",
                                            options=options_departements,
                                        ),
                                    ),
                                    html.H5("Titulaire"),
                                    dbc.Row(
                                        dcc.Dropdown(
                                            id="dashboard_titulaire_categorie",
                                            placeholder="Catégorie",
                                            options=get_enum_values_as_dict(
                                                "titulaire_categorie"
                                            ),
                                        ),
                                    ),
                                    html.H5("Marché"),
                                    dbc.Row(
                                        dcc.Dropdown(
                                            id="dashboard_marche_type",
                                            placeholder="Type",
                                            options=get_enum_values_as_dict("type"),
                                        ),
                                    ),
                                    dbc.Row(
                                        dcc.Dropdown(
                                            id="dashboard_marche_considerationsSociales",
                                            placeholder="Considérations sociales",
                                            options=get_enum_values_as_dict(
                                                "considerationsSociales"
                                            ),
                                            multi=True,
                                        ),
                                    ),
                                    dbc.Row(
                                        dcc.Dropdown(
                                            id="dashboard_marche_considerationsEnvironnementales",
                                            placeholder="Considérations environnementales",
                                            multi=True,
                                            options=get_enum_values_as_dict(
                                                "considerationsEnvironnementales"
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
    Input("dashboard_acheteur_categorie", "value"),
    Input("dashboard_acheteur_departement_code", "value"),
    Input("dashboard_titulaire_categorie", "value"),
    Input("dashboard_marche_type", "value"),
    Input("dashboard_marche_considerationsSociales", "value"),
    Input("dashboard_marche_considerationsEnvironnementales", "value"),
)
def udpate_dashboard_cards(
    dashboard_year,
    dashboard_acheteur_categorie,
    dashboard_acheteur_departement_code,
    dashboard_titulaire_categorie,
    dashboard_marche_type,
    dashboard_marche_considerationsSociales,
    dashboard_marche_considerationsEnvironnementales,
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

    if dashboard_acheteur_categorie:
        lff = lff.filter(pl.col("acheteur_categorie") == dashboard_acheteur_categorie)

    if dashboard_acheteur_departement_code:
        lff = lff.filter(
            pl.col("acheteur_departement_code").is_in(
                dashboard_acheteur_departement_code
            )
        )

    ## Titulaire

    if dashboard_titulaire_categorie:
        lff = lff.filter(pl.col("titulaire_categorie") == dashboard_titulaire_categorie)

    ## Marché

    if dashboard_marche_type:
        lff = lff.filter(pl.col("type") == dashboard_marche_type)

    if dashboard_marche_considerationsSociales:
        lff = lff.filter(
            pl.col("considerationsSociales")
            .str.split(", ")
            .list.set_intersection(dashboard_marche_considerationsSociales)
            .list.len()
            > 0
        )

    if dashboard_marche_considerationsEnvironnementales:
        lff = lff.filter(
            pl.col("considerationsEnvironnementales")
            .str.split(", ")
            .list.set_intersection(dashboard_marche_considerationsEnvironnementales)
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
    total_montant = df_per_uid.select(pl.col("montant").sum()).item()
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
        html.P(["Montant total : ", html.Strong(format_number(total_montant) + " €")]),
    ]

    cards.append(make_card(title="Résumé", paragraphs=card_basic_counts))

    donut_acheteur_categorie = make_donut(lff, "acheteur_categorie")
    cards.append(make_card(title="Catégorie d'acheteur", fig=donut_acheteur_categorie))

    donut_titulaire_categorie = make_donut(lff, "titulaire_categorie")
    cards.append(
        make_card(title="Catégorie d'entreprise", fig=donut_titulaire_categorie)
    )

    geographic_maps: list[dbc.Col] = get_geographic_maps(dff)

    return dbc.Row(children=cards + geographic_maps)
