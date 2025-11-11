from dash import Input, Output, callback, dcc, html, register_page

from src.utils import meta_content

name = "Recherche"

register_page(
    __name__,
    path="/",
    title=meta_content["title"],
    name=name,
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=0,
)

layout = html.Div(
    className="container",
    children=[
        dcc.Input(
            id="search",
            type="text",
            placeholder="Nom d'acheteur, d'entreprise, mot de clé de marché...",
        ),
        html.Div(
            className="search_options",
            children=[dcc.RadioItems(options=["Acheteur(s)"])],
        ),
        html.Div(id="search_results"),
    ],
)


@callback(Output("search_results", "children"), Input("search", "value"))
def search_results(query):
    if len(query) >= 3:
        # results = []
        # dff = dff.select("acheteur_id", "acheteur_nom")
        return html.Div([])
    else:
        return html.P("Tapez au moins 3 caractères")
