import datetime

import dash_bootstrap_components as dbc
import polars as pl
from dash import (
    ClientsideFunction,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    dcc,
    html,
    register_page,
)

from src.db import aggregate_marches, count_marches, query_marches, schema
from src.figures import (
    DataTable,
    get_distance_histogram,
    get_org_location_map,
    get_top_org_table,
    make_column_picker,
)
from src.utils.data import DF_TITULAIRES, get_annuaire_data, get_departement_region
from src.utils.frontend import get_button_properties
from src.utils.seo import META_CONTENT
from src.utils.table import (
    COLUMNS,
    filter_table_data,
    format_number,
    get_default_hidden_columns,
    prepare_table_data,
    sort_table_data,
    write_styled_excel,
)
from src.utils.tracking import track_search


def get_title(titulaire_id: str = None) -> str:
    titulaire_nom = DF_TITULAIRES.filter(pl.col("titulaire_id") == titulaire_id).select(
        "titulaire_nom"
    )
    if titulaire_nom.height > 0:
        return f"Marchés publics remportés par {titulaire_nom.item(0, 0)} | colibre"
    return "Marchés publics remportés | colibre"


def _titulaire_scope(pathname: str, titulaire_year: str | None) -> tuple[str, list]:
    """WHERE SQL scopant les requêtes à ce titulaire (et éventuellement une année)."""
    titulaire_siret = pathname.split("/")[-1]
    where_sql = "titulaire_id = ? AND titulaire_typeIdentifiant = 'SIRET'"
    params: list = [titulaire_siret]
    if titulaire_year and titulaire_year != "Toutes les années":
        where_sql += ' AND YEAR("dateNotification") = ?'
        params.append(int(titulaire_year))
    return where_sql, params


register_page(
    __name__,
    path_template="/titulaires/<titulaire_id>",
    title=get_title,
    name="Titulaire",
    description="Consultez les marchés publics remportés par ce titulaire.",
    image_url=META_CONTENT["image_url"],
    order=5,
)

DATATABLE = html.Div(
    className="marches_table",
    children=DataTable(
        dtid="titulaire_datatable",
        persistence=True,
        persistence_type="local",
        persisted_props=["filter_query", "sort_by"],
        page_action="custom",
        filter_action="custom",
        sort_action="custom",
        page_size=10,
        hidden_columns=[],
        columns=[{"id": col, "name": col} for col in schema.names()],
    ),
)

