import datetime

import dash_bootstrap_components as dbc
import polars as pl
from dash import (
    Input,
    Output,
    State,
    callback,
    dcc,
    html,
    register_page,
)

from src.db import aggregate_marches, count_marches, query_marches, schema
from src.figures import (
    get_distance_histogram,
    get_org_location_map,
    get_top_org_ag_grid,
    make_card,
    make_column_picker,
)
from src.utils.data import DF_ACHETEURS, get_annuaire_data, get_departement_region
from src.utils.entity_grid import entity_scope, register_entity_grid_callbacks
from src.utils.frontend import DROPDOWN_LABELS_FR, get_button_properties
from src.utils.seo import META_CONTENT
from src.utils.table import (
    COLUMNS,
    format_number,
    get_default_hidden_columns,
    write_styled_excel,
)


def get_title(acheteur_id: str | None = None) -> str:
    acheteur_nom = DF_ACHETEURS.filter(pl.col("acheteur_id") == acheteur_id).select(
        "acheteur_nom"
    )
    if acheteur_nom.height > 0:
        return f"Marchés publics attribués par {acheteur_nom.item(0, 0)} | colibre"
    return "Marchés publics attribués | colibre"


def _acheteur_scope(pathname: str, ach_year: str | None) -> tuple[str, list]:
    """WHERE SQL scopant les requêtes à cet acheteur (et éventuellement une année)."""
    return entity_scope("acheteur", pathname.split("/")[-1], ach_year)


register_page(
    __name__,
    path_template="/acheteurs/<acheteur_id>",
    title=get_title,
    name="Acheteur",
    description="Consultez les marchés publics attribués par cet acheteur.",
    image_url=META_CONTENT["image_url"],
    order=5,
)


