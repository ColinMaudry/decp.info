import urllib.parse
from datetime import datetime

import dash_bootstrap_components as dbc
import polars as pl
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

from src.cache import cache
from src.db import query_marches, schema
from src.figures import (
    DataTable,
    get_barchart_sources,
    get_dashboard_summary_table,
    get_distance_histogram,
    get_duplicate_matrix,
    get_geographic_maps,
    get_top_org_table,
    make_card,
    make_column_picker,
    make_donut,
)
from src.utils import logger
from src.utils.data import (
    DEPARTEMENTS,
    DF_ACHETEURS,
    DF_TITULAIRES,
    prepare_dashboard_data,
)
from src.utils.frontend import get_enum_values_as_dict
from src.utils.seo import META_CONTENT
from src.utils.table import COLUMNS, get_default_hidden_columns, prepare_table_data

NAME = "Observatoire"

register_page(
    __name__,
    path="/observatoire",
    title="Observatoire | decp.info",
    name=NAME,
    description="Visualisez l'état de la publication des données essentielles des marchés publics en France.",
    image_url=META_CONTENT["image_url"],
    order=3,
)
OPTIONS_YEARS = []
for year in reversed(range(2017, datetime.now().year + 1)):
    option_year = {
        "label": str(year),
        "value": year,
    }
    OPTIONS_YEARS.append(option_year)

OPTIONS_DEPARTEMENTS = []
for code in DEPARTEMENTS.keys():
    departement = {
        "label": f"{DEPARTEMENTS[code]['departement']} ({code})",
        "value": code,
    }
    OPTIONS_DEPARTEMENTS.append(departement)

OBSERVATOIRE_COLUMNS = [
    col
    for col in schema.names()
    if col.startswith("acheteur")
    or col.startswith("titulaire")
    or col
    in [
        "uid",
        "dateNotification",
        "montant",
        "considerationsSociales",
        "considerationsEnvironnementales",
        "marcheInnovant",
        "sousTraitanceDeclaree",
        "techniques",
        "sourceDataset",
        "type",
        "codeCPV",
    ]
]

