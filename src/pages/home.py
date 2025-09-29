import os
from datetime import datetime

import polars as pl
from dash import Input, Output, State, callback, dash_table, dcc, html, register_page

from src.utils import (
    add_org_links,
    add_resource_link,
    data_schema,
    filter_table_data,
    format_montant,
    format_number,
    lf,
    meta_content,
    sort_table_data,
)

update_date = os.path.getmtime(os.getenv("DATA_FILE_PARQUET_PATH"))
update_date = datetime.fromtimestamp(update_date).strftime("%d/%m/%Y")

schema = lf.collect_schema()

name = "Tableau"
register_page(
    __name__,
    path="/",
    title=meta_content["title"],
    name=name,
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=1,
)

datatable = html.Div(
    className="marches_table",
    children=dash_table.DataTable(
        cell_selectable=False,
        id="table",
        page_size=20,
        page_current=0,
        page_action="custom",
        filter_action="custom",
        filter_options={"case": "insensitive", "placeholder_text": "Filtrer..."},
        sort_action="custom",
        sort_mode="multi",
        sort_by=[],
        row_deletable=False,
        style_cell_conditional=[
            {
                "if": {"column_id": "objet"},
                "minWidth": "350px",
                "textAlign": "left",
                "overflow": "hidden",
                "lineHeight": "14px",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "acheteur_nom"},
                "minWidth": "250px",
                "textAlign": "left",
                "overflow": "hidden",
                "lineHeight": "14px",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "titulaire_nom"},
                "minWidth": "250px",
                "textAlign": "left",
                "overflow": "hidden",
                "lineHeight": "14px",
                "whiteSpace": "normal",
            },
        ],
        data_timestamp=0,
        markdown_options={"html": True},
        tooltip_duration=8000,
        tooltip_delay=350,
    ),
)

layout = [
    html.Div(
        html.Details(
            children=[
                html.Summary(
                    html.H3("Mode d'emploi", style={"text-decoration": "underline"}),
                ),
                dcc.Markdown(
                    """
    ##### Définition des colonnes

    Pour voir la définition d'une colonne, passez votre souris sur son en-tête.

    ##### Filtres

    Vous pouvez appliquer un filtre pour chaque colonne en entrant du texte sous le nom de la colonne, puis en tapant sur `Entrée`.

    - Champs textuels : la recherche est insensible à la casse (majuscules/minuscules) et retourne les valeurs qui contiennent
    le texte recherché. Exemple : `rennes` retourne "RENNES METROPOLE".
    - Champs numériques : vous pouvez soit taper un nombre pour trouver les valeurs égales, soit le précéder de **>** ou **<** pour filtrer les valeurs supérieures ou inférieures. Exemple pour les offres reçues : `> 4` retourne les marchés ayant reçu plus de 4 offres.
    - Champs date : vous pouvez également utiliser **>** ou **<**. Exemples : `< 2024-01-31` pour "avant le 31 janvier 2024",
    `2024` pour "en 2024", `> 2022` pour "à partir de 2022"

    Vous pouvez filtrer plusieurs colonnes à la fois. Vos filtres sont remis à zéro quand vous rafraîchissez la page.

    ##### Tri

    Pour trier une colonne, utilisez les flèches grises à côté des noms de colonnes. Chaque clic change le tri dans cet ordre : tri ascendant, tri descendant, pas de tri.

    ##### Télécharger le résultat

    Vous pouvez télécharger le résultat de vos filtres et tris, pour les colonnes affichées, en cliquant sur **Télécharger au format Excel**.

    ##### Liens

    Les liens dans les colonnes Acheteur et Titulaire vous permettent de consulter une vue qui leur est dédiée
    (informations, marchés attribués/remportés, etc.)

    """
                ),
            ],
            id="instructions",
        ),
        id="header",
    ),
    # html.Div(
    #     [
    #         "Recherche dans objet : ",
    #         dcc.Input(id="search", value="", type="text"),
    #     ]
    # )]),
    dcc.Loading(
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        id="loading-home",
        type="default",
        children=[
            html.Div(
                [
                    html.P("lignes", id="nb_rows"),
                    html.Button(
                        "Téléchargement désactivé au-delà de 65 000 lignes",
                        id="btn-download-data",
                        disabled=True,
                    ),
                    dcc.Download(id="download-data"),
                    dcc.Store(id="filtered_data", storage_type="memory"),
                    html.P("Données mises à jour le " + str(update_date)),
                ],
                className="table-menu",
            ),
            datatable,
        ],
    ),
]


