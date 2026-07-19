from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/mentions-legales",
    title="Mentions légales | À propos | colibre",
    description="Mentions légales de colibre : éditeur, hébergement, suivi d'audience, attributions.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Mentions légales"),
            html.H4("Publication", id="publication"),
            dcc.Markdown(
                """
Site Web développé et administré par [SAS Colmo](https://annuaire-entreprises.data.gouv.fr/entreprise/colmo-989393350), 989 393 350 RCS Rennes au capital de 3 000 euros, société présidée par Colin Maudry.

Siège social : 1 carrefour Jouaust, 35000 Rennes

Hébergement : serveur situé en France et administré par Scaleway, 8 rue de la Ville l'Evêque, 75008 Paris
"""
            ),
            html.H4("Suivi d'audience", id="audience"),
            dcc.Markdown(
                """
Ce site dépose un petit fichier texte (un « cookie ») sur votre ordinateur lorsque vous le consultez ([Wikipédia](https://fr.wikipedia.org/wiki/Cookie_(informatique))). Cela me permet de mesurer le nombre de visites, de distinguer les nouveaux visiteurs des utilisateurs réguliers et ainsi de communiquer sur l'impact de colibre.

**Ce site n'affiche pas de bannière de consentement aux cookies, pourquoi ?**

C'est vrai, vous n'avez pas eu à cliquer sur un bloc qui recouvre la moitié de la page pour dire que vous êtes d'accord avec le dépôt de cookies.

Rien d'exceptionnel, ce site respecte simplement la loi, qui dit que certains outils de suivi d'audience, correctement configurés pour respecter la vie privée, sont exemptés d'autorisation préalable.

L'outil utilisé pour le suivi d'audience est [Matomo](https://matomo.org/), un [logiciel libre](https://matomo.org/free-software/), paramétré pour être en conformité avec [la recommandation « Cookies »](https://www.cnil.fr/fr/solutions-pour-les-cookies-de-mesure-daudience) de la CNIL. Cela signifie que votre adresse IP, par exemple, est anonymisée avant d'être enregistrée. Il m'est donc impossible d'associer vos visites sur ce site à votre personne.

Les données suivantes sont également enregistrées, de manière anonyme, afin de mieux comprendre comment vous utilisez le site et l'améliorer :

- recherches sur la page d'accueil
- filtres appliqués aux données
"""
            ),
            html.H4("Attributions", id="attributions"),
            dcc.Markdown(
                """
Les polices de caractères sont distribuées par [Bunny fonts](https://fonts.bunny.net), une alternative européenne et qualitative à Google Fonts.

- la police de caractère [Inter](https://fonts.bunny.net/family/inter), principale police de ce site, a été créée par The Inter Project Authors ([source](https://github.com/rsms/inter))
- la police de caractère [Fira Code](https://fonts.bunny.net/family/fira-code), la police à largeure fixe, a été créée par The Fira Code Project Authors (https://github.com/tonsky/FiraCode)
"""
            ),
            html.H4("Marchés par département", id="liste_marches"),
            dcc.Markdown("- [Marchés par département](/departements)"),
        ]
    )
    return apropos_shell("mentions-legales", contenu)
