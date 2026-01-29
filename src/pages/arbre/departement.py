import polars as pl
from dash import Input, Output, callback, dcc, html, register_page

from src.utils import departements, df_acheteurs_departement, df_titulaires_departement

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

    def make_link_list(org_type) -> list:
        link_list = []
        if org_type == "acheteur":
            df = df_acheteurs_departement
        elif org_type == "titulaire":
            df = df_titulaires_departement
        else:
            raise ValueError

        df = df.filter(pl.col(f"{org_type}_departement_code") == departement)

        for row in df.iter_rows(named=True):
            li = html.Li(
                [
                    dcc.Link(
                        row[f"{org_type}_nom"],
                        href=url + f"/{org_type}/{row[f'{org_type}_id']}",
                        title=f"Marchés publics de {row[f'{org_type}_nom']}",
                    ),
                    " ",
                    dcc.Link(
                        "(page dédiée)",
                        href=f"/{org_type}s/{row[f'{org_type}_id']}",
                        title=f"Page dédiée aux marchés publics de {row[f'{org_type}_nom']}",
                    ),
                ]
            )
            link_list.append(li)
        return link_list

    content = [
        html.H3("Acheteurs publics du département"),
        html.Ul(make_link_list("acheteur")),
        html.H3("Titulaires du département"),
        html.Ul(make_link_list("titulaire")),
    ]

    return content
