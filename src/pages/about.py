import os

from dash import dcc, html, register_page
from dotenv import load_dotenv

from src.figures import get_sources_tables

title = "À propos"

load_dotenv()

register_page(
    __name__, path="/a-propos", title=f"decp.info - {title}", name=title, order=5
)

layout = [
    html.Div(
        className="container",
        children=[
            html.H2(title),
            dcc.Markdown(
                """Outil d'exploration libre et gratuit des [Données Essentielles de la Commande Publique](), développé par Colin Maudry.

Ce projet vise à démocratiser l'accès aux données des marchés publics et à un outil performant et gratuit. Si vous le trouvez utile
j'aimerais beaucoup échanger avec vous pour comprendre vos cas d'usages et vos besoins. Cet outil ne peut rester performant que si je comprends les problèmes qu'il peut aider à résoudre. Ce projet ne peut rester gratuit que grâce au financement du développement de nouvelles fonctionnalités.

En effet, le potentiel des données d'attribution de marchés et des données qui peuvent les enrichir est très loin d'être exploité par
les fonctionnalités actuelles de decp.info. Il est ainsi possible de rajouter

- de nombreuses visualisations de données (cartes, graphiques, tableaux) sur des thématiques variées (vivacité de la concurrence, secteurs d'activité, insertion par l'activité économique (IAE), distance acheteur-fournisseur...)
- la sauvegarde de filtre pour les retrouver plus tard et les partager
- des alertes par email si des marchés correspondant à certains critères
- le développement d'une API pour alimenter d'autres logiciels
- ...et toutes les fonctionnalités auxquelles vous pourrez penser :)

   """
            ),
            html.H4("Pour contribuer", id="contribuer"),
            dcc.Markdown("""
- via l'achat d'un prestation de service (devis, prestation, facture), vous pouvez financer le développement de [fonctionnalités prévues](https://github.com/ColinMaudry/decp.info/issues), ou d'autres !
- ma société accepte aussi les dons (pas de réduction d'impôt possible)
- envoyez un mail et on discute !

#### Pour explorer le projet

- ✉️  [inscription à la liste de diffusion](https://6254d9a3.sibforms.com/serve/MUIFAEonUVkoSVrdgey18CTgLyI16xw4yeu-M-YOUzhWE_AgfQfbgkyT7GvA_RYLro9MfuRqkzQxSvu7-uzbMSv2a2ZQPsliM7wtiiqIL8kR2zOvl6m11fb5qjcOxMAYsLiY_YBi3P7NY95CTJ8vRY4CpsDclF2iLooOElKkTgIgi5nePe7zAIrgiYM5v2EuALlGJZMEG9vBP-Cu) (annonces des mises à jour et évènements, maximum une fois par mois)
- 📔  [wiki du projet](https://github.com/ColinMaudry/decp-processing/wiki)
- 🚰  code source
    - [de decp.info](https://github.com/ColinMaudry/decp.info)
    - [du traitement des données](https://github.com/ColinMaudry/decp-processing)
    """),
            html.H4("Contact", id="contact"),
            dcc.Markdown("""
- Email : [colin+decp@maudry.com](mailto:colin+decp@maudry.com)
- venez discuter de la transparence de la commande publique [sur le forum teamopendata.org](https://teamopendata.org/c/commande-publique/101)
- Bluesky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
- LinkedIn : [colinmaudry](https://www.linkedin.com/in/colinmaudry/)
"""),
            html.H4("Sources de données", id="sources"),
            get_sources_tables(os.getenv("SOURCE_STATS_CSV_PATH")),
            html.H4("Mentions légales", id="mentions-legales"),
            dcc.Markdown("""
    Site Web développé et édité par [SAS Colmo](https://annuaire-entreprises.data.gouv.fr/entreprise/colmo-989393350), 989 393 350 RCS Rennes au capital de 3 000 euros.

    Siège social : 1 carrefour Jouaust, 35000 Rennes

    Hébergement : serveur situé en France et administré par Scaleway, 8 rue de la Ville l’Evêque, 75008 Paris
    """),
        ],
    )
]
