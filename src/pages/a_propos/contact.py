from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/contact",
    title="Contact | À propos | colibre",
    description="Contactez Colin Maudry, développeur de colibre.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Contact"),
            dcc.Markdown(
                """
- Email : [colin@colmo.tech](mailto:colin@colmo.tech)
- Bluesky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
- LinkedIn : [colinmaudry](https://www.linkedin.com/in/colinmaudry/)
"""
            ),
        ]
    )
    return apropos_shell("contact", contenu)
