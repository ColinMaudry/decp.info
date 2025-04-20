from dash import Dash, html, dcc, callback, Output, Input, dash_table
import plotly.express as px
import polars as pl
import dash_bootstrap_components as dbc

df = pl.read_ipc("/home/colin/git/decp-processing/dist/decp.arrow")

app = Dash(external_stylesheets=[dbc.themes.UNITED])
server = app.server

app.layout = [
    html.Div(
        [
            "Recherche (acheteur, titulaire, objet) : ",
            dcc.Input(id="search", value="", type="text"),
        ]
    ),
    html.H1(children="decp.info", style={"textAlign": "center"}),
    dash_table.DataTable(
        id="table",
        data=df.to_dicts(),
        page_size=20,
        page_current=0,
        page_action="native",
        filter_action="native",
        columns=[
            {"name": i, "id": i, "deletable": True, "selectable": True}
            for i in df.columns
        ],
        selected_columns=[],
        selected_rows=[],
        sort_action="native",
        sort_mode="multi",
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
