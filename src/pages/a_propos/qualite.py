from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/qualite",
    title="Qualité des données | À propos | colibre",
    description="Informations sur la qualité et l'exhaustivité des données de marchés publics sur colibre.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Qualité et exhaustivité des données"),
            dcc.Markdown(
                """Les données visibles sur ce site proviennent exclusivement de la publication de données
                ouvertes par les acheteurs publics ou en leur nom, régie par
                [l'arrêté du 22 décembre 2022](https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000046850496). Leur
                qualité est donc principalement liée à la qualité de leur saisie par les agents publics, parfois
                peu aidé·es par la qualité des outils à leur disposition.

L'analyse de marchés individuels et le comptage de marchés sur des critères autres que financiers sont plutôt fiables. En revanche, certains montants de marché estimés à des valeurs farfelues ([1 euro](https://colibre.fr/marches/432766947000192025S01301), [1 milliard](https://colibre.fr/marches/2459004280001320210000000271)) faussent les calculs par aggrégation (sommes, moyennes, médianes) et donc la production de statistiques financières fiables. Acheteurs, acheteuses : s'il vous plaît, essayez d'estimer les montants des marchés publics attribués de manière plus précise.

Quant à l'exhaustivité, [decp-processing](https://github.com/ColinMaudry/decp-processing) consolide toutes les sources de données exploitables ayant été identifiées (voir [Sources de données](/a-propos/sources)). Il faut souligner la belle continuité de la publication par la DGFiP des données des marchés publics remontées via le [protocole PES](https://www.collectivites-locales.gouv.fr/finances-locales/le-protocole-dechange-standard-pes). Merci à leurs équipes."""
            ),
        ]
    )
    return apropos_shell("qualite", contenu)
