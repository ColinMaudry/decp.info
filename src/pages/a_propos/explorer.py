from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/explorer",
    title="Explorer le projet | À propos | colibre",
    description="Ressources pour explorer le projet colibre : données, code source, blog.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Pour explorer le projet"),
            dcc.Markdown(
                """
- ✉️  [inscription à la liste de diffusion](https://6254d9a3.sibforms.com/serve/MUIFAEonUVkoSVrdgey18CTgLyI16xw4yeu-M-YOUzhWE_AgfQfbgkyT7GvA_RYLro9MfuRqkzQxSvu7-uzbMSv2a2ZQPsliM7wtiiqIL8kR2zOvl6m11fb5qjcOxMAYsLiY_YBi3P7NY95CTJ8vRY4CpsDclF2iLooOElKkTgIgi5nePe7zAIrgiYM5v2EuALlGJZMEG9vBP-Cu) (annonces des mises à jour et évènements, maximum une fois par mois)
- 💾  [données consolidées en Open Data](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire/)
- 🗞️  [mon blog](https://colin.maudry.com)
- 📔  [wiki du projet](https://github.com/ColinMaudry/decp-processing/wiki)
- 🚰  code source
    - [de colibre](https://github.com/ColinMaudry/colibre)
    - [du traitement des données](https://github.com/ColinMaudry/decp-processing)
"""
            ),
        ]
    )
    return apropos_shell("explorer", contenu)
