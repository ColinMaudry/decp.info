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

from src.callbacks import get_top_org_table
from src.figures import DataTable, make_column_picker, point_on_map
from src.utils import (
    add_canonical_link,
    columns,
    df,
    df_acheteurs,
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


def get_title(acheteur_id: str = None) -> str:
    acheteur_nom = df_acheteurs.filter(pl.col("acheteur_id") == acheteur_id).select(
        "acheteur_nom"
    )
    if acheteur_nom.height > 0:
        return f"Marchés publics attribués par {acheteur_nom.item(0, 0)} | decp.info"
    return "Marchés publics attribués | decp.info"


register_page(
    __name__,
    path_template="/acheteurs/<acheteur_id>",
    title=get_title,
    name="Acheteur",
    description="Consultez les marchés publics attribués par cet acheteur.",
    image_url=meta_content["image_url"],
    order=5,
)

datatable = html.Div(
    className="marches_table",
    children=DataTable(
        dtid="acheteur_datatable",
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
    dcc.Store(id="acheteur_data", storage_type="memory"),
    dcc.Store(id="acheteur-hidden-columns", storage_type="local"),
    dcc.Store(id="filter-cleanup-trigger-acheteur"),
    dcc.Location(id="acheteur_url", refresh="callback-nav"),
    html.Div(
        children=[
            html.Div(
                className="wrapper",
                children=[
                    html.H2(
                        className="org_title",
                        children=[
                            html.Span(id="acheteur_siret"),
                            " - ",
                            html.Span(id="acheteur_nom"),
                        ],
                    ),
                    html.Div(
                        className="org_year",
                        children=dcc.Dropdown(
                            id="acheteur_year",
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
                            html.P(["Commune : ", html.Strong(id="acheteur_commune")]),
                            html.P(
                                [
                                    "Département : ",
                                    html.Strong(id="acheteur_departement"),
                                ]
                            ),
                            html.P(["Région : ", html.Strong(id="acheteur_region")]),
                            html.A(
                                id="acheteur_lien_annuaire",
                                children="Plus de détails sur l'Annuaire des entreprises",
                            ),
                        ],
                    ),
                    html.Div(
                        className="org_stats",
                        children=[
                            html.P(id="acheteur_titre_stats"),
                            html.P(id="acheteur_marches_attribues"),
                            html.P(id="acheteur_titulaires_differents"),
                            html.Button(
                                "Téléchargement au format Excel",
                                id="btn-download-data-acheteur",
                                className="btn btn-primary",
                            ),
                            dcc.Download(id="download-data-acheteur"),
                        ],
                    ),
                    html.Div(className="org_map", id="acheteur_map"),
                    html.Div(
                        className="org_top",
                        children=[
                            html.H3("Top titulaires"),
                            html.Div(className="marches_table", id="top10_titulaires"),
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
                            # Bouton modal des colonnes affichées
                            dbc.Button(
                                "Colonnes affichées",
                                id="acheteur_columns_open",
                                className="column_list",
                            ),
                            html.P("lignes", id="acheteur_nb_rows"),
                            html.Button(
                                "Téléchargement désactivé au-delà de 65 000 lignes",
                                id="btn-download-filtered-data-acheteur",
                                className="btn btn-primary",
                                disabled=True,
                            ),
                            dcc.Download(id="acheteur-download-filtered-data"),
                            dbc.Button(
                                "Remise à zéro",
                                title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                                id="btn-acheteur-reset",
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
                    datatable,
                ],
            ),
        ],
    ),
]


@callback(
    Output(component_id="acheteur_siret", component_property="children"),
    Output(component_id="acheteur_nom", component_property="children"),
    Output(component_id="acheteur_commune", component_property="children"),
    Output(component_id="acheteur_map", component_property="children"),
    Output(component_id="acheteur_departement", component_property="children"),
    Output(component_id="acheteur_region", component_property="children"),
    Output(component_id="acheteur_lien_annuaire", component_property="href"),
    Input(component_id="acheteur_url", component_property="pathname"),
)
def update_acheteur_infos(url):
    acheteur_siret = url.split("/")[-1]
    # if len(acheteur_siret) != 14:
    #     acheteur_siret = (
    #         f"Le SIRET renseigné doit faire 14 caractères ({acheteur_siret})"
    #     )
    data = get_annuaire_data(acheteur_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        acheteur_map = point_on_map(
            data_etablissement["latitude"], data_etablissement["longitude"]
        )
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
        acheteur_map = html.Div()
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = ""
        libelle_commune = ""

    return (
        acheteur_siret,
        raison_sociale,
        libelle_commune,
        acheteur_map,
        departement,
        nom_region,
        lien_annuaire,
    )


@callback(
    Output(component_id="acheteur_marches_attribues", component_property="children"),
    Output(
        component_id="acheteur_titulaires_differents", component_property="children"
    ),
    Input(component_id="acheteur_data", component_property="data"),
)
def update_acheteur_stats(data):
    dff = pl.DataFrame(data, strict=False, infer_schema_length=5000)
    if dff.height == 0:
        dff = pl.DataFrame(schema=df.collect_schema())
    df_marches = dff.unique("id")
    nb_marches = format_number(df_marches.height)
    # somme_marches = format_number(int(df_marches.select(pl.sum("montant")).item()))
    marches_attribues = [html.Strong(nb_marches), " marchés et accord-cadres attribués"]
    # + ", pour un total de ", html.Strong(somme_marches + " €")]
    del df_marches

    nb_titulaires = dff.unique("titulaire_id").height
    nb_titulaires = [
        html.Strong(format_number(nb_titulaires)),
        " titulaires (SIRET) différents",
    ]
    del dff

    return marches_attribues, nb_titulaires


@callback(
    Output(component_id="acheteur_data", component_property="data"),
    Output("btn-download-data-acheteur", "disabled"),
    Output("btn-download-data-acheteur", "children"),
    Output("btn-download-data-acheteur", "title"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def get_acheteur_marches_data(url, acheteur_year: str) -> tuple:
    acheteur_siret = url.split("/")[-1]
    lff = df.lazy()
    lff = lff.filter(pl.col("acheteur_id") == acheteur_siret)
    if acheteur_year and acheteur_year != "Toutes les années":
        acheteur_year = int(acheteur_year)
        lff = lff.filter(pl.col("dateNotification").dt.year() == acheteur_year)
    lff = lff.sort(["dateNotification", "uid"], descending=True, nulls_last=True)
    dff: pl.DataFrame = lff.collect(engine="streaming")
    download_disabled, download_text, download_title = get_button_properties(dff.height)

    data = dff.to_dicts()
    return data, download_disabled, download_text, download_title


@callback(
    Output("acheteur_datatable", "data"),
    Output("acheteur_datatable", "columns"),
    Output("acheteur_datatable", "tooltip_header"),
    Output("acheteur_datatable", "data_timestamp"),
    Output("acheteur_nb_rows", "children"),
    Output("btn-download-filtered-data-acheteur", "disabled"),
    Output("btn-download-filtered-data-acheteur", "children"),
    Output("btn-download-filtered-data-acheteur", "title"),
    Output("filter-cleanup-trigger-acheteur", "data"),
    Input("acheteur_url", "href"),
    Input("acheteur_data", "data"),
    Input("acheteur_datatable", "page_current"),
    Input("acheteur_datatable", "page_size"),
    Input("acheteur_datatable", "filter_query"),
    Input("acheteur_datatable", "sort_by"),
    State("acheteur_datatable", "data_timestamp"),
)
def get_last_marches_data(
    href, data, page_current, page_size, filter_query, sort_by, data_timestamp
) -> tuple:
    return prepare_table_data(
        data, data_timestamp, filter_query, page_current, page_size, sort_by, "acheteur"
    )


@callback(
    Output(component_id="top10_titulaires", component_property="children"),
    Input(component_id="acheteur_data", component_property="data"),
)
def get_top_titulaires(data):
    return get_top_org_table(data, "titulaire")


@callback(
    Output("download-data-acheteur", "data"),
    Input("btn-download-data-acheteur", "n_clicks"),
    State(component_id="acheteur_data", component_property="data"),
    State(component_id="acheteur_nom", component_property="children"),
    State(component_id="acheteur_year", component_property="value"),
    prevent_initial_call=True,
)
def download_acheteur_data(
    n_clicks,
    data: [dict],
    acheteur_nom: str,
    annee: str,
):
    df_to_download = pl.DataFrame(data)

    def to_bytes(buffer):
        df_to_download.write_excel(
            buffer, worksheet="DECP" if annee in ["Toutes les années", None] else annee
        )

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{acheteur_nom}_{date}.xlsx")


@callback(
    Output("acheteur-download-filtered-data", "data"),
    State("acheteur_data", "data"),
    Input("btn-download-filtered-data-acheteur", "n_clicks"),
    State("acheteur_nom", "children"),
    State("acheteur_datatable", "filter_query"),
    State("acheteur_datatable", "sort_by"),
    State("acheteur_datatable", "hidden_columns"),
    prevent_initial_call=True,
)
def download_filtered_acheteur_data(
    data, n_clicks, acheteur_nom, filter_query, sort_by, hidden_columns: list = None
):
    lff: pl.LazyFrame = pl.LazyFrame(
        data
    )  # start from the full acheteur data, not from paginated table data

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        lff = filter_table_data(lff, filter_query, "ach download")

    if len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    def to_bytes(buffer):
        lff.collect(engine="streaming").write_excel(buffer, worksheet="DECP")

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(
        to_bytes, filename=f"decp_filtrées_{acheteur_nom}_{date}.xlsx"
    )


# Pour nettoyer les icontains et i< des filtres
# voir aussi src/assets/dash_clientside.js
clientside_callback(
    ClientsideFunction(
        namespace="clientside",
        function_name="clean_filters",
    ),
    Output("filter-cleanup-trigger-acheteur", "data", allow_duplicate=True),
    Input("filter-cleanup-trigger-acheteur", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("acheteur-hidden-columns", "data", allow_duplicate=True),
    Input("acheteur_column_list", "selected_rows"),
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
    Output("acheteur_datatable", "hidden_columns", allow_duplicate=True),
    Input(
        "acheteur-hidden-columns",
        "data",
    ),
    prevent_initial_call=True,
)
def store_hidden_columns(hidden_columns):
    return hidden_columns


@callback(
    Output("acheteur_column_list", "selected_rows"),
    Input("acheteur_datatable", "hidden_columns"),
    State("acheteur_column_list", "selected_rows"),  # pour éviter la boucle infinie
)
def update_checkboxes_from_hidden_columns(hidden_cols, current_checkboxes):
    hidden_cols = hidden_cols or get_default_hidden_columns("acheteur")

    # Show all columns that are NOT hidden
    visible_cols = [columns.index(col) for col in columns if col not in hidden_cols]
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
    Output("acheteur_datatable", "filter_query", allow_duplicate=True),
    Output("acheteur_datatable", "sort_by"),
    Input("btn-acheteur-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_view(n_clicks):
    return "", []


@callback(Input("acheteur_url", "pathname"))
def cb_add_canonical_link(pathname):
    print("coucou 2")
    add_canonical_link(pathname)
