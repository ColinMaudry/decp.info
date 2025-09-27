import polars as pl
from dash import Input, Output, callback, dash_table, dcc, html, register_page

from src.utils import lf

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
            html.H2(id="acheteur_title", children=""),
            html.H3("Derniers marchés publics notifiés"),
            html.Div(id="acheteur_last_marches", children=""),
        ],
    ),
]


@callback(
    Output(component_id="acheteur_title", component_property="children"),
    Input(component_id="url", component_property="pathname"),
)
def update_acheteur(url):
    acheteur_siret = url.split("/")[-1]
    if len(acheteur_siret) != 14:
        return f"Le SIRET renseigné doit faire 14 caractères ({acheteur_siret})"

    return acheteur_siret


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
