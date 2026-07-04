import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, register_page
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell
from src.subscriptions import db, plans
from src.utils.frontend import format_date_french

register_page(
    __name__,
    path="/compte/abonnement",
    title="Abonnement | colibre",
    name="Abonnement",
    description="Gestion de votre abonnement colibre.",
)


def _csrf_input():
    from flask_wtf.csrf import generate_csrf

    return dcc.Input(type="hidden", name="csrf_token", value=generate_csrf())


def _reabo_button(has_used_trial: bool):
    label = "Me réabonner" if has_used_trial else "M'abonner"
    return html.Div(
        [
            html.P(
                "Abonnez-vous pour accéder aux fonctionnalités réservées "
                "aux abonné·es.",
                className="mb-3",
            ),
            html.A(
                label,
                href="/a-propos/abonnement",
                className="btn btn-primary",
            ),
        ],
        className="mb-4",
    )


def _active_view(row):
    meta = plans.plan_meta(row["plan"]) or {"label": row["plan"]}
    end = format_date_french(row["current_period_end"])
    blocks = [html.H3(meta["label"], className="mb-3")]

    if row["status"] == "pending":
        blocks.extend(
            [
                dbc.Alert(
                    "Sans méthode de paiement enregistrée, votre abonnement sera "
                    "résilié à la fin de la période d'essai.",
                    color="warning",
                    className="mb-3",
                ),
                html.Form(
                    method="POST",
                    action="/subscriptions/add-payment",
                    children=[
                        _csrf_input(),
                        html.Button(
                            "Ajouter une méthode de paiement",
                            type="submit",
                            className="btn btn-primary mb-3",
                        ),
                    ],
                ),
            ]
        )
    elif row["status"] == "trial":
        blocks.append(
            dbc.Alert(
                f"Essai gratuit jusqu'au {end}, puis facturation et débit automatique à chaque date anniversaire.",
                color="info",
            )
        )
    elif row["status"] == "cancelled":
        blocks.append(
            dbc.Alert(f"Abonnement résilié, actif jusqu'au {end}.", color="warning")
        )
    elif row["status"] == "active":
        blocks.append(html.P(f"Prochaine facturation : {end}"))

    if row["status"] in ("pending", "trial", "active"):
        blocks.append(
            html.Button(
                "Me désabonner",
                id="resiliation-trigger",
                n_clicks=0,
                className="btn btn-outline-danger mt-3",
            )
        )

    return html.Div(blocks)


def _resiliation_modal(end_raw):
    end = format_date_french(end_raw) if end_raw else None
    if end:
        body_text = (
            f"Êtes-vous sûr de vouloir mettre fin à votre abonnement ? "
            f"Vous resterez abonné jusqu'à la date anniversaire, le {end}."
        )
    else:
        body_text = "Êtes-vous sûr de vouloir mettre fin à votre abonnement ?"
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Résilier l'abonnement")),
            dbc.ModalBody(body_text),
            dbc.ModalFooter(
                [
                    dbc.Button(
                        "Annuler",
                        id="resiliation-annuler",
                        color="secondary",
                        className="me-2",
                        n_clicks=0,
                    ),
                    html.Form(
                        method="POST",
                        action="/subscriptions/cancel",
                        children=[
                            _csrf_input(),
                            html.Button(
                                "Je suis sûr",
                                type="submit",
                                className="btn btn-danger",
                            ),
                        ],
                        style={"display": "inline"},
                    ),
                ]
            ),
        ],
        id="resiliation-modal",
        is_open=False,
    )


def _feedback(query):
    msgs = {
        "succes": (
            "Merci, votre abonnement est activé. Bonne exploration !",
            "success",
        ),
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
                "Une erreur est survenue avec le service de paiement.", color="primary"
            )
        )
    return out


_salaire_modal = dbc.Modal(
    [
        dbc.ModalHeader(dbc.ModalTitle("Salaire médian — coût employeur")),
        dbc.ModalBody(html.Img(src="/assets/salaire.png", style={"width": "100%"})),
    ],
    id="salaire-modal",
    size="lg",
    is_open=False,
)


@callback(
    Output("salaire-modal", "is_open"),
    Input("salaire-modal-trigger", "n_clicks"),
    prevent_initial_call=True,
)
def _open_salaire_modal(_):
    return True


@callback(
    Output("resiliation-modal", "is_open"),
    Input("resiliation-trigger", "n_clicks"),
    Input("resiliation-annuler", "n_clicks"),
    State("resiliation-modal", "is_open"),
    prevent_initial_call=True,
)
def _toggle_resiliation(_, __, is_open):
    return not is_open


def _tous_abonnes_banner():
    from src.utils import TOUS_ABONNES

    if not TOUS_ABONNES:
        return None
    return dbc.Alert(
        "Les fonctionnalités normalement accessibles contre un abonnement de "
        "20 € HT par mois sont accessibles à tous et toutes en attendant la "
        "validation de mon dossier pour recevoir des paiements.",
        color="info",
    )


def _show_active_view(row) -> bool:
    return row is not None and row["status"] not in ("failed", "expired")


def layout(**query):
    guard = account_guard("/compte/abonnement", require_subscription=False)
    if guard is not None:
        return guard

    row = db.get_current(current_user.id) if current_user.is_authenticated else None

    body = [html.H2("Abonnement", className="mb-4")]
    banner = _tous_abonnes_banner()
    if banner is not None:
        body.append(banner)
    body.extend(_feedback(query))

    if _show_active_view(row):
        body.append(_active_view(row))
        body.append(_resiliation_modal(row["current_period_end"]))
    else:
        if row is not None and row["status"] == "expired":
            body.append(
                dbc.Alert(
                    "Votre abonnement a expiré.", color="warning", className="mb-4"
                )
            )
        body.append(_reabo_button(db.has_used_trial(current_user.id)))

    body.append(_salaire_modal)
    return account_shell("abonnement", html.Div(body))
