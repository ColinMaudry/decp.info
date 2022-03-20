from dash import html, dcc
import plotly.io as pio
from os import getenv
from app import app
from dash.dependencies import Input, Output
from views import siret

pio.templates.default = "none"


app.layout = html.Div([
    dcc.Store(id='memory'),
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content'),
    html.Div(id='debug')
])


@app.callback(Output('page-content', 'children'),
              # Output('debug', 'children'),
              Input('url', 'pathname'))
def display_page(pathname):

    if pathname.startswith('/siret/'):
        return [siret.layout]
    else:
        return ['Page inconnue...', pathname]


if __name__ == '__main__':
    port = getenv('PORT', 8050)
    app.run_server(debug=True, host='0.0.0.0', port=int(port))
