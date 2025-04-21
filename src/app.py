from dash import Dash, html, dcc, callback, Output, Input, dash_table
import polars as pl
import dash_bootstrap_components as dbc

df = pl.read_parquet("/home/colin/git/decp-processing/dist/2025-04-21/decp.parquet")

app = Dash(external_stylesheets=[dbc.themes.UNITED], title="decp.info")
server = app.server

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

app.layout = [
    html.H1(children="decp.info"),
    html.Details(
        children=[
            html.Summary("Utilisation"),
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
    html.Div(
        [
            "Recherche dans objet : ",
            dcc.Input(id="search", value="", type="text"),
        ]
    ),
    dcc.Loading(
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        id="loading-1",
        type="default",
        children=datatable,
    ),
]


@callback(
    Output(component_id="table", component_property="data", allow_duplicate=True),
    Input(component_id="search", component_property="value"),
    prevent_initial_call=True,
)
def global_search(text):
    new_df = df
    new_df = new_df.filter(pl.col("objet").str.contains("(?i)" + text))
    return new_df.to_dicts()


# @callback(
#     Output("table", "data"), Input("table", "page_current"), Input("table", "page_size")
# )
# def update_table(page_current, page_size):
#     return df[page_current * page_size : (page_current + 1) * page_size].to_dicts()


if __name__ == "__main__":
    app.run(debug=True)