layout = [
    dcc.Store(id="titulaire-hidden-columns", storage_type="local"),
    dcc.Store(id="filter-cleanup-trigger-titulaire"),
    dcc.Location(id="titulaire_url", refresh="callback-nav"),
    html.Div(
        children=[
            html.Div(
                style={"marginBottom": "50px"},
                children=[
                    dbc.Row(
                        className="mb-2",
                        children=[
                            dbc.Col(
                                [
                                    html.H2(
                                        children=[
                                            html.Span(id="titulaire_siret"),
                                            " - ",
                                            html.Span(id="titulaire_nom"),
                                        ],
                                    ),
                                    html.P(
                                        id="titulaire_activite_libelle",
                                        style={"color": "gray", "marginTop": "-10px"},
                                    ),
                                ],
                                width=8,
                            ),
                            dbc.Col(
                                dcc.Dropdown(
                                    id="titulaire_year",
                                    options=["Toutes les années"]
                                    + [
                                        str(year)
                                        for year in range(
                                            2018, int(datetime.date.today().year) + 1
                                        )
                                    ],
                                    placeholder="Année",
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
                                            html.Strong(id="titulaire_commune"),
                                        ]
                                    ),
                                    html.P(
                                        [
                                            "Département : ",
                                            html.Strong(id="titulaire_departement"),
                                        ]
                                    ),
                                    html.P(
                                        [
                                            "Région : ",
                                            html.Strong(id="titulaire_region"),
                                        ]
                                    ),
                                    html.A(
                                        id="titulaire_lien_annuaire",
                                        children="Plus de détails sur l'Annuaire des entreprises",
                                    ),
                                ],
                                width=4,
                            ),
                            dbc.Col(
                                children=[
                                    html.P(id="titulaire_titre_stats"),
                                    html.P(id="titulaire_marches_remportes"),
                                    html.P(id="titulaire_acheteurs_differents"),
                                    html.Button(
                                        "Téléchargement au format Excel",
                                        id="btn-download-data-titulaire",
                                        className="btn btn-primary",
                                    ),
                                    dcc.Download(id="download-data-titulaire"),
                                ],
                                width=4,
                            ),
                            dbc.Col(
                                id="titulaire_map",
                                width=4,
                                style={"minHeight": "300px"},
                            ),
                        ],
                    ),
                    dbc.Row(
                        children=[
                            dbc.Col(
                                html.Div(
                                    children=[
                                        html.H3("Top acheteurs"),
                                        html.Div(
                                            className="marches_table",
                                            id="top10_acheteurs",
                                            style={"minHeight": "420px"},
                                        ),
                                    ],
                                ),
                                width=8,
                            ),
                            dbc.Col(
                                id="titulaire-distance-histogram",
                                width=4,
                                style={"minHeight": "450px"},
                            ),
                        ],
                    ),
                ],
            ),
            # récupérer les données de l'acheteur sur l'api annuaire
            html.H3("Derniers marchés publics remportés"),
            dcc.Loading(
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                id="loading-home",
                type="default",
                children=[
                    html.Div(
                        [
                            dbc.Button(
                                "Colonnes",
                                id="titulaire_columns_open",
                                color="secondary",
                                size="sm",
                                className="column_list",
                            ),
                            dbc.Button(
                                "Téléchargement désactivé au-delà de 65 000 lignes",
                                id="btn-download-filtered-data-titulaire",
                                color="secondary",
                                size="sm",
                                disabled=True,
                            ),
                            dcc.Download(id="titulaire-download-filtered-data"),
                            dbc.Button(
                                "Réinitialiser",
                                title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                                id="btn-titulaire-reset",
                                color="danger",
                                outline=True,
                                size="sm",
                            ),
                        ],
                        className="table-toolbar",
                    ),
                    html.Div(
                        html.Span(id="titulaire_nb_rows"),
                        className="table-meta",
                    ),
                    dbc.Modal(
                        [
                            dbc.ModalHeader(
                                dbc.ModalTitle("Choix des colonnes à afficher")
                            ),
                            dbc.ModalBody(
                                id="titulaire_columns_body",
                                children=make_column_picker("titulaire"),
                            ),
                            dbc.ModalFooter(
                                dbc.Button(
                                    "Fermer",
                                    id="titulaire_columns_close",
                                    className="ms-auto",
                                    n_clicks=0,
                                )
                            ),
                        ],
                        id="titulaire_columns",
                        is_open=False,
                        fullscreen="md-down",
                        scrollable=True,
                        size="xl",
                    ),
                    DATATABLE,
                ],
            ),
        ],
    ),
]


