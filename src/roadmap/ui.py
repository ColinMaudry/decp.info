from datetime import datetime
from pathlib import Path

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.roadmap import db as roadmap_db
from src.roadmap import github

_CHANGELOG_PATH = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def changelog_markdown() -> dcc.Markdown:
    try:
        text = _CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError:
        text = "_Changelog indisponible._"
    return dcc.Markdown(text)


def _vote_item(issue: dict, count: int, editable: bool, can_vote: bool = True):
    right = [
        dcc.Input(
            value=str(count),
            disabled=True,
            type="text",
            style={"width": "3rem", "textAlign": "right"},
            className="ms-5 flex-shrink-0",
        )
    ]
    if editable:
        right.append(
            dbc.Button(
                "+",
                id={"type": "roadmap-vote", "index": issue["number"]},
                size="sm",
                color="primary" if can_vote else "secondary",
                disabled=not can_vote,
                className="ms-2 flex-shrink-0",
            )
        )
    return dbc.ListGroupItem(
        [
            html.A(issue["title"], href=issue["html_url"], target="_blank"),
            html.Span(right, className="d-flex align-items-center"),
        ],
        className="d-flex justify-content-between align-items-center",
    )


def _balance_item(
    balance: int, next_recharge: datetime | None = None
) -> dbc.ListGroupItem:
    label_parts = [html.Span("Votes restants", style={"fontWeight": "bold"})]
    if next_recharge is not None:
        label_parts.append(
            html.Span(
                f" — rechargement le {next_recharge.strftime('%d/%m/%y à %H:%M')}",
                className="text-muted small",
            )
        )
    return dbc.ListGroupItem(
        [
            html.Span(label_parts),
            dcc.Input(
                value=str(balance),
                disabled=True,
                type="text",
                style={"width": "3rem", "textAlign": "right"},
                className="ms-3 ",
            ),
        ],
        className="d-flex justify-content-between align-items-center",
    )


def vote_items(
    au_vote: list[dict],
    counts: dict[int, int],
    editable: bool,
    can_vote: bool = True,
    balance: int | None = None,
    next_recharge: datetime | None = None,
) -> list:
    result = (
        [_balance_item(balance, next_recharge)]
        if editable and balance is not None
        else []
    )
    ordered = sorted(au_vote, key=lambda i: counts.get(i["number"], 0), reverse=True)
    if not ordered:
        return result + [
            dbc.ListGroupItem("Aucune fonctionnalité au vote pour le moment.")
        ]
    return result + [
        _vote_item(i, counts.get(i["number"], 0), editable, can_vote) for i in ordered
    ]


def _en_cours_items(en_cours: list[dict]) -> list:
    if not en_cours:
        return [dbc.ListGroupItem("Rien en cours pour le moment.")]
    return [
        dbc.ListGroupItem(html.A(i["title"], href=i["html_url"], target="_blank"))
        for i in en_cours
    ]


def _subscribe_hint() -> html.P:
    return html.P(
        [
            dcc.Link("Abonnez-vous", href="/projet/abonnement"),
            " pour donner votre voix aux fonctionnalités qui vous seraient utiles.",
        ],
        className="text-muted",
    )


def roadmap_content(
    editable: bool,
    balance: int | None = None,
    next_recharge: datetime | None = None,
) -> html.Div:
    try:
        issues = github.fetch_roadmap_issues()
        counts = roadmap_db.vote_counts()
    except Exception:
        issues = {"en_cours": [], "au_vote": []}
        counts = {}

    body: list = []
    body.append(html.H3("En cours de développement", className="mt-3"))
    body.append(dbc.ListGroup(_en_cours_items(issues["en_cours"]), className="mb-4"))
    can_vote = editable and balance is not None and balance > 0
    body.append(html.H3("Au vote"))
    body.append(
        html.P(
            "Les abonné·es votent pour les fonctionnalités à développer en priorité."
        )
    )
    if not editable:
        # Seule la page publique passe ici : /compte/roadmap est réservée aux
        # abonné·es, donc toujours en editable=True.
        body.append(_subscribe_hint())
    body.append(
        html.Div(
            dbc.ListGroup(
                vote_items(
                    issues["au_vote"],
                    counts,
                    editable,
                    can_vote,
                    balance=balance,
                    next_recharge=next_recharge,
                ),
                id="roadmap-vote-list",
            ),
            className="mb-4",
            style={"width": "fit-content"},
        )
    )
    body.append(html.Hr())
    body.append(html.H3("Historique des versions", id="versions"))
    body.append(changelog_markdown())
    return html.Div(body)
