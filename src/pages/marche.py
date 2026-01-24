import json
from datetime import datetime

import dash_bootstrap_components as dbc
import polars as pl
from dash import Input, Output, callback, dcc, html, register_page
from polars import selectors as cs

from src.utils import (
    data_schema,
    df,
    format_values,
    make_org_jsonld,
    meta_content,
    unformat_montant,
)


def get_title(uid: str = None) -> str:
    return f"Marché {uid} | decp.info"


register_page(
    __name__,
    path_template="/marches/<uid>",
    title=get_title,
    name="Marché",
    description="Consultez les détails de ce marché public : montant, acheteur, titulaires, modifications, etc.",
    image_url=meta_content["image_url"],
    order=7,
)

layout = [
    dcc.Store(id="marche_data"),
    dcc.Store(id="titulaires_data"),
    dcc.Location(id="marche_url", refresh="callback-nav"),
    html.Script(
        type="application/ld+json", id="marche_jsonld", children=['{"test": "1"}']
    ),
    dbc.Container(
        className="marche_infos",
        children=[
            dbc.Row(
                dbc.Col(
                    [
                        html.H1(id="marche_objet", style={"fontSize": "1.5em"}),
                        html.P(
                            "Vous consultez un résumé des données de ce marché public"
                        ),
                        html.Ul(
                            [
                                html.Li(
                                    "après son attribution aux titulaires qui l'ont remporté à la suite d'un appel d'offres (ou sans appel d'offres via une attribution directe)"
                                ),
                                html.Li(
                                    "après avoir appliqué les éventuelles modifications de montant, durée ou titulaires renseignées par l'acheteur"
                                ),
                            ]
                        ),
                        html.P(
                            "Le montant total payé aux titulaires, la durée du marché et la liste des titulaires peuvent cependant encore évoluer jusqu'à la fin de l'exécution du marché."
                        ),
                    ]
                )
            ),
            dbc.Row(
                [
                    dbc.Col(id="marche_infos_1", width=12, md=4),
                    dbc.Col(id="marche_infos_2", width=12, md=4),
                    dbc.Col(
                        width=12,
                        md=4,
                        children=[
                            html.H4("Titulaires"),
                            html.Ul(id="marche_infos_titulaires"),
                        ],
                    ),
                ]
            ),
        ],
    ),
]


@callback(
    Output("marche_data", "data"),
    Output("titulaires_data", "data"),
    Input(component_id="marche_url", component_property="pathname"),
)
def get_marche_data(url) -> tuple[dict, list]:
    marche_uid = url.split("/")[-1]

    # Récupération des données du marché à partir du df global

    lff = df.lazy()
    lff = lff.filter(pl.col("uid") == pl.lit(marche_uid))

    # Données des titulaires du marché
    dff_titulaires = lff.select(cs.starts_with("titulaire")).collect(engine="streaming")

    # Données du marché
    dff_marche = lff.unique("uid").collect(engine="streaming")
    dff_marche = format_values(dff_marche)

    return dff_marche.to_dicts()[0], dff_titulaires.to_dicts()


