"""Couche « au courant de la requête » entre les pages roadmap et `ui.py`.

`ui.py` reste de la présentation pure. Ce module y ajoute ce qui dépend de
l'utilisateur connecté — droits de vote, solde, prochain rechargement — et
porte le callback de vote.

Les deux pages roadmap (`/a-propos/roadmap`, publique, et `/compte/roadmap`,
réservée aux abonné·es) partagent tout ce qui est ici : elles rendent le même
contenu, avec les mêmes droits, et diffèrent seulement par leur coquille.

Le callback vit ici plutôt que dans un module de page parce que Dash ré-exécute
les pages via `exec_module` pendant la découverte `use_pages` : un `@callback`
déclaré dans une page importée par ailleurs serait enregistré deux fois
(« Duplicate callback outputs »). Un module ordinaire est mis en cache par
`sys.modules` et n'enregistre le sien qu'une fois.
"""

from dash import ALL, Input, Output, callback, ctx, no_update
from flask_login import current_user

from src.pages._compte_shell import current_user_has_subscription
from src.roadmap import db as roadmap_db
from src.roadmap import github
from src.roadmap import ui as roadmap_ui
from src.subscriptions import db as subs_db


def _vote_state() -> tuple[int, object]:
    """Solde de votes et date du prochain rechargement pour l'utilisateur courant."""
    return (
        subs_db.credit_pending(current_user.id),
        subs_db.next_recharge_at(current_user.id),
    )


def content_for_current_user():
    """Contenu roadmap, votable si l'utilisateur courant est abonné."""
    if not current_user_has_subscription():
        return roadmap_ui.roadmap_content(editable=False)
    balance, next_recharge = _vote_state()
    sub = subs_db.get_current(current_user.id)
    return roadmap_ui.roadmap_content(
        editable=True,
        balance=balance,
        next_recharge=next_recharge,
        sub_status=sub["status"] if sub else None,
        trial_ends_at=sub["current_period_end"] if sub else None,
    )


@callback(
    Output("roadmap-vote-list", "children"),
    Input({"type": "roadmap-vote", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def cast_vote(n_clicks):
    # Le solde protège déjà d'une requête forgée (spend_vote ne débite qu'au-delà
    # de zéro, credit_pending ne crédite que les abonnements actifs), mais ce
    # callback est désormais exposé depuis une page publique : on vérifie
    # l'abonnement explicitement plutôt que de s'en remettre à cet invariant.
    if not current_user.is_authenticated or not current_user_has_subscription():
        return no_update
    if not ctx.triggered_id or not any(n_clicks):
        return no_update
    issue_number = ctx.triggered_id["index"]
    if subs_db.spend_vote(current_user.id):
        roadmap_db.record_vote(current_user.id, issue_number)
    balance, next_recharge = _vote_state()
    issues = github.fetch_roadmap_issues()
    counts = roadmap_db.vote_counts()
    return roadmap_ui.vote_items(
        issues["au_vote"],
        counts,
        editable=True,
        can_vote=balance > 0,
        balance=balance,
        next_recharge=next_recharge,
    )
