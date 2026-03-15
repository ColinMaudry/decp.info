from datetime import datetime, timedelta

import dash_bootstrap_components as dbc
import polars as pl
import polars.selectors as cs
from dash import Input, Output, callback, dcc, html, register_page

from src.figures import (
    get_geographic_maps,
)
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
                                width=12,
                                md=3,
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
                                            placeholder="Catégorie d'acheteur",
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
                                ],
                            ),
                            dbc.Col(
                                width=12,
                                md=9,
                                id="cards",
                                children=[
                                    dbc.Row(
                                        (
                                            dbc.Col(
                                                width=6,
                                                md=4,
                                                className="card",
                                                id="card_basic_counts",
                                            )
                                        ),
                                        className="mb-4",
                                    ),
                                    dbc.Row(id="maps_row"),
                                ],
                            ),
                        ]
                    )
                ],
            ),
        ],
    ),
]


@callback(
    Output("card_basic_counts", "children"),
    Output("maps_row", "children"),
    Input("dashboard_year", "value"),
    Input("dashboard_acheteur_categorie", "value"),
    Input("dashboard_acheteur_departement_code", "value"),
)
def udpate_dashboard_cards(
    dashboard_year, dashboard_acheteur_categorie, dashboard_acheteur_departement_code
):
    lff: pl.LazyFrame = df.lazy()
    lff = lff.select(
        "uid",
        cs.starts_with("acheteur"),
        cs.starts_with("titulaire"),
        "dateNotification",
        "montant",
    )

    # Application des filtres

    if dashboard_year:
        lff = lff.filter(pl.col("dateNotification").dt.year() == int(dashboard_year))
    else:
        lff = lff.filter(
            pl.col("dateNotification") > (datetime.now() - timedelta(days=365))
        )

    if dashboard_acheteur_categorie:
        lff = lff.filter(pl.col("acheteur_categorie") == dashboard_acheteur_categorie)

    if dashboard_acheteur_departement_code:
        lff = lff.filter(
            pl.col("acheteur_departement_code").is_in(
                dashboard_acheteur_departement_code
            )
        )

    # Génération des métriques
    dff = lff.collect()

    nb_acheteurs = dff.select("acheteur_id").n_unique()
    nb_titulaires = dff.select("titulaire_id", "titulaire_typeIdentifiant").n_unique()

    df_per_uid = (
        dff.select("uid", "montant").group_by("uid").agg(pl.col("montant").first())
    )
    total_montant = df_per_uid.select(pl.col("montant").sum()).item()
    nb_marches = df_per_uid.height

    # À transformer en fonction
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

    geographic_maps = get_geographic_maps(dff)

    return card_basic_counts, geographic_maps
