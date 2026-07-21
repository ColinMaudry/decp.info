from datetime import datetime

import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.rencontres import openagenda
from src.rencontres.calendrier import lien_google, lien_outlook
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/contact",
    title="Contact | À propos | colibre",
    description="Contactez Colin Maudry, développeur de colibre.",
    image_url=META_CONTENT["image_url"],
)

_MOIS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def _format_creneau(debut: datetime) -> str:
    return (
        f"{debut.day} {_MOIS[debut.month - 1]} {debut.year} "
        f"à {debut.hour}h{debut.minute:02d}"
    )


def _carte(ev) -> dbc.Card:
    corps = [
        html.H5(ev.titre, className="card-title"),
        html.P(_format_creneau(ev.debut), className="text-muted mb-1"),
    ]
    if ev.lieu_nom or ev.lieu_ville:
        lieu = " — ".join(p for p in (ev.lieu_nom, ev.lieu_ville) if p)
        corps.append(html.P(lieu, className="mb-1"))
    if ev.description:
        corps.append(html.P(ev.description))
    if ev.visio_url:
        corps.append(
            html.P(html.A("Rejoindre en visio", href=ev.visio_url, target="_blank"))
        )
    corps.append(
        html.Div(
            [
                dbc.Button(
                    "Google Agenda",
                    href=lien_google(ev),
                    target="_blank",
                    color="primary",
                    outline=True,
                    size="sm",
                    class_name="me-2",
                ),
                dbc.Button(
                    "Outlook",
                    href=lien_outlook(ev),
                    target="_blank",
                    color="primary",
                    outline=True,
                    size="sm",
                    class_name="me-2",
                ),
                dbc.Button(
                    ".ics",
                    href=f"/rencontres/{ev.uid}.ics",
                    color="secondary",
                    outline=True,
                    size="sm",
                ),
            ],
            className="mt-2",
        )
    )
    return dbc.Card(dbc.CardBody(corps), class_name="mb-3")


def _section_rencontres():
    evenements = openagenda.fetch_rencontres()
    if not evenements:
        return html.P(
            "Prochaines rencontres bientôt annoncées.", className="text-muted"
        )
    return html.Div([_carte(ev) for ev in evenements])


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Contact"),
            dcc.Markdown(
                """
- Chat en direct (💬 en bas à droite de l'écran)
- Email : [colin@colmo.tech](mailto:colin@colmo.tech)
- Bluesky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
- LinkedIn : [colinmaudry](https://www.linkedin.com/in/colinmaudry/)
"""
            ),
            html.H2("Prochaines rencontres", className="mt-4"),
            _section_rencontres(),
        ]
    )
    return apropos_shell("contact", contenu)
