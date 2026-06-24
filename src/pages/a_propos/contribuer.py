from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/contribuer",
    title="Contribuer | À propos | decp.info",
    description="Comment contribuer au projet decp.info.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Pour contribuer"),
            dcc.Markdown(
                """
- via l'achat d'une prestation de service (devis, prestation, facture), vous pouvez financer le développement de [fonctionnalités prévues](https://github.com/ColinMaudry/decp.info/issues), ou d'autres !
- ma société accepte aussi les dons (pas de réduction d'impôt possible)
- écrivez-moi et on discute !
"""
            ),
        ]
    )
    return apropos_shell("contribuer", contenu)
