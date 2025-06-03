from time import sleep

from narwhals.exceptions import ComputeError
from dash import html, dcc, dash_table, register_page, Input, Output, State, callback
from dotenv import load_dotenv
import os
import polars as pl
from polars.exceptions import ComputeError
from src.utils import split_filter_part, add_annuaire_link
import logging

logger = logging.getLogger("decp.info")
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

load_dotenv()

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

df: pl.LazyFrame = df.lazy()

# Ajout des liens vers l'annuaire
df = add_annuaire_link(df)

title = "Tableau"
register_page(__name__, path="/", title=f"decp.info - {title}", name=title, order=1)

datatable = dash_table.DataTable(
    cell_selectable=False,
    id="table",
    page_size=20,
    page_current=0,
    page_action="custom",
    filter_action="custom",
    filter_options={"case": "insensitive", "placeholder_text": "Filtrer..."},
    columns=[
        {"name": i, "id": i, "presentation": "markdown"}
        for i in df.collect_schema().names()
    ],
    selected_columns=[],
    selected_rows=[],
    # sort_action="native",
    # sort_mode="multi",
    export_format="xlsx",
    export_columns="visible",
    export_headers="ids",
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
                html.Summary(html.H3("Utilisation")),
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
        children=datatable,
    ),
]


@callback(
    Output("table", "data"),
    Output("table", "data_timestamp"),
    Input("table", "page_current"),
    Input("table", "page_size"),
    Input("table", "filter_query"),
    State("table", "data_timestamp"),
)
def update_table(page_current, page_size, filter_query, data_timestamp):
    print(" + + + + + + + + + + + + + + + + + + ")
    print("Filter query:", filter_query)
    # 1. Apply Filters
    dff = df  # start from the original data
    if filter_query:
        filtering_expressions = filter_query.split(" && ")
        for filter_part in filtering_expressions:
            col_name, operator, filter_value = split_filter_part(filter_part)
            print("filter_value:", filter_value)
            print("filter_value_type:", type(filter_value))

            if operator in ("<", "<=", ">", ">="):
                filter_value = int(filter_value)
                if operator == "<":
                    dff = dff.filter(pl.col(col_name) < filter_value)
                elif operator == ">":
                    dff = dff.filter(pl.col(col_name) > filter_value)
                elif operator == ">=":
                    dff = dff.filter(pl.col(col_name) >= filter_value)
                elif operator == "<=":
                    dff = dff.filter(pl.col(col_name) <= filter_value)
                # these operators match polars series filter operators

            elif operator == "contains":
                dff = dff.filter(pl.col(col_name).str.contains("(?i)" + filter_value))
            # elif operator == 'datestartswith':
            # dff = dff.filter(pl.col(col_name).str.startswith(filter_value)")

    # 2. Paginate Data
    start_row = page_current * page_size
    # end_row = (page_current + 1) * page_size

    dff = dff.slice(start_row, page_size).collect()
    # print("dff_sliced:", dff.select("titulaire.typeId"))
    dff = dff.to_dicts()

    return dff, data_timestamp + 1  # update data, update timestamp
