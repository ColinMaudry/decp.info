import datetime

import polars as pl
from dash import Input, Output, callback, dash_table, dcc, html, register_page

from src.figures import point_on_map
from src.utils import format_number, get_annuaire_data, get_departement_region, lf

register_page(
    __name__,
    path_template="/acheteur/<acheteur_id>",
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
                            html.P(id="acheteur_fournisseurs_differents"),
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
        component_id="acheteur_fournisseurs_differents", component_property="children"
    ),
    Input(component_id="acheteur_data", component_property="data"),
)
def update_acheteur_stats(data):
    df = pl.DataFrame(data)
    df_marches = df.unique("uid")
    nb_marches = format_number(df_marches.height)
    # somme_marches = format_number(int(df_marches.select(pl.sum("montant")).item()))
    marches_attribues = [html.Strong(nb_marches), " marchés et accord-cadres attribués"]
    # + ", pour un total de ", html.Strong(somme_marches + " €")]
    del df_marches

    nb_fournisseurs = df.unique("titulaire_id").height
    nb_fournisseurs = [
        html.Strong(format_number(nb_fournisseurs)),
        " fournisseurs (SIRET) différents",
    ]
    del df

    return marches_attribues, nb_fournisseurs


@callback(
    Output(component_id="acheteur_data", component_property="data"),
    Input(component_id="url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def get_acheteur_marches_data(url, acheteur_year: str) -> pl.LazyFrame:
    acheteur_siret = url.split("/")[-1]
    lff = lf.filter(pl.col("acheteur_id") == acheteur_siret)
    if acheteur_year and acheteur_year != "Toutes":
        lff = lff.filter(
            pl.col("dateNotification").cast(pl.String).str.starts_with(acheteur_year)
        )
    lff = lff.select(
        "uid",
        "objet",
        "dateNotification",
        "titulaire_id",
        "titulaire_nom",
        "montant",
        "codeCPV",
        "dureeMois",
    )
    lff = lff.sort("dateNotification", descending=True, nulls_last=True)
    data = lff.collect(engine="streaming").to_dicts()
    return data


@callback(
    Output(component_id="acheteur_last_marches", component_property="children"),
    Input(component_id="acheteur_data", component_property="data"),
)
def get_last_marches_table(data) -> html.Div:
    columns = data[0].keys()

    table = html.Div(
        className="marches_table",
        children=dash_table.DataTable(
            data=data,
            page_action="native",
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
                    "lineHeight": "14px",
                    "whiteSpace": "normal",
                },
            ],
        ),
    )
    return table
