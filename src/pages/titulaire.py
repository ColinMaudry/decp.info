import datetime

import polars as pl
from dash import Input, Output, State, callback, dash_table, dcc, html, register_page

from src.figures import point_on_map
from src.utils import (
    add_links_in_dict,
    format_montant,
    format_number,
    get_annuaire_data,
    get_departement_region,
    lf,
    meta_content,
    setup_table_columns,
)

register_page(
    __name__,
    path_template="/titulaires/<titulaire_id>",
    title=meta_content["title"],
    name="Titulaire",
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=5,
)

# 21690123100011

layout = [
    dcc.Store(id="titulaire_data", storage_type="memory"),
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
                            html.Span(id="titulaire_siret"),
                            " - ",
                            html.Span(id="titulaire_nom"),
                        ],
                    ),
                    html.Div(
                        className="org_year",
                        children=dcc.Dropdown(
                            id="titulaire_year",
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
                            html.P(["Commune : ", html.Strong(id="titulaire_commune")]),
                            html.P(
                                [
                                    "Département : ",
                                    html.Strong(id="titulaire_departement"),
                                ]
                            ),
                            html.P(["Région : ", html.Strong(id="titulaire_region")]),
                            html.A(
                                id="titulaire_lien_annuaire",
                                children="Plus de détails sur l'Annuaire des entreprises",
                                target="_blank",
                            ),
                        ],
                    ),
                    html.Div(
                        className="org_stats",
                        children=[
                            html.P(id="titulaire_titre_stats"),
                            html.P(id="titulaire_marches_remportes"),
                            html.P(id="titulaire_acheteurs_differents"),
                            html.Button(
                                "Téléchargement au format Excel",
                                id="btn-download-titulaire-data",
                            ),
                            dcc.Download(id="download-titulaire-data"),
                        ],
                    ),
                    html.Div(className="org_map", id="titulaire_map"),
                ],
            ),
            # récupérer les données de l'acheteur sur l'api annuaire
            html.H3("Derniers marchés publics remportés"),
            html.Div(id="titulaire_last_marches", children=""),
        ],
    ),
]


@callback(
    Output(component_id="titulaire_siret", component_property="children"),
    Output(component_id="titulaire_nom", component_property="children"),
    Output(component_id="titulaire_commune", component_property="children"),
    Output(component_id="titulaire_map", component_property="children"),
    Output(component_id="titulaire_departement", component_property="children"),
    Output(component_id="titulaire_region", component_property="children"),
    Output(component_id="titulaire_lien_annuaire", component_property="href"),
    Input(component_id="url", component_property="pathname"),
)
def update_titulaire_infos(url):
    titulaire_siret = url.split("/")[-1]
    if len(titulaire_siret) != 14:
        titulaire_siret = (
            f"Le SIRET renseigné doit faire 14 caractères ({titulaire_siret})"
        )
    data = get_annuaire_data(titulaire_siret)
    data_etablissement = data["matching_etablissements"][0]
    titulaire_map = point_on_map(
        data_etablissement["latitude"], data_etablissement["longitude"]
    )
    code_departement, nom_departement, nom_region = get_departement_region(
        data_etablissement["code_postal"]
    )
    departement = f"{nom_departement} ({code_departement})"
    lien_annuaire = (
        f"https://annuaire-entreprises.data.gouv.fr/etablissement/{titulaire_siret}"
    )
    return (
        titulaire_siret,
        data["nom_raison_sociale"],
        data_etablissement["libelle_commune"],
        titulaire_map,
        departement,
        nom_region,
        lien_annuaire,
    )


@callback(
    Output(component_id="titulaire_marches_remportes", component_property="children"),
    Output(
        component_id="titulaire_acheteurs_differents", component_property="children"
    ),
    Input(component_id="titulaire_data", component_property="data"),
)
def update_titulaire_stats(data):
    df = pl.DataFrame(data)
    if df.height == 0:
        df = pl.DataFrame(schema=lf.collect_schema())
    df_marches = df.unique("uid")
    nb_marches = format_number(df_marches.height)
    # somme_marches = format_number(int(df_marches.select(pl.sum("montant")).item()))
    marches_remportes = [html.Strong(nb_marches), " marchés et accord-cadres remportés"]
    # + ", pour un total de ", html.Strong(somme_marches + " €")]
    del df_marches

    nb_acheteurs = df.unique("acheteur_id").height
    nb_acheteurs = [
        html.Strong(format_number(nb_acheteurs)),
        " titulaires (SIRET) différents",
    ]
    del df

    return marches_remportes, nb_acheteurs


@callback(
    Output(component_id="titulaire_data", component_property="data"),
    Input(component_id="url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def get_titulaire_marches_data(url, titulaire_year: str) -> pl.LazyFrame:
    titulaire_siret = url.split("/")[-1]
    lff = lf.filter(
        (pl.col("titulaire_id") == titulaire_siret)
        & (pl.col("titulaire_typeIdentifiant") == "SIRET")
    )
    lff = lff.fill_null("")
    lff = lff.select(
        "id",
        "uid",
        "objet",
        "dateNotification",
        "acheteur_id",
        "acheteur_nom",
        "montant",
        "codeCPV",
        "dureeMois",
    )
    if titulaire_year and titulaire_year != "Toutes":
        lff = lff.filter(
            pl.col("dateNotification").cast(pl.String).str.starts_with(titulaire_year)
        )
    lff = lff.sort(["dateNotification", "uid"], descending=True, nulls_last=True)

    data = lff.collect(engine="streaming").to_dicts()
    return data


@callback(
    Output(component_id="titulaire_last_marches", component_property="children"),
    Input(component_id="titulaire_data", component_property="data"),
)
def get_last_marches_table(data) -> html.Div:
    columns = [
        "uid",
        "objet",
        "dateNotification",
        "acheteur_nom",
        "montant",
        "codeCPV",
        "dureeMois",
    ]

    dff = pl.DataFrame(data)
    dff = format_montant(dff)
    columns, tooltip = setup_table_columns(
        dff, hideable=False, exclude=["acheteur_id", "id"]
    )
    data = dff.to_dicts()
    # Idéalement on utiliserait add_org_links(), mais le résultat attendu
    # est différent de home.py (Tableau)
    data = add_links_in_dict(data, "acheteur")

    table = html.Div(
        className="marches_table",
        id="titulaire_datatable",
        children=dash_table.DataTable(
            data=data,
            markdown_options={"html": True},
            page_action="native",
            filter_action="native",
            filter_options={"case": "insensitive", "placeholder_text": "Filtrer..."},
            columns=columns,
            tooltip_header=tooltip,
            tooltip_duration=8000,
            tooltip_delay=350,
            cell_selectable=False,
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
                    "if": {"column_id": "acheteur_nom"},
                    "maxWidth": "400px",
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
    Output("download-titulaire-data", "data"),
    Input("btn-download-titulaire-data", "n_clicks"),
    State(component_id="titulaire_data", component_property="data"),
    State(component_id="titulaire_nom", component_property="children"),
    State(component_id="titulaire_year", component_property="value"),
    prevent_initial_call=True,
)
def download_titulaire_data(
    n_clicks,
    data: [dict],
    titulaire_nom: str,
    annee: str,
):
    df_to_download = pl.DataFrame(data)

    def to_bytes(buffer):
        df_to_download.write_excel(
            buffer, worksheet="DECP" if annee in ["Toutes", None] else annee
        )

    date = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{titulaire_nom}_{date}.xlsx")
