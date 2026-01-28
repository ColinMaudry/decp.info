import polars as pl
from dash import Input, Output, callback, dcc, html, register_page

from src.utils import (
    df_acheteurs,
    df_acheteurs_marches,
    df_titulaires,
    df_titulaires_marches,
)

name = "Liste des marchés publics"


def make_org_nom_verbe(org_type, org_id) -> tuple:
    if org_type == "titulaire":
        df = df_titulaires
        verbe = "remportés"
    elif org_type == "acheteur":
        df = df_acheteurs
        verbe = "attribués"
    else:
        raise ValueError

    org_nom = (
        df.filter(pl.col(f"{org_type}_id") == org_id).select(f"{org_type}_nom").item()
    )

    return org_nom, verbe


def get_title(code, org_type, org_id):
    org_nom, verbe = make_org_nom_verbe(org_type, org_id)

    return f"Marchés publics {verbe} par {org_nom} | decp.info"


def get_description(code, org_type, org_id):
    org_nom, verbe = make_org_nom_verbe(org_type, org_id)

    return f"Liste complète des marchés publics {verbe} par {org_nom} et publiés par decp.info. Cliquez sur les liens pour consulter les détails de chaque marché."


register_page(
    __name__,
    path_template="/departements/<code>/<org_type>/<org_id>",
    title=get_title,
    description=get_description,
    order=40,
    name=name,
)

layout = html.Div(
    [
        dcc.Location(id="liste_marches_url", refresh="callback-nav"),
        html.Div(id="liste_marches"),
    ]
)


@callback(
    Output(component_id="liste_marches", component_property="children"),
    Input(component_id="liste_marches_url", component_property="pathname"),
)
def liste_marches(url):
    org_type = url.split("/")[-2]
    org_id = url.split("/")[-1]

    def make_link_list() -> list:
        link_list = []
        if org_type == "acheteur":
            df = df_acheteurs_marches
        elif org_type == "titulaire":
            df = df_titulaires_marches
        else:
            raise ValueError

        df = df.filter(pl.col(f"{org_type}_id") == org_id)

        for row in df.iter_rows(named=True):
            li = html.Li(
                [
                    dcc.Link(
                        row["objet"],
                        href=f"/marches/{row['uid']}",
                        title=f"Marchés public attribué : {row['objet']}",
                    )
                ]
            )
            link_list.append(li)
        return link_list

    nom, verbe = make_org_nom_verbe(org_type, org_id)

    content = [
        html.H3(f"Marchés publics {verbe} par {nom}"),
        html.Ul(make_link_list()),
    ]

    return content
