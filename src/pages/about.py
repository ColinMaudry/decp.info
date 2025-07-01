from dash import dcc, html, register_page

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
                """Outil d'exploration des [Données Essentielles de la Commande Publique](), développé par Colin Maudry, sous licence GPL v3 (libre et gratuit).

Ce projet vise à démocratiser l'accès aux données des marchés publics et à un outil performant et gratuit. Si vous le trouvez utile
j'aimerais beaucoup échanger avec vous pour comprendre vos cas d'usages et vos besoins. Cet outil ne peut rester performant que si je comprends les problèmes qu'il peut aider à résoudre. Ce projet ne peut rester gratuit que grâce au financement du développement de nouvelles fonctionnalités.

En effet, le potentiel des données d'attribution de marchés et des données qui peuvent les enrichir est très loin d'être exploité par
les fonctionnalités actuelles de decp.info. Il est ainsi possible de rajouter

- de nombreuses visualisations de données (cartes, graphiques, tableaux) sur des thématiques variées (vivacité de la concurrence, secteurs d'activité, insertion par l'activité économique (IAE), distance acheteur-fournisseur...)
- la sauvegarde de filtre pour les retrouver plus tard et les partager
- des alertes par email si des marchés correspondant à certains critères
- le développement d'une API pour alimenter d'autres logiciels
- ...et toutes les fonctionnalités auxquelles vous pourrez penser :)

#### Pour aller plus loin

- [wiki du projet](https://github.com/ColinMaudry/decp-processing/wiki)
- [code source de decp.info](https://github.com/ColinMaudry/decp.info)
- [code source du traitement des données](https://github.com/ColinMaudry/decp-processing)

#### Contact

- venez discuter de la transparence de la commande publique [sur le forum teamopendata.org](https://teamopendata.org/c/commande-publique/101)
- [colin+decp@maudry.com](mailto:colin+decp@maudry.com)
- Bluesky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
- LinkedIn : [colinmaudry](https://www.linkedin.com/in/colinmaudry/)
"""
            ),
        ],
    )
]
