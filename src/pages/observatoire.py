import urllib.parse
from datetime import datetime

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
from src.utils import (
    data_schema,
    departements,
    df,
    df_acheteurs,
    df_titulaires,
    get_enum_values_as_dict,
    logger,
    meta_content,
    prepare_dashboard_data,
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

options_departements = []
for code in departements.keys():
    departement = {
        "label": f"{departements[code]['departement']} ({code})",
        "value": code,
    }
    options_departements.append(departement)

OBSERVATOIRE_COLUMNS = [
    col
    for col in df.columns
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
                                                options=options_departements,
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
                                                options=options_departements,
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
                                                    id="dashboard_marche_sousTraitanceDeclaree",
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
                                                id="dashboard_marche_considerationsSociales",
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
                                                id="dashboard_marche_considerationsEnvironnementales",
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
                                    dcc.Download(id="download-observatoire"),
                                    dbc.Button(
                                        "Prévisualiser les données",
                                        id="btn-observatoire-preview",
                                        className="mt-2",
                                        color="primary",
                                        outline=True,
                                    ),
                                    dcc.Input(
                                        id="observatoire-share-url",
                                        readOnly=True,
                                        style={"display": "none"},
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
                                    "Colonnes affichées",
                                    id="observatoire-preview-columns-open",
                                    size="sm",
                                    color="secondary",
                                    outline=True,
                                ),
                                dbc.Button(
                                    "Télécharger au format Excel",
                                    id="btn-download-observatoire",
                                    disabled=True,
                                    className="mt-2",
                                    color="primary",
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
                id="observatoire-preview-columns",
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
                    page_size=10,
                    page_action="native",
                    sort_action="native",
                    filter_action="native",
                    hidden_columns=[],
                    columns=[{"id": col, "name": col} for col in OBSERVATOIRE_COLUMNS],
                ),
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
    Output("dashboard_marche_objet", "value"),
    Output("dashboard_marche_code_cpv", "value"),
    Output("dashboard_montant_min", "value"),
    Output("dashboard_montant_max", "value"),
    Output("dashboard_marche_techniques", "value"),
    Output("dashboard_marche_innovant", "value"),
    Output("dashboard_marche_sousTraitanceDeclaree", "value"),
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
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
    return (no_update,) * 17


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
                style={"display": "none"},
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
    Input("dashboard_marche_objet", "value"),
    Input("dashboard_marche_code_cpv", "value"),
    Input("dashboard_montant_min", "value"),
    Input("dashboard_montant_max", "value"),
    Input("dashboard_marche_techniques", "value"),
    Input("dashboard_marche_innovant", "value"),
    Input("dashboard_marche_sousTraitanceDeclaree", "value"),
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
    dashboard_marche_objet,
    dashboard_marche_code_cpv,
    dashboard_montant_min,
    dashboard_montant_max,
    dashboard_marche_techniques,
    dashboard_marche_innovant,
    dashboard_marche_sous_traitance_declaree,
    dashboard_marche_considerations_sociales,
    dashboard_marche_considerations_environnementales,
):
    lff: pl.LazyFrame = df.lazy()

    columns = [
        "uid",
        cs.starts_with("acheteur"),
        cs.starts_with("titulaire"),
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

    if dashboard_marche_objet:
        columns.append("objet")

    lff = lff.select(columns)

    # Filtrage des données
    lff = prepare_dashboard_data(
        lff=lff,
        year=dashboard_year,
        acheteur_id=dashboard_acheteur_id,
        acheteur_categorie=dashboard_acheteur_categorie,
        acheteur_departement_code=dashboard_acheteur_departement_code,
        titulaire_id=dashboard_titulaire_id,
        titulaire_categorie=dashboard_titulaire_categorie,
        titulaire_departement_code=dashboard_titulaire_departement_code,
        type=dashboard_marche_type,
        objet=dashboard_marche_objet,
        code_cpv=dashboard_marche_code_cpv,
        considerations_sociales=dashboard_marche_considerations_sociales,
        considerations_environnementales=dashboard_marche_considerations_environnementales,
        montant_min=dashboard_montant_min,
        montant_max=dashboard_montant_max,
        techniques=dashboard_marche_techniques,
        marche_innovant=dashboard_marche_innovant,
        sous_traitance_declaree=dashboard_marche_sous_traitance_declaree,
    )

    # Génération des métriques
    dff = lff.collect(engine="streaming")

    logger.debug("Filter data: " + str(dff.height))

    df_per_uid = (
        dff.select("uid", "montant").group_by("uid").agg(pl.col("montant").first())
    )
    nb_marches = df_per_uid.height

    if nb_marches == 0:
        dl_disabled, dl_text = True, "Pas de données à télécharger"
    elif nb_marches > 65000:
        dl_disabled, dl_text = True, "Téléchargement désactivé au-delà de 65 000 lignes"
    else:
        dl_disabled, dl_text = False, "Télécharger au format Excel"

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
    State("dashboard_marche_objet", "value"),
    State("dashboard_marche_code_cpv", "value"),
    State("dashboard_montant_min", "value"),
    State("dashboard_montant_max", "value"),
    State("dashboard_marche_techniques", "value"),
    State("dashboard_marche_innovant", "value"),
    State("dashboard_marche_sousTraitanceDeclaree", "value"),
    State("dashboard_marche_considerationsSociales", "value"),
    State("dashboard_marche_considerationsEnvironnementales", "value"),
    prevent_initial_call=True,
)
def download_observatoire(
    _n_clicks,
    dashboard_year,
    dashboard_acheteur_id,
    dashboard_acheteur_categorie,
    dashboard_acheteur_departement_code,
    dashboard_titulaire_id,
    dashboard_titulaire_categorie,
    dashboard_titulaire_departement_code,
    dashboard_marche_type,
    dashboard_marche_objet,
    dashboard_marche_code_cpv,
    dashboard_montant_min,
    dashboard_montant_max,
    dashboard_marche_techniques,
    dashboard_marche_innovant,
    dashboard_marche_sous_traitance_declaree,
    dashboard_considerations_sociales,
    dashboard_considerations_environnementales,
):
    lff = prepare_dashboard_data(
        lff=df.lazy(),
        year=dashboard_year,
        acheteur_id=dashboard_acheteur_id,
        acheteur_categorie=dashboard_acheteur_categorie,
        acheteur_departement_code=dashboard_acheteur_departement_code,
        titulaire_id=dashboard_titulaire_id,
        titulaire_categorie=dashboard_titulaire_categorie,
        titulaire_departement_code=dashboard_titulaire_departement_code,
        type=dashboard_marche_type,
        objet=dashboard_marche_objet,
        code_cpv=dashboard_marche_code_cpv,
        considerations_sociales=dashboard_considerations_sociales,
        considerations_environnementales=dashboard_considerations_environnementales,
        montant_min=dashboard_montant_min,
        montant_max=dashboard_montant_max,
        techniques=dashboard_marche_techniques,
        marche_innovant=dashboard_marche_innovant,
        sous_traitance_declaree=dashboard_marche_sous_traitance_declaree,
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
    Input("observatoire-preview", "is_open"),
    State("dashboard_year", "value"),
    State("dashboard_acheteur_id", "value"),
    State("dashboard_acheteur_categorie", "value"),
    State("dashboard_acheteur_departement_code", "value"),
    State("dashboard_titulaire_id", "value"),
    State("dashboard_titulaire_categorie", "value"),
    State("dashboard_titulaire_departement_code", "value"),
    State("dashboard_marche_type", "value"),
    State("dashboard_marche_objet", "value"),
    State("dashboard_marche_code_cpv", "value"),
    State("dashboard_montant_min", "value"),
    State("dashboard_montant_max", "value"),
    State("dashboard_marche_techniques", "value"),
    State("dashboard_marche_innovant", "value"),
    State("dashboard_marche_sousTraitanceDeclaree", "value"),
    State("dashboard_marche_considerationsSociales", "value"),
    State("dashboard_marche_considerationsEnvironnementales", "value"),
    prevent_initial_call=True,
)
def populate_preview_table(
    is_open,
    dashboard_year,
    dashboard_acheteur_id,
    dashboard_acheteur_categorie,
    dashboard_acheteur_departement_code,
    dashboard_titulaire_id,
    dashboard_titulaire_categorie,
    dashboard_titulaire_departement_code,
    dashboard_marche_type,
    dashboard_marche_objet,
    dashboard_marche_code_cpv,
    dashboard_montant_min,
    dashboard_montant_max,
    dashboard_marche_techniques,
    dashboard_marche_innovant,
    dashboard_marche_sous_traitance_declaree,
    dashboard_marche_considerations_sociales,
    dashboard_marche_considerations_environnementales,
):
    if not is_open:
        return no_update, no_update

    available_in_df = [col for col in OBSERVATOIRE_COLUMNS if col in df.columns]
    lff = prepare_dashboard_data(
        lff=df.lazy().select(available_in_df),
        year=dashboard_year,
        acheteur_id=dashboard_acheteur_id,
        acheteur_categorie=dashboard_acheteur_categorie,
        acheteur_departement_code=dashboard_acheteur_departement_code,
        titulaire_id=dashboard_titulaire_id,
        titulaire_categorie=dashboard_titulaire_categorie,
        titulaire_departement_code=dashboard_titulaire_departement_code,
        type=dashboard_marche_type,
        objet=dashboard_marche_objet,
        code_cpv=dashboard_marche_code_cpv,
        considerations_sociales=dashboard_marche_considerations_sociales,
        considerations_environnementales=dashboard_marche_considerations_environnementales,
        montant_min=dashboard_montant_min,
        montant_max=dashboard_montant_max,
        techniques=dashboard_marche_techniques,
        marche_innovant=dashboard_marche_innovant,
        sous_traitance_declaree=dashboard_marche_sous_traitance_declaree,
    )

    dff = lff.collect(engine="streaming")

    table_data = dff.to_dicts()
    table_columns = [
        {
            "name": data_schema.get(col, {}).get("title", col),
            "id": col,
            "type": "text",
            "format": {"nully": "N/A"},
        }
        for col in available_in_df
    ]
    return table_data, table_columns
