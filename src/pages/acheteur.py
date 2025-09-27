import polars as pl
from dash import Input, Output, callback, dash_table, dcc, html, register_page

from src.figures import point_on_map
from src.utils import get_annuaire_data, lf

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
            html.H2(
                children=[
                    html.Span(id="acheteur_siret"),
                    " - ",
                    html.Span(id="acheteur_nom"),
                ]
            ),
            html.Div(
                className="wrapper",
                children=[
                    html.Div(
                        className="org_infos",
                        children=[html.P(["Commune : ", html.Span(id="commune")])],
                    ),
                    html.Div(className="org_map", id="acheteur_map"),
                    # adresse
                    # code commune
                    # lat long
                ],
            ),
            # récupérer les données de l'acheteur sur l'api annuaire
            html.H3("Derniers marchés publics notifiés"),
            html.Div(id="acheteur_last_marches", children=""),
        ],
    ),
]


@callback(
    Output(component_id="acheteur_siret", component_property="children"),
    Output(component_id="acheteur_nom", component_property="children"),
    Output(component_id="commune", component_property="children"),
    Output(component_id="acheteur_map", component_property="children"),
    Input(component_id="url", component_property="pathname"),
)
def update_acheteur(url):
    acheteur_siret = url.split("/")[-1]
    if len(acheteur_siret) != 14:
        return f"Le SIRET renseigné doit faire 14 caractères ({acheteur_siret})"
    data = get_annuaire_data(acheteur_siret)
    data_etablissement = data["matching_etablissements"][0]
    acheteur_map = point_on_map(
        data_etablissement["latitude"], data_etablissement["longitude"]
    )
    return (
        acheteur_siret,
        data["nom_raison_sociale"],
        data_etablissement["libelle_commune"],
        acheteur_map,
    )


@callback(
    Output(component_id="acheteur_data", component_property="data"),
    Input(component_id="url", component_property="pathname"),
)
def get_acheteur_marches_data(url) -> pl.LazyFrame:
    acheteur_siret = url.split("/")[-1]
    lff = lf.filter(pl.col("acheteur_id") == acheteur_siret)
    lff = lff.select(
        "uid",
        "objet",
        "dateNotification",
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
    table = html.Div(
        className="marches_table",
        children=dash_table.DataTable(
            data=data[:20],
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
