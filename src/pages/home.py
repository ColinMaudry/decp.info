import os
from datetime import datetime

import polars as pl
from dash import Input, Output, State, callback, dash_table, dcc, html, register_page
from dotenv import load_dotenv

from src.utils import (
    add_annuaire_link,
    booleans_to_strings,
    format_number,
    lf,
    logger,
    split_filter_part,
)

load_dotenv()

schema = lf.collect_schema()
update_date = os.path.getmtime(os.getenv("DATA_FILE_PARQUET_PATH"))
update_date = datetime.fromtimestamp(update_date).strftime("%d/%m/%Y")
df_filtered = pl.DataFrame()

# Unique les données actuelles, pas les anciennes versions de marchés

lf = lf.filter(pl.col("donneesActuelles"))

# Suppression des colonnes inutiles
lf = lf.drop(
    [
        "titulaire_siren",
        "acheteur_siren",
        "typeGroupementOperateurs",
        "sourceOpenData",
        "donneesActuelles",
    ]
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

    dff: pl.DataFrame = lff.collect()

    df_filtered = dff.clone()

    nb_rows = f"{format_number(dff.height)} lignes"

    # Pagination des données
    start_row = page_current * page_size
    # end_row = (page_current + 1) * page_size
    dff = dff.slice(start_row, page_size)
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
