from datetime import datetime

import polars as pl
from dash import Input, Output, callback, dcc, html, register_page
from polars import selectors as cs

from src.utils import data_schema, format_montant, lf, meta_content

register_page(
    __name__,
    path_template="/marches/<uid>",
    title=meta_content["title"],
    name="Marché",
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=7,
)

layout = [
    dcc.Store(id="marche_data"),
    dcc.Store(id="titulaires_data"),
    dcc.Location(id="url", refresh="callback-nav"),
    html.Div(
        className="container marche_infos",
        children=[
            html.P("Vous consultez un résumé des données de ce marché public"),
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
            html.Div(
                className="wrapper",
                children=[
                    html.Div(
                        className="marche_map",
                        id="marche_map",
                        children=[
                            html.H4("Titulaires"),
                            html.Ul(id="marche_infos_titulaires"),
                        ],
                    ),
                    html.Div(className="marche_infos_1", id="marche_infos_1"),
                    html.Div(className="marche_infos_2", id="marche_infos_2"),
                ],
            ),
        ],
    ),
]


@callback(
    Output("marche_data", "data"),
    Output("titulaires_data", "data"),
    Input(component_id="url", component_property="pathname"),
)
def get_marche_data(url):
    marche_uid = url.split("/")[-1]

    # Récupération des données du marché à partir du lf global
    lff = lf.filter(pl.col("uid") == pl.lit(marche_uid))

    # Données des titulaires du marché
    dff_titulaires = lff.select(cs.starts_with("titulaire")).collect(engine="streaming")

    # Données du marché
    dff_marche = (
        lff.select(~cs.starts_with("titulaires")).unique().collect(engine="streaming")
    )
    dff_marche = format_montant(dff_marche)

    assert dff_marche.height == 1

    return dff_marche.to_dicts()[0], dff_titulaires.to_dicts()


@callback(
    Output("marche_infos_1", "children"),
    Output("marche_infos_2", "children"),
    Output("marche_infos_titulaires", "children"),
    Input("marche_data", "data"),
    Input("titulaires_data", "data"),
)
def update_marche_info(marche, titulaires):
    def make_parameter(col):
        column_object = data_schema.get(col)
        column_name = column_object.get("friendly_name") if column_object else col

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
                print(marche[col])

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

    marche_infos = [
        make_parameter("id"),
        make_parameter("objet"),
        make_parameter("dateNotification"),  # date
        make_parameter("nature"),
        make_parameter("acheteur_nom"),  # lien
        make_parameter("montant"),
        make_parameter("codeCPV"),
        make_parameter("procedure"),
        make_parameter("techniques"),  # list
        make_parameter("dureeMois"),
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
            content = html.Li(
                html.A(
                    href=f"/titulaires/{titulaire['titulaire_id']}",
                    children=titulaire["titulaire_nom"],
                )
            )
        else:
            content = html.Li(titulaire["titulaire_nom"])
        titulaires_lines.append(content)

    return marche_infos[:half], marche_infos[half:], titulaires_lines