def layout(acheteur_id=None, **kwargs):
    return [
        dcc.Store(id="acheteur-hidden-columns", storage_type="local"),
        dcc.Store(id="acheteur-total"),
        dcc.Store(id="acheteur-total-unique"),
        dcc.Store(id="entity-grid-columns-state", storage_type="local"),
        dcc.Location(id="acheteur_url", refresh="callback-nav"),
        html.Div(
            children=[
                html.Div(
                    style={"marginBottom": "50px"},
                    children=[
                        dbc.Row(
                            className="mb-2",
                            children=[
                                dbc.Col(
                                    html.H2(
                                        children=[
                                            html.Span(id="acheteur_siret"),
                                            " - ",
                                            html.Span(id="acheteur_nom"),
                                        ],
                                    ),
                                    width=8,
                                ),
                                dbc.Col(
                                    dcc.Dropdown(
                                        id="acheteur_year",
                                        options=["Toutes les années"]
                                        + [
                                            str(year)
                                            for year in range(
                                                2018,
                                                int(datetime.date.today().year) + 1,
                                            )
                                        ],
                                        placeholder="Année",
                                        labels=DROPDOWN_LABELS_FR,
                                    ),
                                    width=4,
                                ),
                            ],
                        ),
                        dbc.Row(
                            className="mb-2",
                            children=[
                                dbc.Col(
                                    className="org_infos",
                                    children=[
                                        # TODO: ajouter le type d'acheteur : commune, CD, CR, etc.
                                        html.P(
                                            [
                                                "Commune : ",
                                                html.Strong(id="acheteur_commune"),
                                            ]
                                        ),
                                        html.P(
                                            [
                                                "Département : ",
                                                html.Strong(id="acheteur_departement"),
                                            ]
                                        ),
                                        html.P(
                                            [
                                                "Région : ",
                                                html.Strong(id="acheteur_region"),
                                            ]
                                        ),
                                        html.A(
                                            id="acheteur_lien_annuaire",
                                            children="Plus de détails sur l'Annuaire des entreprises",
                                        ),
                                    ],
                                    width=4,
                                ),
                                dbc.Col(
                                    children=[
                                        html.P(id="acheteur_titre_stats"),
                                        html.P(id="acheteur_marches_attribues"),
                                        html.P(id="acheteur_titulaires_differents"),
                                        html.Button(
                                            "Téléchargement au format Excel",
                                            id="btn-download-data-acheteur",
                                            className="btn btn-secondary",
                                        ),
                                        dcc.Download(id="download-data-acheteur"),
                                    ],
                                    width=4,
                                ),
                                dbc.Col(
                                    id="acheteur_map",
                                    width=4,
                                    style={"minHeight": "300px"},
                                ),
                            ],
                        ),
                        dbc.Row(
                            children=[
                                dbc.Col(
                                    className="marches_table",
                                    id="top10_titulaires",
                                    width=8,
                                    style={"minHeight": "420px"},
                                ),
                                dbc.Col(
                                    id="acheteur-distance-histogram",
                                    width=4,
                                    style={"minHeight": "450px"},
                                ),
                            ],
                        ),
                    ],
                ),
                # récupérer les données de l'acheteur sur l'api annuaire
                html.H3("Derniers marchés publics attribués"),
                dcc.Loading(
                    overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                    id="loading-home",
                    type="default",
                    children=[
                        html.Div(
                            [
                                dbc.Button(
                                    "Colonnes",
                                    id="acheteur_columns_open",
                                    color="secondary",
                                    size="sm",
                                    className="column_list",
                                ),
                                dbc.Button(
                                    "Téléchargement désactivé au-delà de 65 000 lignes",
                                    id="btn-download-filtered-data-acheteur",
                                    color="secondary",
                                    size="sm",
                                    disabled=True,
                                ),
                                dcc.Download(id="acheteur-download-filtered-data"),
                                dbc.Button(
                                    "Réinitialiser",
                                    title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                                    id="btn-acheteur-reset",
                                    color="danger",
                                    outline=True,
                                    size="sm",
                                ),
                            ],
                            className="table-toolbar",
                        ),
                        html.Div(
                            html.Span(id="acheteur_nb_rows"),
                            className="table-meta",
                        ),
                        dbc.Modal(
                            [
                                dbc.ModalHeader(
                                    dbc.ModalTitle("Choix des colonnes à afficher")
                                ),
                                dbc.ModalBody(
                                    id="acheteur_columns_body",
                                    children=make_column_picker("acheteur"),
                                ),
                                dbc.ModalFooter(
                                    dbc.Button(
                                        "Fermer",
                                        id="acheteur_columns_close",
                                        className="ms-auto",
                                        n_clicks=0,
                                    )
                                ),
                            ],
                            id="acheteur_columns",
                            is_open=False,
                            fullscreen="md-down",
                            scrollable=True,
                            size="xl",
                        ),
                        html.Div(
                            id="acheteur-grid-container", className="marches_table"
                        ),
                    ],
                ),
            ],
        ),
    ]


