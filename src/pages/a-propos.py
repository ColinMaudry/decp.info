import os

from dash import dcc, html, register_page

from src.figures import get_sources_tables
from src.utils import meta_content

name = "À propos"

register_page(
    __name__,
    path="/a-propos",
    title="À propos | decp.info",
    name="À propos",
    description="En savoir plus sur decp.info, l'outil d'exploration des données essentielles de la commande publique.",
    image_url=meta_content["image_url"],
    order=5,
)

layout = html.Div(
    className="container",
    children=[
        html.H2(name),
        html.Div(
            className="a-propos-container",
            children=[
                # Main Content Column
                html.Div(
                    className="a-propos-content",
                    children=[
                        dcc.Markdown(
                            """Outil d'exploration libre et gratuit des données de marchés publics, développé par Colin Maudry.

Ce projet vise à démocratiser l'accès aux données des marchés publics et à un outil performant et gratuit. Si vous le trouvez utile
j'aimerais beaucoup échanger avec vous pour comprendre vos cas d'usages et vos besoins. Cet outil ne peut rester performant que si je comprends les problèmes qu'il peut aider à résoudre. Ce projet ne peut rester gratuit que grâce au financement du développement de nouvelles fonctionnalités.

En effet, le potentiel des données d'attribution de marchés et des données qui peuvent les enrichir est très loin d'être exploité par
les fonctionnalités actuelles de decp.info. Il est ainsi possible de rajouter

- de nombreuses visualisations de données (cartes, graphiques, tableaux) sur des thématiques variées (vivacité de la concurrence, secteurs d'activité, insertion par l'activité économique (IAE), distance acheteur-titulaire...)
- des alertes par email si des marchés correspondant à certains critères
- ...et toutes les fonctionnalités auxquelles vous pourrez penser
"""
                        ),
                        html.H4("Consommer les données brutes", id="donnees-brutes"),
                        dcc.Markdown(
                            """
Vous pouvez consommer les données qui alimentent decp.info

- en les téléchargeant [sur data.gouv.fr](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire) (Parquet, CSV), pensez à lire la description du jeu de données
- en interrogeant l'[API REST ouverte](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire#user-content-api-rest)
"""
                        ),
                        html.H4("Contact", id="contact"),
                        dcc.Markdown(
                            """
- Email : [colin@colmo.tech](mailto:colin@colmo.tech)
- Bluesky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
- LinkedIn : [colinmaudry](https://www.linkedin.com/in/colinmaudry/)
"""
                        ),
                        html.H4("Pour contribuer", id="contribuer"),
                        dcc.Markdown(
                            """
- via l'achat d'une prestation de service (devis, prestation, facture), vous pouvez financer le développement de [fonctionnalités prévues](https://github.com/ColinMaudry/decp.info/issues), ou d'autres !
- ma société accepte aussi les dons (pas de réduction d'impôt possible)
- écrivez-moi et on discute !
"""
                        ),
                        html.H4("Pour explorer le projet", id="explorer"),
                        dcc.Markdown(
                            """
- ✉️  [inscription à la liste de diffusion](https://6254d9a3.sibforms.com/serve/MUIFAEonUVkoSVrdgey18CTgLyI16xw4yeu-M-YOUzhWE_AgfQfbgkyT7GvA_RYLro9MfuRqkzQxSvu7-uzbMSv2a2ZQPsliM7wtiiqIL8kR2zOvl6m11fb5qjcOxMAYsLiY_YBi3P7NY95CTJ8vRY4CpsDclF2iLooOElKkTgIgi5nePe7zAIrgiYM5v2EuALlGJZMEG9vBP-Cu) (annonces des mises à jour et évènements, maximum une fois par mois)
- 💾  [données consolidées en Open Data](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire/)
- 🗞️  [mon blog](https://colin.maudry.com)
- 📔  [wiki du projet](https://github.com/ColinMaudry/decp-processing/wiki)
- 🚰  code source
    - [de decp.info](https://github.com/ColinMaudry/decp.info)
    - [du traitement des données](https://github.com/ColinMaudry/decp-processing)
"""
                        ),
                        html.H4(
                            "Qualité et exhaustivité des données",
                            id="qualite-exhausitivite",
                        ),
                        dcc.Markdown(
                            """Les données visibles sur ce site proviennent exclusivement de la publication de données ouvertes par les acheteurs publics ou en leur nom, régie par [l'arrêté du 22 décembre 2022](https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000046850496). Leur qualité est donc principalement liée à la qualité de leur saisie par les agents publics, parfois peu aidé·es par la qualité des outils à leur disposition. Je pense que l'analyse de marchés individuels et le comptage de marchés sur des critères autres que financiers sont plutôt fiables. En revanche, certains montants de marché estimés à des valeurs farfelues ([1 euro](https://decp.info/marches/432766947000192025S01301), [1 milliard](https://decp.info/marches/2459004280001320210000000271)) faussent les calculs par aggrégation (sommes, moyennes, médianes) et donc la production de statistiques financières fiables. Acheteurs, acheteuses : s'il vous plaît, essayez d'estimer les montants des marchés publics attribués de manière plus précise.

Quant à l'exhaustivité, je consolide toutes les sources de données exploitables que j'ai pu identifier (voir [ci-dessous](/a-propos#sources). Certains profils d'acheteurs ne publient pas leurs données malgré l'obligation réglementaire :

- klekoon.fr (ils y travaillent)
- safetender.com (Omnikles)

**marches-publics.info** (AWS) publie ses données de manière assez sporadique depuis début 2023. Compte tenu de son poids dans le secteur, c'est assez dommageable pour la transparence des marchés publics.

Au milieu de ces mauvaises nouvelles, je tiens à souligner la belle continuité de la publication par la DGFiP des données des marchés publics remontées via le [protocole PES](https://www.collectivites-locales.gouv.fr/finances-locales/le-protocole-dechange-standard-pes). Merci à leurs équipes."""
                        ),
                        html.H4("Sources de données ", id="sources"),
                        get_sources_tables(os.getenv("SOURCE_STATS_CSV_PATH")),
                        html.H4("Mentions légales", id="mentions-legales"),
                        html.H5("Publication", id="publication"),
                        dcc.Markdown(
                            """
Site Web développé et édité par [SAS Colmo](https://annuaire-entreprises.data.gouv.fr/entreprise/colmo-989393350), 989 393 350 RCS Rennes au capital de 3 000 euros.

Siège social : 1 carrefour Jouaust, 35000 Rennes

Hébergement : serveur situé en France et administré par Scaleway, 8 rue de la Ville l’Evêque, 75008 Paris
"""
                        ),
                        html.H5("Suivi d'audience", id="audience"),
                        dcc.Markdown(
                            """
Ce site dépose un petit fichier texte (un « cookie ») sur votre ordinateur lorsque vous le consultez ([Wikipédia](https://fr.wikipedia.org/wiki/Cookie_(informatique))). Cela me permet de mesurer le nombre de visites, de distinguer les nouveaux visiteurs des utilisateurs réguliers et ainsi de communiquer sur l'impact de decp.info.

**Ce site n’affiche pas de bannière de consentement aux cookies, pourquoi ?**

C’est vrai, vous n’avez pas eu à cliquer sur un bloc qui recouvre la moitié de la page pour dire que vous êtes d’accord avec le dépôt de cookies.

Rien d’exceptionnel, je respecte simplement la loi, qui dit que certains outils de suivi d’audience, correctement configurés pour respecter la vie privée, sont exemptés d’autorisation préalable.

J’utilise pour cela [Matomo](https://matomo.org/), un outil [libre](https://matomo.org/free-software/), paramétré pour être en conformité avec [la recommandation « Cookies »](https://www.cnil.fr/fr/solutions-pour-les-cookies-de-mesure-daudience) de la CNIL. Cela signifie que votre adresse IP, par exemple, est anonymisée avant d’être enregistrée. Il m’est donc impossible d’associer vos visites sur ce site à votre personne.

J'enregistre également les données suivantes, de manière anonyme, afin de mieux comprendre comment vous utilisez le site et l'améliorer :

- recherches sur la page d'accueil
- filtres appliqués aux données
"""
                        ),
                        html.H5("Attributions", id="attributions"),
                        dcc.Markdown("""
                        Les polices de caractères sont distribuées par [Bunny fonts](https://fonts.bunny.net), une alternative européenne et qualitative à Google Fonts.

                        - la police de caractère [Inter](https://fonts.bunny.net/family/inter), principale police de ce site, a été créée par The Inter Project Authors ([source](https://github.com/rsms/inter))
                        - la police de caractère [Fira Code](https://fonts.bunny.net/family/fira-code), la police à largeure fixe, a été créée par The Fira Code Project Authors (https://github.com/tonsky/FiraCode)
                        """),
                        html.H4(
                            "Liste des marchés par département", id="liste_marches"
                        ),
                        dcc.Markdown(
                            """
                            - [Marchés par département](/departements)
                            """
                        ),
                    ],
                ),
                # Table of Contents Column
                html.Div(
                    className="a-propos-toc",
                    children=[
                        html.Div(
                            [
                                html.A(
                                    "Consommer les données brutes",
                                    href="#donnees-brutes",
                                    className="toc-link",
                                ),
                                html.A(
                                    "Contact", href="#contact", className="toc-link"
                                ),
                                html.A(
                                    "Pour contribuer",
                                    href="#contribuer",
                                    className="toc-link",
                                ),
                                html.A(
                                    "Pour explorer le projet",
                                    href="#explorer",
                                    className="toc-link",
                                ),
                                html.A(
                                    "Qualité et exhaustivité des données",
                                    href="#qualite-exhausitivite",
                                    className="toc-link",
                                ),
                                html.A(
                                    "Sources de données",
                                    href="#sources",
                                    className="toc-link",
                                ),
                                html.A(
                                    "Mentions légales",
                                    href="#mentions-legales",
                                    className="toc-link",
                                ),
                                html.A(
                                    "Publication",
                                    href="#publication",
                                    className="toc-link toc-level-2",
                                ),
                                html.A(
                                    "Suivi d'audience",
                                    href="#audience",
                                    className="toc-link toc-level-2",
                                ),
                                html.A(
                                    "Attributions",
                                    href="#attributions",
                                    className="toc-link toc-level-2",
                                ),
                            ]
                        ),
                    ],
                ),
            ],
        ),
    ],
)
