from dash import Input, Output, callback, dcc, html, register_page

from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos",
    title="À propos | colibre",
    name="À propos",
    description="En savoir plus sur colibre, l'outil d'exploration des données essentielles de la commande publique.",
    image_url=META_CONTENT["image_url"],
    order=5,
)

_HASH_MAP = {
    "#donnees-brutes": "/a-propos/donnees#donnees-brutes",
    "#api-privee": "/a-propos/donnees#donnees-brutes",
    "#contact": "/a-propos/contact",
    "#explorer": "/a-propos/explorer",
    "#qualite-exhausitivite": "/a-propos/donnees#qualite",
    "#sources": "/a-propos/donnees#sources",
    "#mentions-legales": "/a-propos/mentions-legales",
    "#publication": "/a-propos/mentions-legales#publication",
    "#audience": "/a-propos/mentions-legales#audience",
    "#attributions": "/a-propos/mentions-legales#attributions",
    "#liste_marches": "/a-propos/mentions-legales#liste_marches",
}


def layout(**_):
    return html.Div(dcc.Location(id="apropos-redirect-loc"))


@callback(
    Output("apropos-redirect-loc", "href"),
    Input("apropos-redirect-loc", "hash"),
)
def _redirect(hash_val):
    return _HASH_MAP.get(hash_val or "", "/a-propos/presentation")