@callback(
    Output(component_id="acheteur_siret", component_property="children"),
    Output(component_id="acheteur_nom", component_property="children"),
    Output(component_id="acheteur_commune", component_property="children"),
    Output(component_id="acheteur_departement", component_property="children"),
    Output(component_id="acheteur_region", component_property="children"),
    Output(component_id="acheteur_lien_annuaire", component_property="href"),
    Input(component_id="acheteur_url", component_property="pathname"),
)
def update_acheteur_infos(url):
    acheteur_siret = url.split("/")[-1]
    data = get_annuaire_data(acheteur_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        code_departement, nom_departement, nom_region = get_departement_region(
            data_etablissement["code_postal"]
        )
        departement = f"{nom_departement} ({code_departement})"
        lien_annuaire = (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{acheteur_siret}"
        )
        raison_sociale = data["nom_raison_sociale"]
        libelle_commune = data_etablissement["libelle_commune"]

    else:
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = ""
        libelle_commune = ""

    return (
        acheteur_siret,
        raison_sociale,
        libelle_commune,
        departement,
        nom_region,
        lien_annuaire,
    )


@callback(
    Output(component_id="acheteur_map", component_property="children"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def update_acheteur_map(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    geo_columns = [
        col
        for col in [
            "uid",
            "acheteur_longitude",
            "acheteur_latitude",
            "acheteur_nom",
            "titulaire_longitude",
            "titulaire_latitude",
            "titulaire_nom",
        ]
        if col in schema.names()
    ]
    dff = query_marches(where_sql, params, columns=geo_columns)
    return get_org_location_map(dff, "acheteur", "acheteur_map_leaflet")


@callback(
    Output(component_id="acheteur_marches_attribues", component_property="children"),
    Output(
        component_id="acheteur_titulaires_differents", component_property="children"
    ),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def update_acheteur_stats(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    agg = aggregate_marches(
        "COUNT(*) AS n, COUNT(DISTINCT titulaire_id) AS nb_titulaires",
        where_sql,
        params,
    )
    nb_marches = format_number(int(agg["n"][0])) if agg.height else "0"
    nb_titulaires = format_number(int(agg["nb_titulaires"][0])) if agg.height else "0"

    marches_attribues = [html.Strong(nb_marches), " marchés et accord-cadres attribués"]
    nb_titulaires = [
        html.Strong(nb_titulaires),
        " titulaires (SIRET) différents",
    ]

    return marches_attribues, nb_titulaires


@callback(
    Output("btn-download-data-acheteur", "disabled"),
    Output("btn-download-data-acheteur", "children"),
    Output("btn-download-data-acheteur", "title"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def update_download_button_acheteur(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    return get_button_properties(count_marches(where_sql, params))


@callback(
    Output(component_id="top10_titulaires", component_property="children"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def get_top_titulaires(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    table = get_top_org_ag_grid(
        query_marches(where_sql, params).lazy(), "titulaire", ["titulaire_distance"]
    )
    return make_card(fig=table, title="Top titulaires", lg=12, xl=12)


@callback(
    Output("download-data-acheteur", "data"),
    Input("btn-download-data-acheteur", "n_clicks"),
    State(component_id="acheteur_url", component_property="pathname"),
    State(component_id="acheteur_year", component_property="value"),
    State(component_id="acheteur_nom", component_property="children"),
    prevent_initial_call=True,
)
def download_acheteur_data(
    n_clicks,
    pathname: str,
    annee: str,
    acheteur_nom: str,
):
    where_sql, params = _acheteur_scope(pathname, annee)
    df_to_download = query_marches(
        where_sql, params, order_by='"dateNotification" DESC, uid DESC'
    )

    def to_bytes(buffer):
        write_styled_excel(
            df_to_download,
            buffer,
            worksheet="DECP" if annee in ["Toutes les années", None] else annee,
        )

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{acheteur_nom}_{date}.xlsx")


@callback(
    Output("acheteur-hidden-columns", "data", allow_duplicate=True),
    Input("acheteur_column_list", "selected_rows"),
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
    Output("acheteur_column_list", "selected_rows"),
    Input("acheteur-hidden-columns", "data"),
    State("acheteur_column_list", "selected_rows"),  # pour éviter la boucle infinie
)
def update_checkboxes_from_hidden_columns(hidden_cols, current_checkboxes):
    hidden_cols = hidden_cols or get_default_hidden_columns("acheteur")

    # Show all columns that are NOT hidden
    visible_cols = [COLUMNS.index(col) for col in COLUMNS if col not in hidden_cols]
    return visible_cols


@callback(
    Output("acheteur_columns", "is_open"),
    Input("acheteur_columns_open", "n_clicks"),
    Input("acheteur_columns_close", "n_clicks"),
    State("acheteur_columns", "is_open"),
)
def toggle_acheteur_columns(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open


@callback(
    Output("acheteur-distance-histogram", "children"),
    Input("acheteur_url", "pathname"),
    Input("acheteur_year", "value"),
)
def update_acheteur_distance_histogram(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    lff = query_marches(where_sql, params).lazy()
    fig = get_distance_histogram(lff)
    return make_card(
        title="Distance acheteur–titulaire",
        subtitle="en nombre de marchés, échelle logarithmique",
        fig=fig,
        lg=12,
        xl=12,
    )


register_entity_grid_callbacks("acheteur")
