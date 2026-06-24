from dash import Input, Output, callback, dcc, html, register_page

from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos",
    title="À propos | decp.info",
    name="À propos",
    description="En savoir plus sur decp.info, l'outil d'exploration des données essentielles de la commande publique.",
    image_url=META_CONTENT["image_url"],
    order=5,
)

_HASH_MAP = {
    "#donnees-brutes": "/a-propos/donnees-brutes",
    "#api-privee": "/a-propos/api-privee",
    "#contact": "/a-propos/contact",
    "#contribuer": "/a-propos/contribuer",
    "#explorer": "/a-propos/explorer",
    "#qualite-exhausitivite": "/a-propos/qualite",
    "#sources": "/a-propos/sources",
    "#mentions-legales": "/a-propos/mentions-legales",
    "#publication": "/a-propos/mentions-legales",
    "#audience": "/a-propos/mentions-legales",
    "#attributions": "/a-propos/mentions-legales",
    "#liste_marches": "/a-propos/mentions-legales",
}


def layout(**_):
    return html.Div(dcc.Location(id="apropos-redirect-loc"))


@callback(
    Output("apropos-redirect-loc", "href"),
    Input("apropos-redirect-loc", "hash"),
)
def _redirect(hash_val):
    return _HASH_MAP.get(hash_val or "", "/a-propos/presentation")