@callback(
    Output("table", "data"),
    Output("table", "columns"),
    Output("table", "tooltip_header"),
    Output("table", "data_timestamp"),
    Output("nb_rows", "children"),
    Output("btn-download-data", "disabled"),
    Output("btn-download-data", "children"),
    Output("btn-download-data", "title"),
    Input("table", "page_current"),
    Input("table", "page_size"),
    Input("table", "filter_query"),
    Input("table", "sort_by"),
    State("table", "data_timestamp"),
)
def update_table(page_current, page_size, filter_query, sort_by, data_timestamp):
    print(" + + + + + + + + + + + + + + + + + + ")

    # Application des filtres
    lff: pl.LazyFrame = lf  # start from the original data
    if filter_query:
        lff = filter_table_data(lff, filter_query)

    if len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    # Remplace les strings null par "", mais pas les numeric null
    lff = lff.fill_null("")

    # Matérialisation des filtres
    dff: pl.DataFrame = lff.collect()

    height = dff.height

    nb_rows = f"{format_number(height)} lignes"

    # Pagination des données
    start_row = page_current * page_size
    # end_row = (page_current + 1) * page_size
    dff = dff.slice(start_row, page_size)

    # Ajout des liens vers l'annuaire des entreprises
    dff = add_org_links(dff)

    # Ajout des liens vers les fichiers Open Data
    dff = add_resource_link(dff)

    # Formatage des montants
    dff = format_montant(dff)

    # Liste finale de colonnes
    columns = []
    tooltip = {}
    for column_id in dff.columns:
        column_object = data_schema.get(column_id)
        if column_object:
            column_name = column_object.get("friendly_name", column_id)
        else:
            column_name = column_id

        column = {
            "name": column_name,
            "id": column_id,
            "presentation": "markdown",
            "type": "text",
            "format": {"nully": "N/A"},
            "hideable": True,
        }
        columns.append(column)

        if column_object:
            tooltip[column_id] = {
                "value": f"""**{column_object.get("friendly_name", column_id)}**

    """
                + column_object["description"],
                "type": "markdown",
            }

    dicts = dff.to_dicts()

    if height > 65000:
        download_disabled = True
        download_text = "Téléchargement désactivé au-delà de 65 000 lignes"
        download_title = "Excel ne supporte pas d'avoir plus de 65 000 URLs dans une même feuille de calcul. Contactez-moi pour me présenter votre besoin en téléchargement afin que je puisse adapter la solution."
    else:
        download_disabled = False
        download_text = "Télécharger au format Excel"
        download_title = ""

    return (
        dicts,
        columns,
        tooltip,
        data_timestamp + 1,
        nb_rows,
        download_disabled,
        download_text,
        download_title,
    )


@callback(
    Output("download-data", "data"),
    Input("btn-download-data", "n_clicks"),
    State("table", "filter_query"),
    State("table", "sort_by"),
    State("table", "hidden_columns"),
    prevent_initial_call=True,
)
def download_data(n_clicks, filter_query, sort_by, hidden_columns: list = None):
    lff: pl.LazyFrame = lf  # start from the original data

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        lff = filter_table_data(lff, filter_query)

    if len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    def to_bytes(buffer):
        lff.collect(engine="streaming").write_excel(buffer, worksheet="DECP")

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.xlsx")
