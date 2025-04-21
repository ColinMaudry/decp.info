from dash import (
    Dash,
    html,
    dcc,
    callback,
    Output,
    Input,
    dash_table,
    page_container,
    register_page,
)
from dotenv import load_dotenv
import os
import polars as pl

load_dotenv()

df = pl.read_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))

title = "Tableau"
register_page(__name__, path="/", title=f"decp.info - {title}", name=title, order=1)

datatable = dash_table.DataTable(
    cell_selectable=False,
    id="table",
    data=df.to_dicts(),
    page_size=20,
    page_current=0,
    page_action="native",
    filter_action="native",
    filter_options={"case": "insensitive", "placeholder_text": "Filtrer..."},
    columns=[
        {"name": i, "id": i, "deletable": True, "selectable": False} for i in df.columns
    ],
    selected_columns=[],
    selected_rows=[],
    sort_action="native",
    sort_mode="multi",
    export_format="xlsx",
    export_columns="visible",
    export_headers="ids",
    style_cell_conditional=[
        {
            "if": {"column_id": "objet"},
            "minWidth": "300px",
            "textAlign": "left",
            "overflow": "hidden",
            "lineHeight": "14px",
            "whiteSpace": "normal",
        },
    ],
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

    **Télécharger le résultat**

    Vous pouvez télécharger le résultat de vos filtres et tris en cliquant sur Télécharger au format Excel.

    Les colonnes supprimées seront absentes du fichier téléchargé.

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
