import os

from dash import dcc, html, register_page

from src.figures import get_duplicate_matrix, get_sources_tables
from src.pages._apropos_shell import apropos_shell
from src.pages.etapes import build_chart, build_mobile
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/donnees",
    title="Données | À propos | colibre",
    description="Données brutes, qualité des données et sources utilisées par colibre pour consolider les marchés publics français.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            dcc.Markdown(
                """
Les données présentées sur ce site sont publiées par les acheteurs publics dans le cadre de la réglementation DECP (Données Essentielles de la Commande Publique).
Ces données couvrent principalement l'étape d'attribution des marchés publics, qui suit l'étape de publicité (l'appel d'offres).

**Données publiées par étape de passsation du marché et par seuil selon la valeur du marché** :

"""
            ),
            build_mobile(),
            build_chart(),
            html.H2("Consommer les données brutes"),
            dcc.Markdown("""
Vous pouvez consommer les données qui alimentent colibre en les téléchargeant
[sur data.gouv.fr](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire) (Parquet, CSV),
pensez à lire la description du jeu de données

Une API REST tabulaire (JSON) est également disponible par abonnement mensuel pour accéder aux mêmes données et alimenter une application.
Documentation interactive : [Swagger UI](/api/v1/swagger). Si cela vous intéresse, [envoyez un message](/a-propos/contact)."""),
            html.H2("Qualité et exhaustivité des données", className="mt-4"),
            dcc.Markdown(
                """Les données visibles sur ce site proviennent exclusivement de la publication de données
                ouvertes par les acheteurs publics ou en leur nom, régie par
                [l'arrêté du 22 décembre 2022](https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000046850496). Leur
                qualité est donc principalement liée à la qualité de leur saisie par les agents publics, parfois
                peu aidé·es par la qualité des outils à leur disposition.

L'analyse de marchés individuels et le comptage de marchés sur des critères autres que financiers
sont plutôt fiables. En revanche, certains montants de marché estimés à des
valeurs farfelues ([1 euro](https://colibre.fr/marches/432766947000192025S01301),
[1 milliard](https://colibre.fr/marches/2459004280001320210000000271)) faussent les calculs par aggrégation
(sommes, moyennes, médianes) et donc la production de statistiques financières fiables.
Acheteurs, acheteuses : s'il vous plaît, essayez d'estimer les montants des marchés publics attribués de manière plus précise.

Quant à l'exhaustivité, [decp-processing](https://github.com/ColinMaudry/decp-processing) consolide
toutes les sources de données exploitables ayant pu être identifiées (voir [Sources de données](/a-propos/donnees)).
Il faut souligner la belle continuité de la publication par la DGFiP des données des marchés publics remontées via le
[protocole PES](https://www.collectivites-locales.gouv.fr/finances-locales/le-protocole-dechange-standard-pes).
Merci à leurs équipes."""
            ),
            html.H2("Sources de données", className="mt-4"),
            get_sources_tables(os.getenv("SOURCE_STATS_CSV_PATH")),
            html.P(
                "Ce graphique illustre les doublons de marchés publics entre sources, c'est-à-dire la proportion de marchés publiés par plus d'une source."
            ),
            get_duplicate_matrix(),
        ]
    )
    return apropos_shell("donnees", contenu)
