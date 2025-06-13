import logging
import os
from datetime import datetime
from time import sleep

import polars as pl
from dash import Input, Output, State, callback, dash_table, dcc, html, register_page
from dotenv import load_dotenv
from polars.exceptions import ComputeError

from src.utils import (
    add_annuaire_link,
    booleans_to_strings,
    format_number,
    numbers_to_strings,
    split_filter_part,
)

logger = logging.getLogger("decp.info")
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

load_dotenv()

# Chargement du fichier parquet
# Le fichier est chargé en mémoire, ce qui est plus rapide qu'une base de données pour le moment.
# On utilise polars pour la rapidité et la facilité de manipulation des données.

try:
    logger.info(
        f"Lecture du fichier parquet ({os.getenv('DATA_FILE_PARQUET_PATH')})..."
    )
    df: pl.DataFrame = pl.read_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))
except ComputeError:
    # Le fichier est probablement en cours de mise à jour
    logger.info("Échec, nouvelle tentative dans 10s...")
    sleep(seconds=10)
    df: pl.DataFrame = pl.read_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))

schema = df.schema
df_filtered = pl.DataFrame()
lf: pl.LazyFrame = df.lazy()

# Suppression des colonnes inutiles
lf = lf.drop(
    ["titulaire_siren", "acheteur_siren", "typeGroupementOperateurs", "sourceOpenData"]
)

# Convertir les colonnes booléennes en chaînes de caractères
lf = booleans_to_strings(lf)

# Remplacer les valeurs manquantes par des chaînes vides
lf = lf.fill_null("")


# Ajout des liens vers l'annuaire
lf = add_annuaire_link(lf)

title = "Tableau"
register_page(__name__, path="/", title="decp.info", name=title, order=1)

datatable = dash_table.DataTable(
    cell_selectable=False,
    id="table",
    page_size=20,
    page_current=0,
    page_action="custom",
    filter_action="custom",
    filter_options={"case": "insensitive", "placeholder_text": "Filtrer..."},
    columns=[
        {
            "name": i,
            "id": i,
            "presentation": "markdown",
            "type": "text",
            "format": {"nully": "N/A"},
        }
        for i in lf.collect_schema().names()
    ],
    selected_columns=[],
    selected_rows=[],
    # sort_action="native",
    # sort_mode="multi",
    # export_format="xlsx",
    # export_columns="visible",
    # export_headers="ids",
    style_cell_conditional=[
        {
            "if": {"column_id": "objet"},
            "minWidth": "350px",
            "textAlign": "left",
            "overflow": "hidden",
            "lineHeight": "14px",
            "whiteSpace": "normal",
        },
    ],
    data_timestamp=0,
    markdown_options={"html": True},
)

layout = [
    html.Div(
        html.Details(
            children=[
                html.Summary(html.H3("Mode d'emploi")),
                dcc.Markdown(
                    """

    **Filtres**

    Vous pouvez appliquer un filtre pour chaque colonne en entrant du texte sous le nom de la colonne, puis en tapant sur `Entrée`.

    - Champs textuels : la recherche est insensible à la casse (majuscules/minuscules).
    - Champs numériques : possibilité d'ajouter < ou > devant le chiffre recherché pour chercher des valeurs inférieures ou supérieur.

    Vous pouvez filtrer plusieurs colonnes à la fois. Vos filtres sont perdus quand vous rafraîchissez la page.

    **Télécharger le résultat**

    Vous pouvez télécharger le résultat de vos filtres en cliquant sur Télécharger au format Excel.

    Si vous téléchargez un volume important de données, il se peut que vous attendiez quelques minutes avant le début du téléchargement.
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
        id="loading-1",
        type="default",
        children=[
            html.Div(
                [
                    html.P("lignes", id="nb_rows"),
                    html.Button("Télécharger au format Excel", id="btn-download-data"),
                    dcc.Download(id="download-data"),
                ],
                className="table-menu",
            ),
            datatable,
        ],
    ),
]


@callback(
    Output("table", "data"),
    Output("table", "data_timestamp"),
    Output("nb_rows", "children"),
    Input("table", "page_current"),
    Input("table", "page_size"),
    Input("table", "filter_query"),
    State("table", "data_timestamp"),
)
def update_table(page_current, page_size, filter_query, data_timestamp):
    print(" + + + + + + + + + + + + + + + + + + ")
    global df_filtered

    # Application des filtres
    lff: pl.LazyFrame = lf  # start from the original data
    if filter_query:
        filtering_expressions = filter_query.split(" && ")
        for filter_part in filtering_expressions:
            col_name, operator, filter_value = split_filter_part(filter_part)
            col_type = str(schema[col_name])
            print("filter_value:", filter_value)
            print("filter_value_type:", type(filter_value))

            if operator in ("<", "<=", ">", ">="):
                filter_value = int(filter_value)
                if operator == "<":
                    lff = lff.filter(pl.col(col_name) < filter_value)
                elif operator == ">":
                    lff = lff.filter(pl.col(col_name) > filter_value)
                elif operator == ">=":
                    lff = lff.filter(pl.col(col_name) >= filter_value)
                elif operator == "<=":
                    lff = lff.filter(pl.col(col_name) <= filter_value)

            elif col_type.startswith("Int") or col_type.startswith("Float"):
                try:
                    filter_value = int(filter_value)
                except ValueError:
                    logger.error(f"Invalid numeric filter value: {filter_value}")
                    continue
                lff = lff.filter(pl.col(col_name) == filter_value)

            elif operator == "contains" and col_type == "String":
                lff = lff.filter(pl.col(col_name).str.contains("(?i)" + filter_value))

            # elif operator == 'datestartswith':
            # lff = lff.filter(pl.col(col_name).str.startswith(filter_value)")

    # Pagination des données
    start_row = page_current * page_size
    # end_row = (page_current + 1) * page_size

    # Remplacement des valeurs numériques par des chaînes de caractères
    lff = numbers_to_strings(lff)

    dff: pl.DataFrame = lff.collect()

    df_filtered = dff.clone()

    nb_rows = f"{format_number(dff.height)} lignes"
    dff = dff.slice(start_row, page_size)
    # print("dff_sliced:", lff.select("titulaire.typeId"))
    dicts = dff.to_dicts()

    return dicts, data_timestamp + 1, nb_rows


@callback(
    Output("download-data", "data"),
    Input("btn-download-data", "n_clicks"),
    prevent_initial_call=True,
)
def download_data(n_clicks):
    def to_bytes(buffer):
        df_filtered.write_excel(buffer, worksheet="DECP")

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.xlsx")
