import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell
from src.subscriptions import db, plans

register_page(
    __name__,
    path="/compte/abonnement",
    title="Abonnement | decp.info",
    name="Abonnement",
    description="Gestion de votre abonnement decp.info.",
)

_PLAN_KEYS = ("simple", "soutien")


def _csrf_input(index: str):
    return dcc.Input(
        type="hidden", id={"type": "csrf-input", "index": index}, name="csrf_token"
    )


def _plan_card(meta: dict, trial: int | None, trial_used: bool):
    if trial_used:
        badge = html.Div(
            "Sans période d'essai (déjà utilisée) — débit immédiat",
            className="text-muted mb-2",
        )
    elif trial:
        badge = html.Div(
            f"{trial} jours d'essai gratuit", className="text-success mb-2"
        )
    else:
        badge = None
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4(meta["label"]),
                html.P(f"{meta['prix_ht']} € HT / mois"),
                html.P(meta["description"]),
                badge,
                html.Form(
                    method="POST",
                    action="/subscriptions/subscribe",
                    children=[
                        _csrf_input(f"subscribe-{meta['key']}"),
                        dcc.Input(type="hidden", name="plan", value=meta["key"]),
                        html.Button(
                            "S'abonner", type="submit", className="btn btn-primary"
                        ),
                    ],
                ),
            ]
        ),
        className="mb-3",
    )


def _plan_cards(trial_used=False, trial_for=plans.trial_days):
    cards = []
    for key in _PLAN_KEYS:
        meta = plans.plan_meta(key)
        if meta:
            cards.append(_plan_card(meta, trial_for(key), trial_used))
    return dbc.Row([dbc.Col(c, md=6) for c in cards])


def _explainer():
    return html.Div(
        [
            html.H4("À quoi servent les abonnements"),
            html.Ul(
                [
                    html.Li("Abonnement Frisbii (solution de paiement) : 50 €"),
                    html.Li("Serveur Scaleway : 40 €"),
                    html.Li("Espace de coworking : 250 €"),
                    html.Li("Salaire médian : 3 840 €"),
                ]
            ),
            html.H4("Ce que les abonnements de soutien permettraient"),
            html.Ul(
                [
                    html.Li(
                        "Rédaction d'études à partir des données, par exemple sur les "
                        "acheteurs dont les données sont introuvables et les raisons de "
                        "cette non-publication."
                    ),
                    html.Li(
                        "Coordination des bonnes volontés souhaitant militer pour une "
                        "législation plus exigeante sur la transparence de la commande "
                        "publique."
                    ),
                ]
            ),
        ]
    )


def _active_view(row):
    meta = plans.plan_meta(row["plan"]) or {"label": row["plan"]}
    end = row["current_period_end"]
    blocks = [html.H3(meta["label"]), html.P(f"Statut : {row['status']}")]
    if row["status"] == "trial":
        blocks.append(
            dbc.Alert(
                f"Essai gratuit jusqu'au {end}, puis débit automatique.", color="info"
            )
        )
    elif row["status"] == "cancelled":
        blocks.append(
            dbc.Alert(f"Abonnement résilié, actif jusqu'au {end}.", color="warning")
        )
    else:
        blocks.append(html.P(f"Prochain renouvellement : {end}"))
    if row["status"] in ("trial", "active"):
        blocks.append(
            html.Form(
                method="POST",
                action="/subscriptions/cancel",
                children=[
                    _csrf_input("cancel"),
                    html.Button(
                        "Résilier", type="submit", className="btn btn-outline-danger"
                    ),
                ],
            )
        )
    return html.Div(blocks)


def _feedback(query):
    msgs = {
        "succes": ("Merci, votre abonnement est en cours d'activation.", "success"),
        "annule": ("Paiement annulé.", "secondary"),
    }
    out = []
    if query.get("paiement") in msgs:
        text, color = msgs[query["paiement"]]
        out.append(dbc.Alert(text, color=color))
    if query.get("resiliation") == "ok":
        out.append(dbc.Alert("Votre abonnement a été résilié.", color="info"))
    if query.get("error") == "frisbii":
        out.append(
            dbc.Alert(
                "Une erreur est survenue avec le service de paiement.", color="danger"
            )
        )
    return out


def layout(**query):
    guard = account_guard("/compte/abonnement", require_subscription=False)
    if guard is not None:
        return guard

    row = db.get_by_user(current_user.id) if current_user.is_authenticated else None
    has_access = (
        db.has_active_subscription(current_user.id)
        if current_user.is_authenticated
        else False
    )

    trial_used = (
        db.has_used_trial(current_user.id) if current_user.is_authenticated else False
    )

    body = [html.H2("Abonnement"), *_feedback(query)]
    if has_access and row is not None:
        body.append(_active_view(row))
    else:
        body.extend([_plan_cards(trial_used=trial_used), html.Hr(), _explainer()])

    return account_shell("abonnement", html.Div(body))