@callback(
    Output(component_id="titulaire_siret", component_property="children"),
    Output(component_id="titulaire_nom", component_property="children"),
    Output(component_id="titulaire_commune", component_property="children"),
    Output(component_id="titulaire_departement", component_property="children"),
    Output(component_id="titulaire_region", component_property="children"),
    Output(component_id="titulaire_lien_annuaire", component_property="href"),
    Output(component_id="titulaire_activite_libelle", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
)
def update_titulaire_infos(url):
    titulaire_siret = url.split("/")[-1]
    if "titulaire_activite_libelle" in DF_TITULAIRES.columns:
        activite_libelle_row = DF_TITULAIRES.filter(
            pl.col("titulaire_id") == titulaire_siret
        ).select("titulaire_activite_libelle")
        activite_libelle = (
            activite_libelle_row.item(0, 0) if activite_libelle_row.height > 0 else ""
        )
    else:
        activite_libelle = ""
    data = get_annuaire_data(titulaire_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        code_departement, nom_departement, nom_region = get_departement_region(
            data_etablissement["code_postal"]
        )
        departement = f"{nom_departement} ({code_departement})"
        lien_annuaire = (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{titulaire_siret}"
        )
        raison_sociale = data["nom_raison_sociale"]
        libelle_commune = data_etablissement["libelle_commune"]

    else:
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = html.Span(
            f"N° SIREN inconnu de l'INSEE ({titulaire_siret[:9]})"
        )
        libelle_commune = ""

    return (
        titulaire_siret,
        raison_sociale,
        libelle_commune,
        departement,
        nom_region,
        lien_annuaire,
        activite_libelle,
    )


@callback(
    Output(component_id="titulaire_map", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def update_titulaire_map(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
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
    return get_org_location_map(dff, "titulaire", "titulaire_map_leaflet")


@callback(
    Output(component_id="titulaire_marches_remportes", component_property="children"),
    Output(
        component_id="titulaire_acheteurs_differents", component_property="children"
    ),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def update_titulaire_stats(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    agg = aggregate_marches(
        "COUNT(DISTINCT uid) AS n, COUNT(DISTINCT acheteur_id) AS nb_acheteurs",
        where_sql,
        params,
    )
    nb_marches = format_number(int(agg["n"][0])) if agg.height else "0"
    nb_acheteurs = format_number(int(agg["nb_acheteurs"][0])) if agg.height else "0"

    texte_marches_remportes = [
        html.Strong(nb_marches),
        " marchés et accord-cadres remportés",
    ]
    texte_nb_acheteurs = [
        html.Strong(nb_acheteurs),
        " acheteurs (SIRET) différents",
    ]

    return texte_marches_remportes, texte_nb_acheteurs


@callback(
    Output("btn-download-data-titulaire", "disabled"),
    Output("btn-download-data-titulaire", "children"),
    Output("btn-download-data-titulaire", "title"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def update_download_button_titulaire(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    return get_button_properties(count_marches(where_sql, params))


@callback(
    Output("titulaire_datatable", "data"),
    Output("titulaire_datatable", "columns"),
    Output("titulaire_datatable", "tooltip_header"),
    Output("titulaire_datatable", "data_timestamp"),
    Output("titulaire_nb_rows", "children"),
    Output("btn-download-filtered-data-titulaire", "disabled"),
    Output("btn-download-filtered-data-titulaire", "children"),
    Output("btn-download-filtered-data-titulaire", "title"),
    Output("filter-cleanup-trigger-titulaire", "data"),
    Input("titulaire_url", "pathname"),
    Input("titulaire_year", "value"),
    Input("titulaire_datatable", "page_current"),
    Input("titulaire_datatable", "page_size"),
    Input("titulaire_datatable", "filter_query"),
    Input("titulaire_datatable", "sort_by"),
    State("titulaire_datatable", "data_timestamp"),
)
def get_last_marches_data(
    pathname,
    titulaire_year,
    page_current,
    page_size,
    filter_query,
    sort_by,
    data_timestamp,
) -> list[dict]:
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    return prepare_table_data(
        None,
        data_timestamp,
        filter_query,
        page_current,
        page_size,
        sort_by,
        "titulaire",
        base_where_sql=where_sql,
        base_params=params,
    )


@callback(
    Output(component_id="top10_acheteurs", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def get_top_acheteurs(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    return get_top_org_table(
        query_marches(where_sql, params).lazy(), "acheteur", ["titulaire_distance"]
    )


@callback(
    Output("download-data-titulaire", "data"),
    Input("btn-download-data-titulaire", "n_clicks"),
    State(component_id="titulaire_url", component_property="pathname"),
    State(component_id="titulaire_year", component_property="value"),
    State(component_id="titulaire_nom", component_property="children"),
    prevent_initial_call=True,
)
def download_titulaire_data(
    n_clicks,
    pathname: str,
    annee: str,
    titulaire_nom: str,
):
    where_sql, params = _titulaire_scope(pathname, annee)
    df_to_download = query_marches(
        where_sql, params, order_by='"dateNotification" DESC, uid DESC'
    ).fill_null("")

    def to_bytes(buffer):
        write_styled_excel(
            df_to_download,
            buffer,
            worksheet="DECP" if annee in ["Toutes les années", None] else annee,
        )

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{titulaire_nom}_{date}.xlsx")


@callback(
    Output("titulaire-download-filtered-data", "data"),
    Input("btn-download-filtered-data-titulaire", "n_clicks"),
    State("titulaire_url", "pathname"),
    State("titulaire_year", "value"),
    State("titulaire_nom", "children"),
    State("titulaire_datatable", "filter_query"),
    State("titulaire_datatable", "sort_by"),
    State("titulaire_datatable", "hidden_columns"),
    prevent_initial_call=True,
)
def download_filtered_titulaire_data(
    n_clicks,
    pathname,
    titulaire_year,
    titulaire_nom,
    filter_query,
    sort_by,
    hidden_columns: list | None = None,
):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    lff: pl.LazyFrame = query_marches(where_sql, params).lazy()

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        track_search(filter_query, "titu download")
        lff = filter_table_data(lff, filter_query)

    if len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    def to_bytes(buffer):
        write_styled_excel(lff.collect(engine="streaming"), buffer)

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(
        to_bytes, filename=f"decp_filtrées_{titulaire_nom}_{date}.xlsx"
    )


# Pour nettoyer les icontains et i< des filtres
# voir aussi src/assets/dash_clientside.js
clientside_callback(
    ClientsideFunction(
        namespace="clientside",
        function_name="clean_filters",
    ),
    Output("filter-cleanup-trigger-titulaire", "data", allow_duplicate=True),
    Input("filter-cleanup-trigger-titulaire", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("titulaire-hidden-columns", "data", allow_duplicate=True),
    Input("titulaire_column_list", "selected_rows"),
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
    Output("titulaire_datatable", "hidden_columns"),
    Input(
        "titulaire-hidden-columns",
        "data",
    ),
)
def store_hidden_columns(hidden_columns):
    if hidden_columns is None:
        hidden_columns = get_default_hidden_columns("titulaire")
    return hidden_columns


@callback(
    Output("titulaire_column_list", "selected_rows"),
    Input("titulaire_datatable", "hidden_columns"),
    State("titulaire_column_list", "selected_rows"),  # pour éviter la boucle infinie
)
def update_checkboxes_from_hidden_columns(hidden_cols, current_checkboxes):
    hidden_cols = hidden_cols or get_default_hidden_columns("titulaire")

    # Show all columns that are NOT hidden
    visible_cols = [COLUMNS.index(col) for col in COLUMNS if col not in hidden_cols]
    return visible_cols


@callback(
    Output("titulaire_columns", "is_open"),
    Input("titulaire_columns_open", "n_clicks"),
    Input("titulaire_columns_close", "n_clicks"),
    State("titulaire_columns", "is_open"),
)
def toggle_titulaire_columns(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open


@callback(
    Output("titulaire_datatable", "filter_query", allow_duplicate=True),
    Output("titulaire_datatable", "sort_by"),
    Input("btn-titulaire-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_view(n_clicks):
    return "", []


@callback(
    Output("titulaire-distance-histogram", "children"),
    Input("titulaire_url", "pathname"),
    Input("titulaire_year", "value"),
)
def update_titulaire_distance_histogram(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    lff = query_marches(where_sql, params).lazy()
    if "titulaire_distance" in lff.collect_schema().names():
        lff = lff.with_columns(
            pl.col("titulaire_distance").cast(pl.Float64, strict=False)
        )
    fig = get_distance_histogram(lff)
    return [
        html.H3("Distance acheteur-titulaire"),
        html.H6("par nombre de marchés", className="card-subtitle mb-2 text-muted"),
        fig,
    ]
