import datetime

import polars as pl
from dash import Input, Output, State, callback, dcc, html, register_page

from src.callbacks import get_top_org_table
from src.figures import DataTable, point_on_map
from src.utils import (
    df,
    format_number,
    get_annuaire_data,
    get_default_hidden_columns,
    get_departement_region,
    meta_content,
    prepare_table_data,
)

register_page(
    __name__,
    path_template="/acheteurs/<acheteur_id>",
    title=meta_content["title"],
    name="Acheteur",
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=5,
)

datatable = html.Div(
    className="marches_table",
    children=DataTable(
        dtid="acheteur_datatable",
        page_action="custom",
        filter_action="custom",
        sort_action="custom",
        page_size=10,
        hidden_columns=get_default_hidden_columns(page="acheteur"),
    ),
)

layout = [
    dcc.Store(id="acheteur_data", storage_type="memory"),
    dcc.Location(id="url", refresh="callback-nav"),
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
                            options=["Toutes"]
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
                                target="_blank",
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
                                id="btn-download-acheteur-data",
                            ),
                            dcc.Download(id="download-acheteur-data"),
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
                            html.P("lignes", id="acheteur_nb_rows"),
                            html.Button(
                                "Téléchargement désactivé au-delà de 65 000 lignes",
                                id="btn-download-data-acheteur",
                                disabled=True,
                            ),
                            dcc.Download(id="acheteur-download-data"),
                            dcc.Store(
                                id="acheteur_filtered_data", storage_type="memory"
                            ),
                        ],
                        className="table-menu",
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
    Input(component_id="url", component_property="pathname"),
)
def update_acheteur_infos(url):
    acheteur_siret = url.split("/")[-1]
    if len(acheteur_siret) != 14:
        acheteur_siret = (
            f"Le SIRET renseigné doit faire 14 caractères ({acheteur_siret})"
        )
    data = get_annuaire_data(acheteur_siret)
    data_etablissement = data["matching_etablissements"][0]
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
    return (
        acheteur_siret,
        data["nom_raison_sociale"],
        data_etablissement["libelle_commune"],
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
    dff = pl.DataFrame(data)
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
    Input(component_id="url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def get_acheteur_marches_data(url, acheteur_year: str) -> list[dict]:
    acheteur_siret = url.split("/")[-1]
    lff = df.lazy()
    lff = lff.filter(pl.col("acheteur_id") == acheteur_siret)
    if acheteur_year and acheteur_year != "Toutes":
        acheteur_year = int(acheteur_year)
        lff = lff.filter(pl.col("dateNotification").dt.year() == acheteur_year)
    lff = lff.sort(["dateNotification", "id"], descending=True, nulls_last=True)
    lff = lff.fill_null("")

    data = lff.collect(engine="streaming").to_dicts()
    return data


@callback(
    Output("acheteur_datatable", "data"),
    Output("acheteur_datatable", "columns"),
    Output("acheteur_datatable", "tooltip_header"),
    Output("acheteur_datatable", "data_timestamp"),
    Output("acheteur_nb_rows", "children"),
    Output("btn-download-data-acheteur", "disabled"),
    Output("btn-download-data-acheteur", "children"),
    Output("btn-download-data-acheteur", "title"),
    Input("acheteur_data", "data"),
    Input("acheteur_datatable", "page_current"),
    Input("acheteur_datatable", "page_size"),
    Input("acheteur_datatable", "filter_query"),
    Input("acheteur_datatable", "sort_by"),
    State("acheteur_datatable", "data_timestamp"),
)
def get_last_marches_data(
    data, page_current, page_size, filter_query, sort_by, data_timestamp
) -> list[dict]:
    return prepare_table_data(
        data, data_timestamp, filter_query, page_current, page_size, sort_by
    )


@callback(
    Output(component_id="top10_titulaires", component_property="children"),
    Input(component_id="acheteur_data", component_property="data"),
)
def get_top_titulaires(data):
    return get_top_org_table(data, "titulaire")


@callback(
    Output("download-acheteur-data", "data"),
    Input("btn-download-acheteur-data", "n_clicks"),
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
            buffer, worksheet="DECP" if annee in ["Toutes", None] else annee
        )

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{acheteur_nom}_{date}.xlsx")
