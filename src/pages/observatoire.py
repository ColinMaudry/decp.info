import urllib.parse
from datetime import datetime, timedelta

import dash_bootstrap_components as dbc
import polars as pl
import polars.selectors as cs
from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)

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


def _apply_filters(
    lff: pl.LazyFrame,
    year,
    acheteur_id,
    acheteur_categorie,
    acheteur_departement_code,
    titulaire_id,
    titulaire_categorie,
    titulaire_departement_code,
    marche_type,
    considerations_sociales,
    considerations_environnementales,
) -> pl.LazyFrame:
    if year:
        lff = lff.filter(pl.col("dateNotification").dt.year() == int(year))
    else:
        lff = lff.filter(
            pl.col("dateNotification") > (datetime.now() - timedelta(days=365))
        )

    if acheteur_id:
        lff = lff.filter(pl.col("acheteur_id").str.contains(acheteur_id))
    else:
        if acheteur_categorie:
            lff = lff.filter(pl.col("acheteur_categorie") == acheteur_categorie)
        if acheteur_departement_code:
            lff = lff.filter(
                pl.col("acheteur_departement_code").is_in(acheteur_departement_code)
            )

    if titulaire_id:
        lff = lff.filter(pl.col("titulaire_id").str.contains(titulaire_id))
    else:
        if titulaire_categorie:
            lff = lff.filter(pl.col("titulaire_categorie") == titulaire_categorie)
        if titulaire_departement_code:
            lff = lff.filter(
                pl.col("titulaire_departement_code").is_in(titulaire_departement_code)
            )

    if marche_type:
        lff = lff.filter(pl.col("type") == marche_type)

    if considerations_sociales:
        lff = lff.filter(
            pl.col("considerationsSociales")
            .str.split(", ")
            .list.set_intersection(considerations_sociales)
            .list.len()
            > 0
        )

    if considerations_environnementales:
        lff = lff.filter(
            pl.col("considerationsEnvironnementales")
            .str.split(", ")
            .list.set_intersection(considerations_environnementales)
            .list.len()
            > 0
        )

    return lff


layout = [
    dcc.Store(id="dashboard-filters"),
    dcc.Location(id="dashboard_url", refresh="callback-nav"),
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Montants")),
            dbc.ModalBody(
                [
                    dcc.Markdown(
                        """
Les données saisies et publiées par les acheteurs comportent de nombreux montants farfelus qui sabotent les statistiques, au lieu de montants estimés avec rigueur. On parle de montant atteignant parfois les millions de milliards. Certains réutilisateurs mettent de côté ces marchés ou bien modifient les montants selon des règles fatalement arbitraires. J'ai fait le choix de ne quasiment pas modifier les données* afin de visibiliser le problème.

Alors, on fait comment ?

\\* Les montants composés de plus de 11 chiffres, sans les décimales, [sont ramenés](https://github.com/ColinMaudry/decp-processing/blob/main/src/tasks/clean.py#L63-L71) à 12 311 111 111, un nombre qui reste très élevé et qui est facilement reconnaissable.
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
                                    dcc.Download(id="download-observatoire"),
                                    dbc.Button(
                                        "Télécharger au format Excel",
                                        id="btn-download-observatoire",
                                        disabled=True,
                                        className="mt-2",
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
    Output("dashboard_acheteur_id", "value"),
    Output("dashboard_titulaire_id", "value"),
    Output("dashboard_url", "search"),
    Input("dashboard_url", "search"),
)
def restore_filters_from_url(search):
    if not search:
        return no_update, no_update, no_update

    params = urllib.parse.parse_qs(search.lstrip("?"))

    acheteur_id = params.get("acheteur_id", [None])[0] or no_update
    titulaire_id = params.get("titulaire_id", [None])[0] or no_update

    return acheteur_id, titulaire_id, ""


@callback(
    Output("cards", "children"),
    Output("btn-download-observatoire", "disabled"),
    Output("btn-download-observatoire", "children"),
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
    lff = _apply_filters(
        lff,
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

    if nb_marches == 0:
        dl_disabled, dl_text = True, "Pas de données à télécharger"
    elif nb_marches > 65000:
        dl_disabled, dl_text = True, "Téléchargement désactivé au-delà de 65 000 lignes"
    else:
        dl_disabled, dl_text = False, "Télécharger au format Excel"

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
        make_card(
            title="Sources de données",
            subtitle="Nombre de marchés attribués par mois de notification et source de données",
            fig=sources_barchart,
            lg=12,
            xl=8,
        )
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

    return dbc.Row(children=cards + geographic_maps + other_cards), dl_disabled, dl_text


@callback(
    Output("download-observatoire", "data"),
    Input("btn-download-observatoire", "n_clicks"),
    State("dashboard_year", "value"),
    State("dashboard_acheteur_id", "value"),
    State("dashboard_acheteur_categorie", "value"),
    State("dashboard_acheteur_departement_code", "value"),
    State("dashboard_titulaire_id", "value"),
    State("dashboard_titulaire_categorie", "value"),
    State("dashboard_titulaire_departement_code", "value"),
    State("dashboard_marche_type", "value"),
    State("dashboard_marche_considerationsSociales", "value"),
    State("dashboard_marche_considerationsEnvironnementales", "value"),
    prevent_initial_call=True,
)
def download_observatoire(
    _n_clicks,
    year,
    acheteur_id,
    acheteur_categorie,
    acheteur_departement_code,
    titulaire_id,
    titulaire_categorie,
    titulaire_departement_code,
    marche_type,
    considerations_sociales,
    considerations_environnementales,
):
    lff = _apply_filters(
        df.lazy(),
        year,
        acheteur_id,
        acheteur_categorie,
        acheteur_departement_code,
        titulaire_id,
        titulaire_categorie,
        titulaire_departement_code,
        marche_type,
        considerations_sociales,
        considerations_environnementales,
    )

    def to_bytes(buffer):
        lff.collect(engine="streaming").write_excel(buffer, worksheet="DECP")

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_observatoire_{date}.xlsx")


@callback(
    Output("montant-modal", "is_open"),
    Input({"type": "modal-trigger", "index": ALL}, "n_clicks"),
    Input("montant-modal-close", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_montant_modal(n_triggers, _close):
    return isinstance(ctx.triggered_id, dict) and any(n_triggers)
