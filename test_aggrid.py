import dash_ag_grid as dag
import pandas as pd
from dash import Dash, html

df = pd.read_csv(
    "https://raw.githubusercontent.com/plotly/datasets/master/gapminder2007.csv"
)

app = Dash()

columnDefs = [
    {"field": "country", "filter": True},
    {"field": "pop", "headerName": "Population"},
    {"field": "lifeExp", "headerName": "Life Expectancy", "filter": True},
]

grid = dag.AgGrid(
    id="getting-started-filter",
    rowData=df.to_dict("records"),
    columnDefs=columnDefs,
)

app.layout = html.Div([grid])

if __name__ == "__main__":
    app.run(debug=True)
