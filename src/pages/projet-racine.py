from dash import Input, Output, callback, dcc, html, register_page

from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/projet",
    title="Le projet | colibre",
    name="Le projet",
    description="En savoir plus sur colibre, l'outil d'exploration des données essentielles de la commande publique.",
    image_url=META_CONTENT["image_url"],
    order=5,
)

_HASH_MAP = {
    "#donnees-brutes": "/projet/donnees#donnees-brutes",
    "#api-privee": "/projet/donnees#donnees-brutes",
    "#contact": "/projet/contact",
    "#explorer": "/projet/explorer",
    "#qualite-exhausitivite": "/projet/donnees#qualite",
    "#sources": "/projet/donnees#sources",
    "#mentions-legales": "/projet/mentions-legales",
    "#publication": "/projet/mentions-legales#publication",
    "#audience": "/projet/mentions-legales#audience",
    "#attributions": "/projet/mentions-legales#attributions",
    "#liste_marches": "/projet/mentions-legales#liste_marches",
}


def layout(**_):
    return html.Div(dcc.Location(id="apropos-redirect-loc"))


@callback(
    Output("apropos-redirect-loc", "href"),
    Input("apropos-redirect-loc", "hash"),
)
def _redirect(hash_val):
    return _HASH_MAP.get(hash_val or "", "/projet/presentation")
