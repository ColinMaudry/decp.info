from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/donnees-brutes",
    title="Données brutes | À propos | colibre",
    description="Téléchargez ou interrogez les données brutes qui alimentent colibre.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Consommer les données brutes"),
            dcc.Markdown(
                """
Vous pouvez consommer les données qui alimentent colibre en les téléchargeant [sur data.gouv.fr](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire) (Parquet, CSV), pensez à lire la description du jeu de données

Une API REST tabulaire (JSON) est également disponible par abonnement mensuel pour accéder aux mêmes données et alimenter une application.
Documentation interactive : [Swagger UI](/api/v1/swagger). Si cela vous intéresse, [contactez-moi](/a-propos/contact)."""
            ),
        ]
    )
    return apropos_shell("donnees-brutes", contenu)
