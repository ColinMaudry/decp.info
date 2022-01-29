import dash
import dash_bootstrap_components as dbc

app = dash.Dash("trackdechets-public-dash", title='DECP.info : statistiques',
                external_stylesheets=[dbc.themes.GRID], suppress_callback_exceptions=True)
server = app.server
