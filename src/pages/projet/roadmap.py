from dash import register_page

from src.pages._projet_shell import projet_shell
from src.roadmap import view as roadmap_view
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/projet/roadmap",
    title="Roadmap | Le projet | colibre",
    description="Les prochaines fonctionnalités de colibre, soumises au vote des abonnés.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    # Page publique, mais votable : une abonnée connectée y retrouve ses boutons
    # de vote et son solde, exactement comme sur /compte/roadmap.
    return projet_shell("roadmap", roadmap_view.content_for_current_user())
