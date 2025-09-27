from dash import html, register_page

register_page(
    __name__,
    path_template="/fournisseur/<acheteur_id>",
    title="decp.info - fournisseur",
    name="Fournisseur",
    order=5,
)

layout = [
    html.Div(className="container", children=["Cette page est encore en construction."])
]
