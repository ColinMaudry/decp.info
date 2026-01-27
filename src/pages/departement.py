import polars as pl
from dash import Input, Output, callback, dcc, html, register_page

from src.utils import departements, df_acheteurs_departement

name = "Département"


def get_title(code):
    return f"Marchés publics de {departements[code]['departement']} | decp.info"


def get_description(code):
    return f"Marchés publics passés dans le département {departements[code]['departement']} | decp.info"


register_page(
    __name__,
    path_template="/departements/<code>",
    title=get_title,
    description=get_description,
    order=50,
    name=name,
)

layout = html.Div(
    [
        dcc.Location(id="departement_url", refresh="callback-nav"),
        html.Div(id="departement_marches"),
    ]
)


@callback(
    Output(component_id="departement_marches", component_property="children"),
    Input(component_id="departement_url", component_property="pathname"),
)
def departement_marches(url):
    departement = url.split("/")[-1]
    acheteurs = []
    df = df_acheteurs_departement.filter(
        pl.col("acheteur_departement_code") == departement
    )
    for row in df.iter_rows(named=True):
        p = html.P(
            [
                dcc.Link(
                    row["acheteur_nom"],
                    href=url + f"/{row['acheteur_id']}",
                    title=f"Marchés publics de {row['acheteur_nom']}",
                ),
                " ",
                dcc.Link(
                    "(page dédiée)",
                    href=f"/acheteurs/{row['acheteur_id']}",
                    title=f"Page dédiée aux marchés publics de {row['acheteur_nom']}",
                ),
            ]
        )
        acheteurs.append(p)
    return acheteurs
