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
    df_acheteurs,
    df_titulaires,
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
    dcc.Location(id="dashboard_url", refresh="callback-nav"),
    dcc.Store(id="observatoire-filters", storage_type="local"),
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
            html.H2(children=[name], id="page_title"),
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
                                                debounce=True,
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
                                                debounce=True,
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
                                    dcc.Input(
                                        id="observatoire-share-url",
                                        readOnly=True,
                                        style={"display": "none"},
                                    ),
                                    html.Div(id="observatoire-copy-container"),
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
    Output("dashboard_year", "value"),
    Output("dashboard_acheteur_id", "value"),
    Output("dashboard_acheteur_categorie", "value"),
    Output("dashboard_acheteur_departement_code", "value"),
    Output("dashboard_titulaire_id", "value"),
    Output("dashboard_titulaire_categorie", "value"),
    Output("dashboard_titulaire_departement_code", "value"),
    Output("dashboard_marche_type", "value"),
    Output("dashboard_marche_considerationsSociales", "value"),
    Output("dashboard_marche_considerationsEnvironnementales", "value"),
    Input("dashboard_url", "search"),
    Input("dashboard_url", "pathname"),
    State("observatoire-filters", "data"),
)
def restore_filters(search, _pathname, stored_filters):
    if search:
        params = urllib.parse.parse_qs(search.lstrip("?"))
        acheteur_id = (params.get("acheteur_id") or [None])[0] or None
        titulaire_id = (params.get("titulaire_id") or [None])[0] or None
        if acheteur_id or titulaire_id:
            return (
                None,
                acheteur_id,
                None,
                None,
                titulaire_id,
                None,
                None,
                None,
                None,
                None,
            )

    if stored_filters:
        return (
            stored_filters.get("year"),
            stored_filters.get("acheteur_id"),
            stored_filters.get("acheteur_categorie"),
            stored_filters.get("acheteur_departement_code"),
            stored_filters.get("titulaire_id"),
            stored_filters.get("titulaire_categorie"),
            stored_filters.get("titulaire_departement_code"),
            stored_filters.get("marche_type"),
            stored_filters.get("considerations_sociales"),
            stored_filters.get("considerations_environnementales"),
        )

    return (no_update,) * 10


@callback(
    Output("observatoire-filters", "data"),
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
    prevent_initial_call=True,
)
def save_filters_to_storage(
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
    return {
        "year": year,
        "acheteur_id": acheteur_id,
        "acheteur_categorie": acheteur_categorie,
        "acheteur_departement_code": acheteur_departement_code,
        "titulaire_id": titulaire_id,
        "titulaire_categorie": titulaire_categorie,
        "titulaire_departement_code": titulaire_departement_code,
        "marche_type": marche_type,
        "considerations_sociales": considerations_sociales,
        "considerations_environnementales": considerations_environnementales,
    }


@callback(
    Output("observatoire-share-url", "value"),
    Output("observatoire-copy-container", "children"),
    Input("dashboard_acheteur_id", "value"),
    Input("dashboard_titulaire_id", "value"),
    State("dashboard_url", "href"),
    prevent_initial_call=True,
)
def sync_observatoire_share_url(acheteur_id, titulaire_id, href):
    if not href:
        return no_update, no_update

    base_url = href.split("?")[0]

    params = {}
    if acheteur_id:
        params["acheteur_id"] = acheteur_id
    if titulaire_id:
        params["titulaire_id"] = titulaire_id

    query_string = urllib.parse.urlencode(params)
    full_url = f"{base_url}?{query_string}" if query_string else base_url

    copy_button = dcc.Clipboard(
        id="btn-copy-observatoire-url",
        target_id="observatoire-share-url",
        title="Copier l'URL de cette vue",
        style={
            "display": "inline-block",
            "fontSize": 20,
            "verticalAlign": "top",
            "cursor": "pointer",
        },
        className="fa fa-link",
        children=[
            dbc.Button(
                "Partager",
                className="btn btn-primary mt-2",
                title="Copier l'adresse de cette vue filtrée pour la partager.",
            )
        ],
    )

    return full_url, copy_button


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
            title="Catégorie d'acheteur",
            subtitle="en nombre de marchés attribués",
            fig=donut_acheteur_categorie,
            lg=12,
            xl=8,
        )
    )

    donut_titulaire_categorie = make_donut(
        lff, "titulaire_categorie", per_uid=False, nulls="?"
    )
    cards.append(
        make_card(
            title="Catégorie d'entreprise",
            subtitle="en nombre de marchés attribués",
            fig=donut_titulaire_categorie,
        )
    )

    donut_marche_type = make_donut(lff, "type", per_uid=True, nulls="?")
    cards.append(
        make_card(
            title="Type d'achat",
            subtitle="en nombre de marchés attribués",
            fig=donut_marche_type,
        )
    )

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


@callback(
    Output("page_title", "children"),
    Input("dashboard_acheteur_id", "value"),
    Input("dashboard_titulaire_id", "value"),
    prevent_initial_call=False,
)
def add_organization_name_in_title(acheteur_id, titulaire_id):
    def lookup_nom(df_org, id_col, nom_col, org_id):
        match = df_org.filter(pl.col(id_col) == org_id)
        return match[nom_col].item(0) if match.height >= 1 else None

    if acheteur_id and len(acheteur_id) == 14:
        if nom := lookup_nom(df_acheteurs, "acheteur_id", "acheteur_nom", acheteur_id):
            return [
                name,
                html.Small(nom, className="text-muted d-block fw-normal fs-5"),
            ]
    elif titulaire_id and len(titulaire_id) == 14:
        if nom := lookup_nom(
            df_titulaires, "titulaire_id", "titulaire_nom", titulaire_id
        ):
            return [
                name,
                html.Small(nom, className="text-muted d-block fw-normal fs-5"),
            ]
    return name