layout = [
    dcc.Location(id="dashboard_url", refresh="callback-nav"),
    dcc.Store(id="observatoire-filters", storage_type="local"),
    dcc.Store(id="observatoire-hidden-columns", storage_type="local"),
    dcc.Store(
        id="filter-cleanup-trigger-observatoire-preview"
    ),  # utilisé juste pour ne pas avoir à adapter les données retournées de prepare_table data
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Montants")),
            dbc.ModalBody(
                [
                    dcc.Markdown(
                        """
Les données saisies et publiées par les acheteurs comportent de nombreux montants farfelus qui sabotent les statistiques, au lieu de montants estimés avec rigueur. On parle de montants atteignant parfois les millions de milliards. Certains réutilisateurs des données mettent de côté ces marchés ou bien modifient les montants selon des règles fatalement arbitraires. J'ai fait le choix de ne quasiment pas modifier les données* afin de visibiliser le problème.

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
            html.H2(children=[NAME], id="page_title"),
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
                                                options=OPTIONS_YEARS,
                                                placeholder="12 derniers mois",
                                                persistence=True,
                                                persistence_type="local",
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
                                                persistence=True,
                                                persistence_type="local",
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
                                                persistence=True,
                                                persistence_type="local",
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
                                                options=OPTIONS_DEPARTEMENTS,
                                                persistence=True,
                                                persistence_type="local",
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
                                                persistence=True,
                                                persistence_type="local",
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
                                                persistence=True,
                                                persistence_type="local",
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
                                                options=OPTIONS_DEPARTEMENTS,
                                                persistence=True,
                                                persistence_type="local",
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
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Input(
                                                id="dashboard_marche_objet",
                                                placeholder="Objet",
                                                debounce=True,
                                                style={"width": "100%"},
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Input(
                                                    id="dashboard_marche_code_cpv",
                                                    placeholder="Code CPV (début)",
                                                    debounce=True,
                                                    style={"width": "100%"},
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                lg=8,
                                            ),
                                            dbc.Col(
                                                html.A(
                                                    "liste des codes",
                                                    href="https://cpvcodes.eu/fr",
                                                    target="_blank",
                                                ),
                                                lg=4,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                dcc.Input(
                                                    id="dashboard_montant_min",
                                                    placeholder="Montant min.",
                                                    type="number",
                                                    min=0,
                                                    debounce=True,
                                                    style={"width": "100%"},
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                width=6,
                                            ),
                                            dbc.Col(
                                                dcc.Input(
                                                    id="dashboard_montant_max",
                                                    placeholder="Montant max.",
                                                    type="number",
                                                    min=0,
                                                    debounce=True,
                                                    style={"width": "100%"},
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                width=6,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_techniques",
                                                placeholder="Techniques d'achat",
                                                options=get_enum_values_as_dict(
                                                    "techniques"
                                                ),
                                                multi=True,
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col("Sous-traitance :", lg=5),
                                            dbc.Col(
                                                dbc.RadioItems(
                                                    id="dashboard_marche_sous_traitance_declaree",
                                                    options=[
                                                        {
                                                            "label": "Tous",
                                                            "value": "all",
                                                        },
                                                        {
                                                            "label": "Oui",
                                                            "value": "oui",
                                                        },
                                                        {
                                                            "label": "Non",
                                                            "value": "non",
                                                        },
                                                    ],
                                                    value="all",
                                                    inline=True,
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                lg=7,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col("Marché innovant :", lg=5),
                                            dbc.Col(
                                                dbc.RadioItems(
                                                    id="dashboard_marche_innovant",
                                                    options=[
                                                        {
                                                            "label": "Tous",
                                                            "value": "all",
                                                        },
                                                        {
                                                            "label": "Oui",
                                                            "value": "oui",
                                                        },
                                                        {
                                                            "label": "Non",
                                                            "value": "non",
                                                        },
                                                    ],
                                                    value="all",
                                                    inline=True,
                                                    persistence=True,
                                                    persistence_type="local",
                                                ),
                                                lg=7,
                                            ),
                                        ]
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_considerations_sociales",
                                                placeholder="Considérations sociales",
                                                options=get_enum_values_as_dict(
                                                    "considerationsSociales"
                                                ),
                                                multi=True,
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        dbc.Col(
                                            dcc.Dropdown(
                                                id="dashboard_marche_considerations_environnementales",
                                                placeholder="Considérations environnementales",
                                                multi=True,
                                                options=get_enum_values_as_dict(
                                                    "considerationsEnvironnementales"
                                                ),
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ),
                                    ),
                                    dbc.Row(
                                        [
                                            dbc.Col(
                                                [
                                                    dcc.Download(
                                                        id="download-observatoire"
                                                    ),
                                                    dbc.Button(
                                                        "Voir les données",
                                                        id="btn-observatoire-preview",
                                                        className="btn btn-primary mt-2",
                                                        color="primary",
                                                        outline=True,
                                                    ),
                                                    dcc.Input(
                                                        id="observatoire-share-url",
                                                        readOnly=True,
                                                        style={"display": "none"},
                                                    ),
                                                ],
                                                lg=12,
                                                xl=6,
                                            ),
                                            dbc.Col(
                                                id="observatoire-copy-container",
                                                lg=12,
                                                xl=6,
                                            ),
                                        ]
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
    dbc.Offcanvas(
        id="observatoire-preview",
        title="Prévisualisation des données",
        placement="bottom",
        is_open=False,
        scrollable=True,
        style={"height": "75vh"},
        children=[
            # Header row: title + "Colonnes affichées" button
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            className="table-menu",
                            children=[
                                dbc.Button(
                                    "Choisir les colonnes",
                                    id="observatoire-preview-columns-open",
                                    className="btn btn-primary",
                                ),
                                html.P(id="nb_rows_observatoire"),
                                dbc.Button(
                                    "Télécharger au format Excel",
                                    id="btn-download-observatoire",
                                    disabled=True,
                                    className="btn btn-primary",
                                    outline=True,
                                ),
                            ],
                        ),
                        width="auto",
                    ),
                ],
                className="mb-2 align-items-center",
            ),
            # Column picker modal
            dbc.Modal(
                [
                    dbc.ModalHeader(
                        dbc.ModalTitle("Colonnes affichées dans la prévisualisation")
                    ),
                    dbc.ModalBody(
                        id="observatoire-preview-columns-body",
                        children=make_column_picker("observatoire_preview"),
                    ),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Fermer",
                            id="observatoire-preview-columns-close",
                            className="ms-auto",
                            n_clicks=0,
                        )
                    ),
                ],
                id="observatoire-preview-columns-modal",
                is_open=False,
                fullscreen="md-down",
                scrollable=True,
                size="xl",
            ),
            # DataTable
            html.Div(
                className="marches_table",
                children=DataTable(
                    dtid="observatoire-preview-table",
                    page_size=5,
                    page_action="custom",
                    sort_action="custom",
                    filter_action="custom",
                    hidden_columns=[],
                    columns=[{"id": col, "name": col} for col in OBSERVATOIRE_COLUMNS],
                ),
            ),
        ],
    ),
]


FILTER_PARAMS = [
    # (component_id, url_key, is_multi, default_value)
    ("dashboard_year", "annee", False, None),
    ("dashboard_acheteur_id", "acheteur_id", False, None),
    ("dashboard_acheteur_categorie", "acheteur_cat", False, None),
    ("dashboard_acheteur_departement_code", "acheteur_dept", True, None),
    ("dashboard_titulaire_id", "titulaire_id", False, None),
    ("dashboard_titulaire_categorie", "titulaire_cat", False, None),
    ("dashboard_titulaire_departement_code", "titulaire_dept", True, None),
    ("dashboard_marche_type", "type", False, None),
    ("dashboard_marche_objet", "objet", False, None),
    ("dashboard_marche_code_cpv", "cpv", False, None),
    ("dashboard_montant_min", "montant_min", False, None),
    ("dashboard_montant_max", "montant_max", False, None),
    ("dashboard_marche_techniques", "techniques", True, None),
    ("dashboard_marche_innovant", "innovant", False, "all"),
    ("dashboard_marche_sous_traitance_declaree", "sous_traitance", False, "all"),
    ("dashboard_marche_considerations_sociales", "social", True, None),
    ("dashboard_marche_considerations_environnementales", "env", True, None),
]


@callback(
    *[Output(fp[0], "value") for fp in FILTER_PARAMS],
    Input("dashboard_url", "search"),
    Input("dashboard_url", "pathname"),
    State("observatoire-filters", "data"),
)
def restore_filters(search, _pathname, stored_filters):
    if search:
        params = urllib.parse.parse_qs(search.lstrip("?"))
        known_keys = {fp[1] for fp in FILTER_PARAMS}
        if any(k in params for k in known_keys):
            values = []
            for _comp_id, url_key, is_multi, default in FILTER_PARAMS:
                if url_key in params:
                    if is_multi:
                        values.append(params[url_key])
                    else:
                        raw = params[url_key][0]
                        if url_key in ("montant_min", "montant_max"):
                            try:
                                raw = float(raw)
                            except (ValueError, TypeError):
                                raw = None
                        values.append(raw)
                else:
                    values.append(default)
            return tuple(values)
    return (no_update,) * 17


@callback(
    Output("observatoire-share-url", "value"),
    Output("observatoire-copy-container", "children"),
    *[Input(fp[0], "value") for fp in FILTER_PARAMS],
    Input("dashboard_url", "href"),
)
def sync_observatoire_share_url(*args):
    # Last arg is href (State), rest are filter values
    filter_values = args[:-1]
    href = args[-1]

    if not href:
        return no_update, no_update

    base_url = href.split("?")[0]

    params = []
    for (_, url_key, is_multi, default), value in zip(FILTER_PARAMS, filter_values):
        if value is None or value == default or value == [] or value == "":
            continue
        if is_multi and isinstance(value, list):
            for v in value:
                params.append((url_key, v))
        else:
            params.append((url_key, value))

    query_string = urllib.parse.urlencode(params)
    full_url = f"{base_url}?{query_string}" if query_string else base_url

    if params:
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
                    "Partager cette vue",
                    id="btn-copy-observatoire",
                    className="btn btn-primary mt-2",
                    title="Copier l'adresse de cette vue filtrée pour la partager.",
                )
            ],
        )
    else:
        copy_button = html.Div()

    return full_url, copy_button


@callback(
    Output("observatoire-copy-container", "children", allow_duplicate=True),
    Input("btn-copy-observatoire", "n_clicks", allow_optional=True),
    prevent_initial_call=True,
)
def show_confirmation(n_clicks):
    if n_clicks:
        return html.Span(
            "Adresse de la vue copiée",
            style={"color": "green", "fontWeight": "bold", "marginLeft": "10px"},
        )
    return no_update


def _normalize_filter_params(filter_params: dict) -> tuple:
    """Produce a deterministic, hashable key for caching."""
    return tuple(
        sorted(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in filter_params.items()
        )
    )


@cache.memoize(timeout=3600)
def _compute_dashboard_children(cache_key: tuple):
    filter_params = {k: (list(v) if isinstance(v, tuple) else v) for k, v in cache_key}

    lff: pl.LazyFrame = query_marches().lazy()
    lff = prepare_dashboard_data(lff=lff, **filter_params)

    dff = lff.collect(engine="streaming")
    logger.debug("Filter data: " + str(dff.height))

    df_per_uid = (
        dff.select("uid", "montant").group_by("uid").agg(pl.col("montant").first())
    )
    nb_marches = df_per_uid.height

    cards = []
    card_summary_table = get_dashboard_summary_table(dff, df_per_uid, nb_marches)
    cards.append(make_card(title="Résumé", paragraphs=card_summary_table))

    donut_acheteur_categorie, nb_acheteur_categories = make_donut(
        lff,
        "acheteur_categorie",
        nulls="Autres",
        per_uid=True,
        potentially_many_names=True,
    )
    cards.append(
        make_card(
            title="Catégorie d'acheteur",
            subtitle="en nombre de marchés attribués",
            fig=donut_acheteur_categorie,
            lg=12 if nb_acheteur_categories > 4 else 6,
            xl=8 if nb_acheteur_categories > 4 else 4,
        )
    )

    donut_titulaire_categorie = make_donut(
        lff, "titulaire_categorie", per_uid=False, nulls="?"
    )
    cards.append(
        make_card(
            title="Catégorie d'entreprise",
            subtitle="en nombre de titulaires",
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

    distance_histogram = get_distance_histogram(lff)
    cards.append(
        make_card(
            title="Distance acheteur–titulaire",
            subtitle="en nombre de marchés, échelle logarithmique",
            fig=distance_histogram,
        )
    )

    top_acheteurs = get_top_org_table(
        lff, org_type="acheteur", filters=False, extra_columns=[]
    )
    cards.append(make_card(title="Top acheteurs", fig=top_acheteurs, lg=12, xl=8))

    top_titulaires = get_top_org_table(
        lff, org_type="titulaire", filters=False, extra_columns=[]
    )
    cards.append(make_card(title="Top titulaires", fig=top_titulaires, lg=12, xl=8))

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

    return cards + geographic_maps + other_cards


@callback(
    Output("cards", "children"),
    Output("observatoire-filters", "data"),
    *[Input(fp[0], "value") for fp in FILTER_PARAMS],
)
def update_dashboard_cards(*filter_values):
    filter_params = {}
    for (input_id, _url_key, _is_multi, _default), value in zip(
        FILTER_PARAMS, filter_values
    ):
        filter_params[input_id] = value

    cache_key = _normalize_filter_params(filter_params)
    children = _compute_dashboard_children(cache_key)

    return dbc.Row(children=children), filter_params


@callback(
    Output("download-observatoire", "data"),
    Input("btn-download-observatoire", "n_clicks"),
    State("observatoire-filters", "data"),
    State("observatoire-hidden-columns", "data"),
    prevent_initial_call=True,
)
def download_observatoire(_n_clicks, filter_params, hidden_columns):
    lff = prepare_dashboard_data(lff=query_marches().lazy(), **(filter_params or {}))

    if hidden_columns:
        lff = lff.drop(hidden_columns)

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
        if nom := lookup_nom(DF_ACHETEURS, "acheteur_id", "acheteur_nom", acheteur_id):
            return [
                NAME,
                html.Small(nom, className="text-muted d-block fw-normal fs-5"),
            ]
    elif titulaire_id and len(titulaire_id) == 14:
        if nom := lookup_nom(
            DF_TITULAIRES, "titulaire_id", "titulaire_nom", titulaire_id
        ):
            return [
                NAME,
                html.Small(nom, className="text-muted d-block fw-normal fs-5"),
            ]
    return NAME


@callback(
    Output("observatoire-preview", "is_open"),
    Input("btn-observatoire-preview", "n_clicks"),
    State("observatoire-preview", "is_open"),
    prevent_initial_call=True,
)
def toggle_observatoire_preview(n_clicks, is_open):
    return not is_open


@callback(
    Output("observatoire-preview-table", "data"),
    Output("observatoire-preview-table", "columns"),
    Output("observatoire-preview-table", "tooltip_header"),
    Output("observatoire-preview-table", "data_timestamp"),
    Output("nb_rows_observatoire", "children"),
    Output("btn-download-observatoire", "disabled"),
    Output("btn-download-observatoire", "children"),
    Output("btn-download-observatoire", "title"),
    Output("filter-cleanup-trigger-observatoire-preview", "data", allow_duplicate=True),
    Input("observatoire-preview", "is_open"),
    Input("observatoire-preview-table", "filter_query"),
    Input("observatoire-preview-table", "page_current"),
    Input("observatoire-preview-table", "page_size"),
    Input("observatoire-preview-table", "sort_by"),
    State("observatoire-preview-table", "data_timestamp"),
    State("observatoire-filters", "data"),
    prevent_initial_call=True,
)
def populate_preview_table(
    is_open,
    filter_query,
    page_current,
    page_size,
    sort_by,
    data_timestamp,
    filter_params,
):
    if not is_open:
        return (no_update,) * 9

    lff = prepare_dashboard_data(lff=query_marches().lazy(), **(filter_params or {}))

    return prepare_table_data(
        lff,
        data_timestamp,
        filter_query,
        page_current,
        page_size,
        sort_by,
        "observatoire-preview",
    )


@callback(
    Output("observatoire-hidden-columns", "data", allow_duplicate=True),
    Input("observatoire_preview_column_list", "selected_rows"),
    prevent_initial_call=True,
)
def update_hidden_columns_from_checkboxes(selected_columns):
    if selected_columns:
        selected_columns = [COLUMNS[i] for i in selected_columns]
        hidden_columns = [col for col in COLUMNS if col not in selected_columns]
        return hidden_columns
    else:
        return []


@callback(
    Output("observatoire-preview-table", "hidden_columns"),
    Input(
        "observatoire-hidden-columns",
        "data",
    ),
)
def store_hidden_columns(hidden_columns):
    return hidden_columns


@callback(
    Output("observatoire_preview_column_list", "selected_rows"),
    Input("observatoire-preview-table", "hidden_columns"),
    State(
        "observatoire_preview_column_list", "selected_rows"
    ),  # pour éviter la boucle infinie
)
def update_checkboxes_from_hidden_columns(hidden_cols, current_checkboxes):
    hidden_cols = hidden_cols or get_default_hidden_columns("tableau")

    # Show all columns that are NOT hidden
    visible_cols = [COLUMNS.index(col) for col in COLUMNS if col not in hidden_cols]
    return visible_cols


@callback(
    Output("observatoire-preview-columns-modal", "is_open"),
    Input("observatoire-preview-columns-open", "n_clicks"),
    Input("observatoire-preview-columns-close", "n_clicks"),
    State("observatoire-preview-columns-modal", "is_open"),
)
def toggle_tableau_columns(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open
