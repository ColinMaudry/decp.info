import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.io as pio
from os import getenv

app = dash.Dash("trackdechets-public-stats", title='DECP.info : statistiques', external_stylesheets=[dbc.themes.GRID])
pio.templates.default = "none"

df_marches: pd.DataFrame = pd.read_csv(
    'https://decp.info/db/decp-sans-titulaires.csv?_sort=uid&acheteur.id__exact=20004525000012&_size=max&_dl=1',
    true_values=['oui'],
    false_values=['non'])
# df_marches = df_marches[df_marches['donneesActuelles'] == 'oui']
df_marches['anneeNotification'] = df_marches['dateNotification'].str[:4]


df_attributions: pd.DataFrame = pd.read_csv(
    'https://decp.info/db/decp.csv?_sort=uid&acheteur.id__exact=20004525000012&_size=max&_dl=1',
    true_values=['oui'],
    false_values=['non'])
# df_attributions = df_attributions[df_attributions['donneesActuelles'] == 'oui']
df_attributions['anneeNotification'] = df_attributions['dateNotification'].str[:4]


def generateYears(years: list) -> [dbc.Row]:
    result = []
    for year in years:
        print(year)
        df_marches_year = df_marches[df_marches['anneeNotification'] == year]
        df_attributions_year = df_attributions[df_attributions['anneeNotification'] == year]
        row = dbc.Row([
            dbc.Col([
                dbc.Row([html.H3(year)]),
                dbc.Row([
                    dbc.Col(html.P(df_marches_year.index.size)),
                    dbc.Col(html.P(str(df_marches_year['montant'].sum()) + ' euros')),
                    dbc.Col(html.P(str(df_attributions_year['titulaire.id'].unique().size)))
                ])
            ])
        ])
        result.append(row)
    return result


acheteur_years = generateYears(['2022', '2021', '2020'])
print(len(acheteur_years))
app.layout = html.Div(children=[
    dbc.Row([
                html.H2('Par année')
            ])

] + acheteur_years)


if __name__ == '__main__':
    port = getenv('PORT', 8050)

    # Scalingo requires 0.0.0.0 as host, instead of the default 127.0.0.1
    app.run_server(debug=bool(getenv('DEVELOPMENT')), host='0.0.0.0', port=int(port))
