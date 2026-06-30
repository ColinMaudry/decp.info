from pathlib import Path

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.roadmap import db as roadmap_db
from src.roadmap import github

_CHANGELOG_PATH = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def balance_text(balance: int) -> str:
    mot = "vote" if balance == 1 else "votes"
    return f"Il te reste {balance} {mot}."


def changelog_markdown() -> dcc.Markdown:
    try:
        text = _CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError:
        text = "_Changelog indisponible._"
    return dcc.Markdown(text)


def _vote_item(issue: dict, count: int, editable: bool):
    mot = "vote" if count == 1 else "votes"
    children = [
        html.A(issue["title"], href=issue["html_url"], target="_blank"),
        html.Span(f" — {count} {mot}", className="text-muted ms-1"),
    ]
    if editable:
        children.append(
            dbc.Button(
                "Voter",
                id={"type": "roadmap-vote", "index": issue["number"]},
                size="sm",
                color="primary",
                className="ms-2",
            )
        )
    return dbc.ListGroupItem(children)


def vote_items(au_vote: list[dict], counts: dict[int, int], editable: bool) -> list:
    ordered = sorted(au_vote, key=lambda i: counts.get(i["number"], 0), reverse=True)
    if not ordered:
        return [dbc.ListGroupItem("Aucune fonctionnalité au vote pour le moment.")]
    return [_vote_item(i, counts.get(i["number"], 0), editable) for i in ordered]


def _en_cours_items(en_cours: list[dict]) -> list:
    if not en_cours:
        return [dbc.ListGroupItem("Rien en cours pour le moment.")]
    return [
        dbc.ListGroupItem(html.A(i["title"], href=i["html_url"], target="_blank"))
        for i in en_cours
    ]


def roadmap_content(editable: bool, balance: int | None = None) -> html.Div:
    try:
        issues = github.fetch_roadmap_issues()
        counts = roadmap_db.vote_counts()
    except Exception:
        issues = {"en_cours": [], "au_vote": []}
        counts = {}

    body: list = []
    if editable and balance is not None:
        body.append(
            dbc.Alert(balance_text(balance), color="info", id="roadmap-balance")
        )
    body.append(html.H3("En cours", className="mt-3"))
    body.append(dbc.ListGroup(_en_cours_items(issues["en_cours"]), className="mb-4"))
    body.append(html.H3("Au vote"))
    body.append(
        dbc.ListGroup(
            vote_items(issues["au_vote"], counts, editable),
            id="roadmap-vote-list",
            className="mb-4",
        )
    )
    body.append(html.Hr())
    body.append(html.H3("Changelog"))
    body.append(changelog_markdown())
    return html.Div(body)
