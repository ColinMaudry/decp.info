import dash
from dash import Input, Output, callback, dcc, html, register_page

register_page(
    __name__,
    path_template="/acheteur/<acheteur_id>",
    title="decp.info - acheteur",
    name="Acheteur",
    order=5,
)

# 21690123100011

print(dash.page_registry["pages.acheteur"])

layout = [
    dcc.Location(id="url", refresh="callback-nav"),
    html.Div(
        className="container",
        children=[
            html.H2(id="acheteur_title", children=""),
        ],
    ),
]


@callback(
    Output(component_id="acheteur_title", component_property="children"),
    Input(component_id="url", component_property="pathname"),
)
def update_acheteur(url):
    acheteur_siret = url.split("/")[-1]
    acheteur_title = acheteur_siret

    return acheteur_title
