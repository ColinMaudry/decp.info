from dash import register_page

from src.pages._compte_shell import account_guard, account_shell
from src.roadmap import view as roadmap_view

register_page(
    __name__,
    path="/compte/roadmap",
    title="Roadmap | colibre",
    name="Roadmap",
    description="Votez pour les prochaines fonctionnalités de colibre.",
)


def layout(**_):
    guard = account_guard("/compte/roadmap", require_subscription=True)
    if guard is not None:
        return guard
    # Même contenu et mêmes droits que /a-propos/roadmap ; seule la coquille
    # diffère. Le callback de vote vit dans src.roadmap.view, partagé par les
    # deux pages.
    return account_shell("roadmap", roadmap_view.content_for_current_user())
