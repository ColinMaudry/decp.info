import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

from src.admin.guard import is_admin
from src.auth.db import get_user_by_id
from src.pages.admin._shell import admin_nav, not_admin
from src.subscriptions.db import (
    SUBSCRIPTION_STATUSES,
    get_current,
    get_subscriber_state,
    list_by_user,
)

register_page(
    __name__,
    path_template="/admin/user/<user_id>",
    title="Détail utilisateur | colibre",
    name="Détail utilisateur",
    description="Panneau d'administration interne.",
)

ERROR_MESSAGES = {"invalid_status": "Statut invalide ou abonnement introuvable."}
SUCCESS_MESSAGES = {"status_changed": "Statut de l'abonnement mis à jour."}


def _parse_user_id(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def _not_found():
    return dbc.Container(
        [
            html.H2("Panneau admin"),
            admin_nav("liste"),
            dbc.Alert("Utilisateur introuvable.", color="warning"),
        ],
        fluid=True,
        className="py-4",
    )


def _csrf():
    return dcc.Input(
        type="hidden",
        id={"type": "csrf-input", "index": "admin-status"},
        name="csrf_token",
    )


def _account_section(user):
    return html.Div(
        [
            html.H4("Compte"),
            html.P([html.Strong("Email : "), user["email"]]),
            html.P(
                [
                    html.Strong("Vérifié : "),
                    "oui" if user["email_verified"] else "non",
                ]
            ),
            html.P([html.Strong("SIRET : "), user["siret"] or "—"]),
            html.P([html.Strong("Créé le : "), user["created_at"]]),
        ]
    )


def _state_section(user_id):
    state = get_subscriber_state(user_id)
    return html.Div(
        [
            html.H4("État abonné", className="mt-4"),
            html.P(
                [
                    html.Strong("Solde de votes : "),
                    str(state["votes_balance"] if state else 0),
                ]
            ),
            html.P(
                [
                    html.Strong("Essai utilisé : "),
                    "oui" if state and state["trial_used"] else "non",
                ]
            ),
        ]
    )


def _history_section(user_id, current_id):
    rows = []
    for sub in list_by_user(user_id):
        badge = (
            dbc.Badge("actuel", color="primary", className="ms-2")
            if sub["id"] == current_id
            else None
        )
        rows.append(
            html.Tr(
                [
                    html.Td([sub["plan"] or "—", badge]),
                    html.Td(sub["status"] or "—"),
                    html.Td(sub["frisbii_subscription_handle"] or "—"),
                    html.Td(sub["prix_ht"] if sub["prix_ht"] is not None else "—"),
                    html.Td(sub["current_period_end"] or "—"),
                    html.Td(sub["created_at"]),
                ]
            )
        )
    return html.Div(
        [
            html.H4("Historique des abonnements", className="mt-4"),
            dbc.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th(h)
                                for h in (
                                    "Plan",
                                    "Statut",
                                    "Handle Frisbii",
                                    "Prix HT",
                                    "Fin de période",
                                    "Créé le",
                                )
                            ]
                        )
                    ),
                    html.Tbody(rows),
                ],
                bordered=True,
                size="sm",
            ),
        ]
    )


def _status_form(user_id, current):
    if current is None:
        return html.Div()
    return html.Div(
        [
            html.H4("Changer le statut de l'abonnement courant", className="mt-4"),
            html.Form(
                method="POST",
                action="/admin/actions/subscription-status",
                children=[
                    _csrf(),
                    dcc.Input(type="hidden", name="user_id", value=str(user_id)),
                    dcc.Input(
                        type="hidden", name="subscription_id", value=str(current["id"])
                    ),
                    dbc.Select(
                        id="admin-status-select",
                        name="status",
                        options=[
                            {"label": s, "value": s} for s in SUBSCRIPTION_STATUSES
                        ],
                        value=current["status"],
                        className="mb-3",
                        style={"maxWidth": "300px"},
                    ),
                    dbc.Button(
                        "Mettre à jour le statut", type="submit", color="primary"
                    ),
                ],
            ),
        ]
    )


def layout(user_id=None, error=None, status_changed=None, **_):
    if not is_admin():
        return not_admin()

    uid = _parse_user_id(user_id)
    user = get_user_by_id(uid) if uid is not None else None
    if user is None:
        return _not_found()

    alerts = []
    if error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    if status_changed == "1":
        alerts.append(dbc.Alert(SUCCESS_MESSAGES["status_changed"], color="success"))

    current = get_current(user["id"])

    return dbc.Container(
        [
            html.H2("Panneau admin"),
            admin_nav("liste"),
            *alerts,
            _account_section(user),
            _state_section(user["id"]),
            _history_section(user["id"], current["id"] if current else None),
            _status_form(user["id"], current),
        ],
        fluid=True,
        className="py-4",
    )
