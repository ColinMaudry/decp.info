from dash import Dash, html, dcc, callback, Output, Input, dash_table
import plotly.express as px
import polars as pl

df = pl.read_parquet(
    "https://www.data.gouv.fr/fr/datasets/r/11cea8e8-df3e-4ed1-932b-781e2635e432"
)

app = Dash()

app.layout = [
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
    Output("table", "data"), Input("table", "page_current"), Input("table", "page_size")
)
def update_table(page_current, page_size):
    return df[page_current * page_size : (page_current + 1) * page_size].to_dicts()


if __name__ == "__main__":
    app.run(debug=True)