@callback(
    Output("marche_objet", "children"),
    Output("marche_infos_1", "children"),
    Output("marche_infos_2", "children"),
    Output("marche_infos_titulaires", "children"),
    Input("marche_data", "data"),
    Input("titulaires_data", "data"),
)
def update_marche_info(marche, titulaires):
    def make_parameter(col):
        column_object = data_schema.get(col)
        column_name = column_object.get("title") if column_object else col

        if marche[col]:
            if col == "acheteur_nom":
                value = html.A(
                    href=f"/acheteurs/{marche['acheteur_id']}",
                    children=marche["acheteur_nom"],
                )
            elif col == "sourceDataset":
                value = html.A(
                    href=marche["sourceFile"], children=marche["sourceDataset"]
                )
                column_name = "Source des données"

            # Dates
            elif col in ["dateNotification", "datePublicationDonnees"]:
                value = datetime.fromisoformat(marche[col]).strftime("%d/%m/%Y")

            # Listes
            elif (
                col
                in [
                    "techniques",
                    "typesPrix",
                    "considerationsSociales",
                    "considerationsEnvironnementales",
                ]
                and "," in marche[col]
            ):
                col_values = marche[col].split(", ")
                lines = []
                for val in col_values:
                    lines.append(html.Li(val))
                _content = html.Div(
                    [html.P([column_name, " : "]), html.Ul(children=lines)]
                )
                return _content
            else:
                value = marche.get(col)
        else:
            value = ""

        param_content = html.P([column_name, "  : ", html.Strong(value)])
        return param_content

    marche_objet = make_parameter("objet")

    marche_infos = [
        make_parameter("id"),
        make_parameter("dateNotification"),  # date
        make_parameter("nature"),
        make_parameter("acheteur_nom"),  # lien
        make_parameter("montant"),
        make_parameter("codeCPV"),
        make_parameter("procedure"),
        make_parameter("techniques"),  # list
        make_parameter("dureeMois"),
        make_parameter("dureeRestanteMois"),
        make_parameter("offresRecues"),
        make_parameter("datePublicationDonnees"),  # date
        make_parameter("formePrix"),
        make_parameter("typesPrix"),  # list
        make_parameter("attributionAvance"),
        make_parameter("tauxAvance"),
        make_parameter("marcheInnovant"),  # label
        make_parameter("modalitesExecution"),
        make_parameter("considerationsSociales"),  # list
        make_parameter("considerationsEnvironnementales"),  # list
        make_parameter("ccag"),
        make_parameter("sousTraitanceDeclaree"),
        make_parameter("typeGroupementOperateurs"),
        make_parameter("origineFrance"),
        make_parameter("origineUE"),
        make_parameter("idAccordCadre"),
        make_parameter("sourceDataset"),  # lien
    ]

    half = round(len(marche_infos) / 2)
    # pas inclus pour l'instant : lieu d'exécution, modifications

    titulaires_lines = []
    for titulaire in titulaires:
        if titulaire["titulaire_typeIdentifiant"] == "SIRET":
            categorie = titulaire.get("titulaire_categorie", "")
            if titulaire.get("titulaire_categorie"):
                distance = str(titulaire.get("titulaire_categorie")) + " km"
            else:
                distance = ""

            content = html.Li(
                [
                    html.A(
                        href=f"/titulaires/{titulaire['titulaire_id']}",
                        children=titulaire["titulaire_nom"],
                    ),
                    f" ({categorie}, {distance})",
                ]
            )
        else:
            content = html.Li(titulaire["titulaire_nom"])
        titulaires_lines.append(content)

    return marche_objet, marche_infos[:half], marche_infos[half:], titulaires_lines


@callback(
    Output(component_id="marche_jsonld", component_property="children"),
    Input("marche_data", "data"),
    Input("titulaires_data", "data"),
)
def get_marche_jsonld(marche, titulaires) -> str:
    acheteur_id = marche.get("acheteur_id")
    type_order = (
        "Service" if marche.get("categorie") in ["Services", "Travaux"] else "Product"
    )
    result = []

    for titulaire in titulaires:
        jsonld = {
            "@context": "https://schema.org",
            "@type": "Order",
            "@id": f"https://decp.info/marches/{marche.get('uid')}",
            "name": f"{marche.get('nature')} conclu par {marche.get('acheteur_nom')} le {marche.get('dateNotification')}",
            "description": marche.get("objet"),
            "orderNumber": marche.get("uid"),
            "orderDate": marche.get("dateNotification"),
            "price": unformat_montant(marche.get("montant")),
            "priceCurrency": "EUR",
            "customer": make_org_jsonld(
                acheteur_id, org_name=marche.get("acheteur_nom"), org_type="acheteur"
            ),
            "seller": make_org_jsonld(
                titulaire.get("titulaire_id"),
                org_name=titulaire.get("titulaire_nom"),
                org_type="titulaire",
                type_org_id=titulaire.get("titulaire_typeIdentifiant"),
            ),
            "orderedItem": {
                "@type": type_order,
                "name": marche.get("objet"),
                "category": {
                    "@type": "CategoryCode",
                    "propertyID": "cpv",
                    "codeValue": marche.get("codeCPV"),
                    # "description": "Description du code CPV"
                },
                # "serviceType": "Description du code CPV"
            },
        }
        result.append(jsonld)
    return json.dumps(result, indent=2)
