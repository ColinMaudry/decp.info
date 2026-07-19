from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/presentation",
    title="Présentation | À propos | colibre",
    description="En savoir plus sur colibre, l'outil d'exploration des données essentielles de la commande publique.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Présentation"),
            dcc.Markdown(
                """Outil d'exploration libre des données de marchés publics, développé par Colin Maudry via la société [Colmo](https://annuaire-entreprises.data.gouv.fr/entreprise/colmo-989393350).

Ce projet vise à démocratiser l'accès aux données des marchés publics dans un outil performant en grande partie gratuit.
Si vous le trouvez utile, [envoyez un message](/a-propos/contact) pour exposer vos cas d'usages et vos besoins. Cet outil ne peut rester
performant qu'avec la connaissance des problèmes à résoudre.
Ce projet est financé par ses [abonné·es](/a-propos/abonnement) et par des missions de conseil et de développement.
"""
            ),
        ]
    )
    return apropos_shell("presentation", contenu)
