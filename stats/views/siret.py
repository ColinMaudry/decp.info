from dash import html, dcc
import dash_bootstrap_components as dbc
import pandas as pd
from dash.dependencies import Input, Output
from app import app

SIRET = '20004525000012'

df_marches: pd.DataFrame = pd.read_csv(
    'https://decp.info/db/decp-sans-titulaires.csv?_sort=uid&acheteur.id__exact=20004525000012&_size=max&_dl=1',
    true_values=['oui'],
    false_values=['non'])
# df_marches = df_marches[df_marches['donneesActuelles'] == 'oui']
df_marches['anneeNotification'] = df_marches['dateNotification'].str[:4]


df_attributions: pd.DataFrame = pd.read_csv(
    f'https://decp.info/db/decp.csv?_sort=uid&acheteur.id__exact={SIRET}&_size=max&_dl=1',
    true_values=['oui'],
    false_values=['non'])
# df_attributions = df_attributions[df_attributions['donneesActuelles'] == 'oui']
df_attributions['anneeNotification'] = df_attributions['dateNotification'].str[:4]


def fn(input_number) -> str:
    return '{:,.0f}'.format(input_number).replace(',', ' ')


layout = html.Div(id='stats')


@app.callback(Output('stats', 'children'),
              Input('url', 'pathname'))
def generateYears(pathname) -> [dbc.Row]:
    siret = pathname.split('/')[2]
    print(siret)
    years = ['2022', '2021', '2020']
    result = [dbc.Row([
                html.H2('Par année')
            ])]
    for year in years:
        df_marches_year = df_marches[df_marches['anneeNotification'] == year]
        df_attributions_year = df_attributions[df_attributions['anneeNotification'] == year]
        row = dbc.Row([
            dbc.Col([
                dbc.Row([
                    html.H3(year),
                    html.A('Télécharger les données', href=f'https://decp.info/db/decp?_sort=rowid&dateNotification__'
                                                           f'startswith={year}&acheteur.id__exact={siret}')
                         ]),
                dbc.Row([
                    dbc.Col([
                        html.H4('Marchés attribués'),
                        html.P(df_marches_year.index.size)]),
                    dbc.Col([
                        html.H4('Montant total attribué'),
                        html.P(fn(df_marches_year['montant'].sum()) + ' euros')]),
                    dbc.Col([
                        html.H4('Titulaires différents'),
                        html.P(str(df_attributions_year['titulaire.id'].unique().size))])
                ])
            ])
        ])
        result.append(row)
    return result
