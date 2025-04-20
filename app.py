from dash import Dash, html, dcc, callback, Output, Input, dash_table
import polars as pl
import dash_bootstrap_components as dbc

df = pl.read_parquet(
    "https://www.data.gouv.fr/fr/datasets/r/11cea8e8-df3e-4ed1-932b-781e2635e432"
)

app = Dash(external_stylesheets=[dbc.themes.UNITED], title="decp.info")
server = app.server

datatable = dash_table.DataTable(
    id="table",
    data=df.to_dicts(),
    page_size=20,
    page_current=0,
    page_action="native",
    # filter_action="native",
    columns=[
        {"name": i, "id": i, "deletable": True, "selectable": True} for i in df.columns
    ],
    selected_columns=[],
    selected_rows=[],
    sort_action="native",
    sort_mode="multi",
)

app.layout = [
    html.H1(children="decp.info", style={"textAlign": "center"}),
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


@callback(
    Output("table", "data"), Input("table", "page_current"), Input("table", "page_size")
)
def update_table(page_current, page_size):
    return df[page_current * page_size : (page_current + 1) * page_size].to_dicts()


if __name__ == "__main__":
    app.run(debug=True)
