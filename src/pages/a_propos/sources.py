import os

from dash import html, register_page

from src.figures import get_sources_tables
from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/sources",
    title="Sources de données | À propos | decp.info",
    description="Sources de données utilisées par decp.info pour consolider les marchés publics français.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Sources de données"),
            get_sources_tables(os.getenv("SOURCE_STATS_CSV_PATH")),
        ]
    )
    return apropos_shell("sources", contenu)
