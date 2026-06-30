from dash import register_page

from src.pages._apropos_shell import apropos_shell
from src.roadmap import ui as roadmap_ui
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/roadmap",
    title="Roadmap | À propos | decp.info",
    description="Les prochaines fonctionnalités de decp.info, soumises au vote des abonnés.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    return apropos_shell("roadmap", roadmap_ui.roadmap_content(editable=False))
