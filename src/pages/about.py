import os

from dash import dcc, html, register_page

from src.figures import get_sources_tables

title = "À propos"

register_page(
    __name__, path="/a-propos", title=f"decp.info - {title}", name=title, order=5
)

layout = [
    html.Div(
        className="container",
        children=[
            html.H2(title),
            dcc.Markdown(
                """Outil d'exploration libre et gratuit des données de marchés publics, développé par Colin Maudry.

Ce projet vise à démocratiser l'accès aux données des marchés publics et à un outil performant et gratuit. Si vous le trouvez utile
j'aimerais beaucoup échanger avec vous pour comprendre vos cas d'usages et vos besoins. Cet outil ne peut rester performant que si je comprends les problèmes qu'il peut aider à résoudre. Ce projet ne peut rester gratuit que grâce au financement du développement de nouvelles fonctionnalités.

En effet, le potentiel des données d'attribution de marchés et des données qui peuvent les enrichir est très loin d'être exploité par
les fonctionnalités actuelles de decp.info. Il est ainsi possible de rajouter

- de nombreuses visualisations de données (cartes, graphiques, tableaux) sur des thématiques variées (vivacité de la concurrence, secteurs d'activité, insertion par l'activité économique (IAE), distance acheteur-fournisseur...)
- la sauvegarde de filtres pour les retrouver plus tard et les partager
- des alertes par email si des marchés correspondant à certains critères
- le développement d'une API pour alimenter d'autres logiciels
- ...et toutes les fonctionnalités auxquelles vous pourrez penser
   """
            ),
            html.H4("Pour contribuer", id="contribuer"),
            dcc.Markdown("""
- via l'achat d'une prestation de service (devis, prestation, facture), vous pouvez financer le développement de [fonctionnalités prévues](https://github.com/ColinMaudry/decp.info/issues), ou d'autres !
- ma société accepte aussi les dons (pas de réduction d'impôt possible)
- envoyez un mail et on discute !

#### Pour explorer le projet

- ✉️  [inscription à la liste de diffusion](https://6254d9a3.sibforms.com/serve/MUIFAEonUVkoSVrdgey18CTgLyI16xw4yeu-M-YOUzhWE_AgfQfbgkyT7GvA_RYLro9MfuRqkzQxSvu7-uzbMSv2a2ZQPsliM7wtiiqIL8kR2zOvl6m11fb5qjcOxMAYsLiY_YBi3P7NY95CTJ8vRY4CpsDclF2iLooOElKkTgIgi5nePe7zAIrgiYM5v2EuALlGJZMEG9vBP-Cu) (annonces des mises à jour et évènements, maximum une fois par mois)
- 💾  [données consolidées en Open Data](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire/)
- 🗞️  [mon blog](https://colin.maudry.com), qui parle beaucoup de transparence des marchés publics
- 📔  [wiki du projet](https://github.com/ColinMaudry/decp-processing/wiki)
- 🚰  code source
    - [de decp.info](https://github.com/ColinMaudry/decp.info)
    - [du traitement des données](https://github.com/ColinMaudry/decp-processing)
    """),
            html.H4("Contact", id="contact"),
            dcc.Markdown("""
- Email : [colin+decp@maudry.com](mailto:colin+decp@maudry.com)
- Bluesky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
- LinkedIn : [colinmaudry](https://www.linkedin.com/in/colinmaudry/)
- venez discuter de la transparence de la commande publique [sur le forum teamopendata.org](https://teamopendata.org/c/commande-publique/101)
"""),
            html.H4("Sources de données", id="sources"),
            get_sources_tables(os.getenv("SOURCE_STATS_CSV_PATH")),
            html.H4("Mentions légales", id="mentions-legales"),
            dcc.Markdown("""
##### Publication

Site Web développé et édité par [SAS Colmo](https://annuaire-entreprises.data.gouv.fr/entreprise/colmo-989393350), 989 393 350 RCS Rennes au capital de 3 000 euros.

Siège social : 1 carrefour Jouaust, 35000 Rennes

Hébergement : serveur situé en France et administré par Scaleway, 8 rue de la Ville l’Evêque, 75008 Paris

##### Suivi d'audience

Ce site dépose un petit fichier texte (un « cookie ») sur votre ordinateur lorsque vous le consultez ([Wikipédia](https://fr.wikipedia.org/wiki/Cookie_(informatique))). Cela me permet de mesurer le nombre de visites, de distinguer les nouveaux visiteurs des utilisateurs réguliers et ainsi de communiquer sur l'impact de decp.info.

**Ce site n’affiche pas de bannière de consentement aux cookies, pourquoi ?**

C’est vrai, vous n’avez pas eu à cliquer sur un bloc qui recouvre la moitié de la page pour dire que vous êtes d’accord avec le dépôt de cookies.

Rien d’exceptionnel, je respecte simplement la loi, qui dit que certains outils de suivi d’audience, correctement configurés pour respecter la vie privée, sont exemptés d’autorisation préalable.

J’utilise pour cela [Matomo](https://matomo.org/), un outil [libre](https://matomo.org/free-software/), paramétré pour être en conformité avec [la recommandation « Cookies »](https://www.cnil.fr/fr/solutions-pour-les-cookies-de-mesure-daudience) de la CNIL. Cela signifie que votre adresse IP, par exemple, est anonymisée avant d’être enregistrée. Il m’est donc impossible d’associer vos visites sur ce site à votre personne."""),
            # Matomo propose cependant ce formulaire si vous souhaitez totalement désactiver le suivi de vos sessions sur ce site :"""),
            #             html.Div(
            #                 id="matomo-opt-out",
            #                 style={
            #                     "border": "1pt solid lightgrey",
            #                     "padding": "12px",
            #                     "margin": "auto 0 auto 12px",
            #                     "width": "80%",
            #                 },
            #                 children=["Vous utilisez un bloqueur de suivi de trafic."],
            #             ),
            #             html.Script(
            #                 src="https://analytics.maudry.com/index.php?module=CoreAdminHome&action=optOutJS&divId=matomo-opt-out&language=auto&showIntro=1"
            #             ),
        ],
    )
]
