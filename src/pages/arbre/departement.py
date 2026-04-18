from dash import Input, Output, callback, dcc, html, register_page

from src.db import get_cursor
from src.old_utils import DEPARTEMENTS

NAME = "Département"


def get_title(code):
    return f"Marchés publics de {DEPARTEMENTS[code]['departement']} | decp.info"


def get_description(code):
    return f"Marchés publics passés dans le département {DEPARTEMENTS[code]['departement']} | decp.info"


register_page(
    __name__,
    path_template="/departements/<code>",
    title=get_title,
    description=get_description,
    order=50,
    name=NAME,
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
        table = (
            "acheteurs_departement"
            if org_type == "acheteur"
            else "titulaires_departement"
            if org_type == "titulaire"
            else None
        )
        if table is None:
            raise ValueError
        col_prefix = org_type
        rows = (
            get_cursor()
            .execute(
                f"SELECT {col_prefix}_id, {col_prefix}_nom "
                f"FROM {table} "
                f"WHERE {col_prefix}_departement_code = ? "
                f"ORDER BY {col_prefix}_nom",
                [departement],
            )
            .fetchall()
        )

        link_list = []
        for org_id, org_nom in rows:
            li = html.Li(
                [
                    dcc.Link(
                        org_nom,
                        href=url + f"/{org_type}/{org_id}",
                        title=f"Marchés publics de {org_nom}",
                    ),
                    " ",
                    dcc.Link(
                        "(page dédiée)",
                        href=f"/{org_type}s/{org_id}",
                        title=f"Page dédiée aux marchés publics de {org_nom}",
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
