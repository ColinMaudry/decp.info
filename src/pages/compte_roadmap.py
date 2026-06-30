from dash import ALL, Input, Output, callback, ctx, no_update, register_page
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell
from src.roadmap import db as roadmap_db
from src.roadmap import github
from src.roadmap import ui as roadmap_ui
from src.subscriptions import db as subs_db

register_page(
    __name__,
    path="/compte/roadmap",
    title="Roadmap | decp.info",
    name="Roadmap",
    description="Votez pour les prochaines fonctionnalités de decp.info.",
)


def layout(**_):
    guard = account_guard("/compte/roadmap", require_subscription=True)
    if guard is not None:
        return guard
    balance = subs_db.credit_pending(current_user.id)
    return account_shell(
        "roadmap", roadmap_ui.roadmap_content(editable=True, balance=balance)
    )


@callback(
    Output("roadmap-vote-list", "children"),
    Output("roadmap-balance", "children"),
    Input({"type": "roadmap-vote", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def cast_vote(n_clicks):
    if not ctx.triggered_id or not any(n_clicks):
        return no_update, no_update
    issue_number = ctx.triggered_id["index"]
    if subs_db.spend_vote(current_user.id):
        roadmap_db.record_vote(current_user.id, issue_number)
    balance = subs_db.credit_pending(current_user.id)
    issues = github.fetch_roadmap_issues()
    counts = roadmap_db.vote_counts()
    items = roadmap_ui.vote_items(issues["au_vote"], counts, editable=True)
    return items, roadmap_ui.balance_text(balance)
