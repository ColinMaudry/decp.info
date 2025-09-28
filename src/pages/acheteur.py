import datetime

import polars as pl
from dash import Input, Output, State, callback, dash_table, dcc, html, register_page

from src.figures import point_on_map
from src.utils import (
    add_org_links_in_dict,
    format_number,
    get_annuaire_data,
    get_departement_region,
    lf,
)

register_page(
    __name__,
    path_template="/acheteurs/<acheteur_id>",
    title="decp.info - acheteur",
    name="Acheteur",
    order=5,
)

# 21690123100011

layout = [
    dcc.Store(id="acheteur_data", storage_type="memory"),
    dcc.Location(id="url", refresh="callback-nav"),
    html.Div(
        className="container",
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
                ],
            ),
            # récupérer les données de l'acheteur sur l'api annuaire
            html.H3("Derniers marchés publics attribués"),
            html.Div(id="acheteur_last_marches", children=""),
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
    df = pl.DataFrame(data)
    if df.height == 0:
        df = pl.DataFrame(schema=lf.collect_schema())
    df_marches = df.unique("id")
    nb_marches = format_number(df_marches.height)
    # somme_marches = format_number(int(df_marches.select(pl.sum("montant")).item()))
    marches_attribues = [html.Strong(nb_marches), " marchés et accord-cadres attribués"]
    # + ", pour un total de ", html.Strong(somme_marches + " €")]
    del df_marches

    nb_titulaires = df.unique("titulaire_id").height
    nb_titulaires = [
        html.Strong(format_number(nb_titulaires)),
        " titulaires (SIRET) différents",
    ]
    del df

    return marches_attribues, nb_titulaires


@callback(
    Output(component_id="acheteur_data", component_property="data"),
    Input(component_id="url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def get_acheteur_marches_data(url, acheteur_year: str) -> pl.LazyFrame:
    acheteur_siret = url.split("/")[-1]
    lff = lf.filter(pl.col("acheteur_id") == acheteur_siret)
    lff = lff.fill_null("")
    lff = lff.select(
        "id",
        "objet",
        "dateNotification",
        "titulaire_id",
        "titulaire_nom",
        "montant",
        "codeCPV",
        "dureeMois",
    )
    if acheteur_year and acheteur_year != "Toutes":
        lff = lff.filter(
            pl.col("dateNotification").cast(pl.String).str.starts_with(acheteur_year)
        )
    lff = lff.sort(["dateNotification", "id"], descending=True, nulls_last=True)

    data = lff.collect(engine="streaming").to_dicts()
    return data


@callback(
    Output(component_id="acheteur_last_marches", component_property="children"),
    Input(component_id="acheteur_data", component_property="data"),
)
def get_last_marches_table(data) -> html.Div:
    columns = [
        "id",
        "objet",
        "dateNotification",
        "titulaire_nom",
        "montant",
        "codeCPV",
        "dureeMois",
    ]

    data = add_org_links_in_dict(data, "titulaire")

    table = html.Div(
        className="marches_table",
        id="marches_datatable",
        children=dash_table.DataTable(
            data=data,
            markdown_options={"html": True},
            page_action="native",
            filter_action="native",
            filter_options={"case": "insensitive", "placeholder_text": "Filtrer..."},
            columns=[
                {
                    "name": i,
                    "id": i,
                    "presentation": "markdown",
                    "type": "text",
                    "format": {"nully": "N/A"},
                    "hideable": False,
                }
                for i in columns
                if i not in ["titulaire_id"]
            ],
            page_size=10,
            style_cell_conditional=[
                {
                    "if": {"column_id": "objet"},
                    "minWidth": "300px",
                    "textAlign": "left",
                    "overflow": "hidden",
                    "lineHeight": "14px",
                    "whiteSpace": "normal",
                },
                {
                    "if": {"column_id": "titulaire_nom"},
                    "minWidth": "200px",
                    "textAlign": "left",
                    "overflow": "hidden",
                    "lineHeight": "18px",
                    "whiteSpace": "normal",
                },
            ],
        ),
    )
    return table


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
