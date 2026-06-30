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
                """Outil d'exploration libre et gratuit des données de marchés publics, développé par Colin Maudry.

Ce projet vise à démocratiser l'accès aux données des marchés publics et à un outil performant et gratuit. Si vous le trouvez utile
j'aimerais beaucoup échanger avec vous pour comprendre vos cas d'usages et vos besoins. Cet outil ne peut rester performant que si je comprends les problèmes qu'il peut aider à résoudre. Ce projet ne peut rester gratuit que grâce au financement du développement de nouvelles fonctionnalités.

En effet, le potentiel des données d'attribution de marchés et des données qui peuvent les enrichir est très loin d'être exploité par
les fonctionnalités actuelles de colibre. Il est ainsi possible de rajouter

- de nombreuses visualisations de données (cartes, graphiques, tableaux) sur des thématiques variées (vivacité de la concurrence, secteurs d'activité, insertion par l'activité économique (IAE), distance acheteur-titulaire...)
- des alertes par email si des marchés correspondant à certains critères
- ...et toutes les fonctionnalités auxquelles vous pourrez penser
"""
            ),
        ]
    )
    return apropos_shell("presentation", contenu)
