import datetime
from typing import Any

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

from src.callbacks import get_top_org_table
from src.figures import DataTable, make_column_picker, point_on_map
from src.utils import (
    columns,
    df,
    df_titulaires,
    filter_table_data,
    format_number,
    get_annuaire_data,
    get_button_properties,
    get_default_hidden_columns,
    get_departement_region,
    meta_content,
    prepare_table_data,
    sort_table_data,
)


def get_title(titulaire_id: str = None) -> str:
    titulaire_nom = df_titulaires.filter(pl.col("titulaire_id") == titulaire_id).select(
        "titulaire_nom"
    )
    if titulaire_nom.height > 0:
        return f"Marchés publics remportés par {titulaire_nom.item(0, 0)} | decp.info"
    return "Marchés publics remportés | decp.info"


register_page(
    __name__,
    path_template="/titulaires/<titulaire_id>",
    title=get_title,
    name="Titulaire",
    description="Consultez les marchés publics remportés par ce titulaire.",
    image_url=meta_content["image_url"],
    order=5,
)

datatable = html.Div(
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
        columns=[{"id": col, "name": col} for col in df.columns],
    ),
)

layout = [
    dcc.Store(id="titulaire_data", storage_type="memory"),
    dcc.Store(id="titulaire-hidden-columns", storage_type="local"),
    dcc.Store(id="filter-cleanup-trigger-titulaire"),
    dcc.Location(id="titulaire_url", refresh="callback-nav"),
    html.Div(
        children=[
            html.Div(
                className="wrapper",
                children=[
                    html.H2(
                        className="org_title",
                        children=[
                            html.Span(id="titulaire_siret"),
                            " - ",
                            html.Span(id="titulaire_nom"),
                        ],
                    ),
                    html.Div(
                        className="org_year",
                        children=dcc.Dropdown(
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
                    ),
                    html.Div(
                        className="org_infos",
                        children=[
                            # TODO: ajouter le type d'acheteur : commune, CD, CR, etc.
                            html.P(["Commune : ", html.Strong(id="titulaire_commune")]),
                            html.P(
                                [
                                    "Département : ",
                                    html.Strong(id="titulaire_departement"),
                                ]
                            ),
                            html.P(["Région : ", html.Strong(id="titulaire_region")]),
                            html.A(
                                id="titulaire_lien_annuaire",
                                children="Plus de détails sur l'Annuaire des entreprises",
                            ),
                        ],
                    ),
                    html.Div(
                        className="org_stats",
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
                    ),
                    html.Div(className="org_map", id="titulaire_map"),
                    html.Div(
                        className="org_top",
                        children=[
                            html.H3("Top acheteurs"),
                            html.Div(className="marches_table", id="top10_acheteurs"),
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
                            # Bouton modal des colonnes affichées
                            dbc.Button(
                                "Colonnes affichées",
                                id="titulaire_columns_open",
                                className="column_list",
                            ),
                            html.P("lignes", id="titulaire_nb_rows"),
                            html.Button(
                                "Téléchargement désactivé au-delà de 65 000 lignes",
                                id="btn-download-filtered-data-titulaire",
                                disabled=True,
                                className="btn btn-primary",
                            ),
                            dcc.Download(id="titulaire-download-filtered-data"),
                            dbc.Button(
                                "Remise à zéro",
                                title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                                id="btn-titulaire-reset",
                                className="btn btn-primary",
                            ),
                        ],
                        className="table-menu",
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
                    datatable,
                ],
            ),
        ],
    ),
]


@callback(
    Output(component_id="titulaire_siret", component_property="children"),
    Output(component_id="titulaire_nom", component_property="children"),
    Output(component_id="titulaire_commune", component_property="children"),
    Output(component_id="titulaire_map", component_property="children"),
    Output(component_id="titulaire_departement", component_property="children"),
    Output(component_id="titulaire_region", component_property="children"),
    Output(component_id="titulaire_lien_annuaire", component_property="href"),
    Input(component_id="titulaire_url", component_property="pathname"),
)
def update_titulaire_infos(url):
    titulaire_siret = url.split("/")[-1]
    data = get_annuaire_data(titulaire_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        titulaire_map = point_on_map(
            data_etablissement["latitude"], data_etablissement["longitude"]
        )
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
        titulaire_map = html.Div()
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
        titulaire_map,
        departement,
        nom_region,
        lien_annuaire,
    )


@callback(
    Output(component_id="titulaire_marches_remportes", component_property="children"),
    Output(
        component_id="titulaire_acheteurs_differents", component_property="children"
    ),
    Input(component_id="titulaire_data", component_property="data"),
)
def update_titulaire_stats(data):
    dff = pl.DataFrame(data, strict=False, infer_schema_length=5000)
    if dff.height == 0:
        nb_marches = 0
        nb_acheteurs = 0
    else:
        df_marches = dff.unique("uid")
        nb_marches = format_number(df_marches.height)
        nb_acheteurs = dff.unique("acheteur_id").height

    texte_marches_remportes = [
        html.Strong(nb_marches),
        " marchés et accord-cadres remportés",
    ]
    # + ", pour un total de ", html.Strong(somme_marches + " €")]

    texte_nb_acheteurs = [
        html.Strong(format_number(nb_acheteurs)),
        " acheteurs (SIRET) différents",
    ]

    return texte_marches_remportes, texte_nb_acheteurs


@callback(
    Output(component_id="titulaire_data", component_property="data"),
    Output("btn-download-data-titulaire", "disabled"),
    Output("btn-download-data-titulaire", "children"),
    Output("btn-download-data-titulaire", "title"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def get_titulaire_marches_data(url, titulaire_year: str) -> tuple:
    titulaire_siret = url.split("/")[-1]
    lff = df.lazy()
    lff = lff.filter(
        (pl.col("titulaire_id") == titulaire_siret)
        & (pl.col("titulaire_typeIdentifiant") == "SIRET")
    )
    if titulaire_year and titulaire_year != "Toutes les années":
        lff = lff.filter(
            pl.col("dateNotification").cast(pl.String).str.starts_with(titulaire_year)
        )
    lff = lff.sort(["dateNotification", "uid"], descending=True, nulls_last=True)
    lff = lff.fill_null("")

    dff: pl.DataFrame = lff.collect(engine="streaming")
    download_disabled, download_text, download_title = get_button_properties(dff.height)

    data = dff.to_dicts()
    return data, download_disabled, download_text, download_title


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
    Input(component_id="titulaire_url", component_property="href"),
    Input("titulaire_data", "data"),
    Input("titulaire_datatable", "page_current"),
    Input("titulaire_datatable", "page_size"),
    Input("titulaire_datatable", "filter_query"),
    Input("titulaire_datatable", "sort_by"),
    State("titulaire_datatable", "data_timestamp"),
)
def get_last_marches_data(
    href, data, page_current, page_size, filter_query, sort_by, data_timestamp
) -> list[dict]:
    return prepare_table_data(
        data,
        data_timestamp,
        filter_query,
        page_current,
        page_size,
        sort_by,
        "titulaire",
    )


@callback(
    Output(component_id="top10_acheteurs", component_property="children"),
    Input(component_id="titulaire_data", component_property="data"),
)
def get_top_acheteurs(data):
    return get_top_org_table(data, "acheteur")


@callback(
    Output("download-data-titulaire", "data"),
    Input("btn-download-data-titulaire", "n_clicks"),
    State(component_id="titulaire_data", component_property="data"),
    State(component_id="titulaire_nom", component_property="children"),
    State(component_id="titulaire_year", component_property="value"),
    prevent_initial_call=True,
)
def download_titulaire_data(
    n_clicks,
    data: list[dict[str, Any]],
    titulaire_nom: str,
    annee: str,
):
    df_to_download = pl.DataFrame(data)

    def to_bytes(buffer):
        df_to_download.write_excel(
            buffer, worksheet="DECP" if annee in ["Toutes les années", None] else annee
        )

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{titulaire_nom}_{date}.xlsx")


@callback(
    Output("titulaire-download-filtered-data", "data"),
    State("titulaire_data", "data"),
    Input("btn-download-filtered-data-titulaire", "n_clicks"),
    State("titulaire_nom", "children"),
    State("titulaire_datatable", "filter_query"),
    State("titulaire_datatable", "sort_by"),
    State("titulaire_datatable", "hidden_columns"),
    prevent_initial_call=True,
)
def download_filtered_titulaire_data(
    data, n_clicks, titulaire_nom, filter_query, sort_by, hidden_columns: list = None
):
    lff: pl.LazyFrame = pl.LazyFrame(
        data
    )  # start from the full titulaire data, not from paginated table data

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        lff = filter_table_data(lff, filter_query, "titu download")

    if len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    def to_bytes(buffer):
        lff.collect(engine="streaming").write_excel(buffer, worksheet="DECP")

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
        selected_columns = [columns[i] for i in selected_columns]
        hidden_columns = [col for col in columns if col not in selected_columns]
        return hidden_columns
    else:
        return []


@callback(
    Output("titulaire_datatable", "hidden_columns", allow_duplicate=True),
    Input(
        "titulaire-hidden-columns",
        "data",
    ),
    prevent_initial_call=True,
)
def store_hidden_columns(hidden_columns):
    return hidden_columns


@callback(
    Output("titulaire_column_list", "selected_rows"),
    Input("titulaire_datatable", "hidden_columns"),
    State("titulaire_column_list", "selected_rows"),  # pour éviter la boucle infinie
)
def update_checkboxes_from_hidden_columns(hidden_cols, current_checkboxes):
    hidden_cols = hidden_cols or get_default_hidden_columns("titulaire")

    # Show all columns that are NOT hidden
    visible_cols = [columns.index(col) for col in columns if col not in hidden_cols]
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
