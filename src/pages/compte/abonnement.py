import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, register_page
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell
from src.subscriptions import db, plans
from src.utils.frontend import format_datetime_french

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


def _price_text(meta: dict) -> str | None:
    ht = meta.get("prix_ht")
    if ht is None:
        return None
    return f"{ht} € HT / mois ({round(ht * 1.2, 2):g} € TTC)"


def _reabo_button():
    return html.Div(
        [
            dcc.Markdown(
                "[Abonnez-vous](/a-propos/abonnement) pour accéder aux fonctionnalités réservées "
                "aux abonné·es.",
                className="mb-3",
            ),
        ],
        className="mb-4",
    )


def _free_access_view():
    from src.pages.a_propos.abonnement import abonnement_features

    return html.Div(
        [
            html.H5(
                "Vous avez temporairement accès à toutes les fonctionnalités",
                className="mb-3",
            ),
            html.P("Votre accès gratuit débloque :"),
            abonnement_features,
            dcc.Markdown(
                "Pensez à copier les liens vers vos vues pour les conserver si vous "
                "ne comptez pas souscrire à un abonnement payant.",
                className="text-muted mt-3",
            ),
        ],
        className="mb-4",
    )


def _trial_view(end):
    from src.pages.a_propos.abonnement import abonnement_features

    end_text = format_datetime_french(end) if end else None
    titre = (
        f"Essai gratuit jusqu'au {end_text}" if end_text else "Essai gratuit en cours"
    )
    return html.Div(
        [
            html.H5(titre, className="mb-3"),
            html.P("Votre essai débloque :"),
            abonnement_features,
            dcc.Markdown(
                "À la fin de l'essai, rien n'est prélevé : c'est à vous de "
                "démarrer votre abonnement depuis cette page.",
                className="text-muted mt-3",
            ),
            # Le débit est immédiat, y compris pendant l'essai : le différer
            # jusqu'à la fin de l'essai reviendrait au prélèvement automatique
            # que ce chantier supprime. Les jours restants sont donc perdus, et
            # il faut le dire avant le clic, pas après.
            html.P(
                "Le premier prélèvement a lieu immédiatement ; les jours "
                "d'essai restants ne sont pas reportés.",
                className="text-muted small mt-2",
            ),
            html.A(
                "M'abonner dès maintenant",
                href="/compte/abonnement/mes-infos",
                className="btn btn-outline-secondary mt-2",
            ),
        ],
        className="mb-4",
    )


def _trial_ended_view():
    return html.Div(
        [
            html.H5("Votre essai gratuit est terminé", className="mb-3"),
            html.P(
                "Les fonctionnalités réservées aux abonné·es ne sont plus "
                "accessibles. Vous pouvez démarrer votre abonnement à tout "
                "moment."
            ),
            html.A(
                "Commencer mon abonnement",
                href="/compte/abonnement/mes-infos",
                className="btn btn-secondary mt-2",
            ),
        ],
        className="mb-4",
    )


def _no_sub_view(tous_abonnes: bool, row):
    if tous_abonnes:
        return _free_access_view()
    blocks = []
    if row is not None and row["status"] == "expired":
        blocks.append(
            dbc.Alert("Votre abonnement a expiré.", color="warning", className="mb-4")
        )
    blocks.append(_reabo_button())
    return html.Div(blocks)


def _resume_payment_block():
    return html.Div(
        [
            dbc.Alert(
                "Votre abonnement n'est pas finalisé : aucune méthode de "
                "paiement n'a été enregistrée.",
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
                        className="btn btn-secondary mb-3",
                    ),
                ],
            ),
        ]
    )


def _active_view(row):
    # row["status"] peut valoir "trial" ici sans venir de l'essai applicatif
    # (subscriber_state, qui ne crée aucune ligne subscriptions) : le statut
    # "status" d'une ligne subscriptions est éditable depuis l'admin
    # (src/admin/tables.py), "trial" compris, et une base déployée avant ce
    # chantier peut porter des lignes historiques à ce statut. Accessoirement,
    # webhooks.map_subscription peut aussi le renvoyer si un plan Frisbii
    # restait configuré avec un essai malgré no_trial=True. Les tests
    # d'appartenance ci-dessous incluent donc "trial" au même titre que
    # "active" (cf. db._ACCESS_STATUSES).
    meta = plans.plan_meta(row["plan"]) or {"label": row["plan"]}
    # Horodatages Frisbii en UTC : affichés en heure de Paris et avec l'heure,
    # une fin d'essai de quelques jours se jouant à l'heure près.
    end = (
        format_datetime_french(row["current_period_end"])
        if row["current_period_end"]
        else None
    )
    blocks = [html.H3(meta["label"], className="mb-1")]
    price = _price_text(meta)
    if price:
        blocks.append(html.P(price, className="text-muted mb-3"))

    if row["status"] == "pending":
        blocks.append(_resume_payment_block())
    elif row["status"] == "cancelled":
        texte = (
            f"Abonnement résilié, actif jusqu'au {end}."
            if end
            else "Abonnement résilié."
        )
        blocks.append(dbc.Alert(texte, color="warning"))
    elif row["status"] == "active" and end:
        blocks.append(html.P(f"Prochaine facturation : {end}"))

    if row["status"] in ("pending", "trial", "active"):
        blocks.append(
            html.A(
                "Configurer mon abonnement",
                href="/compte/abonnement/mes-infos",
                className="btn btn-outline-primary mt-3 me-2",
            )
        )

    if row["status"] in ("trial", "active"):
        blocks.append(
            html.Form(
                method="POST",
                action="/subscriptions/change-payment-method",
                children=[
                    _csrf_input(),
                    html.Button(
                        "Changer de méthode de paiement",
                        type="submit",
                        className="btn btn-outline-secondary mt-3 me-2",
                    ),
                ],
                style={"display": "inline-block"},
            )
        )

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
    end = format_datetime_french(end_raw) if end_raw else None
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
    if query.get("carte") == "succes":
        out.append(dbc.Alert("Méthode de paiement mise à jour.", color="success"))
    if query.get("carte") == "annule":
        out.append(dbc.Alert("Modification annulée.", color="secondary"))
    if query.get("error") == "frisbii":
        out.append(
            dbc.Alert(
                "Une erreur est survenue avec le service de paiement.", color="primary"
            )
        )
    if query.get("maj") == "succes":
        out.append(dbc.Alert("Votre abonnement a été mis à jour.", color="success"))
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
        "Les fonctionnalités normalement accessibles contre un abonnement sont temporairement accessibles gratuitement.",
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

    from src.utils import TOUS_ABONNES

    # Un essai en cours doit rester visible même après un abandon de paiement :
    # sans ce cas particulier, `_show_active_view` (vrai pour "pending")
    # masquerait la date de fin d'essai dès la création de la ligne "pending"
    # (create_pending), et rien ne réapparaîtrait à la fin de l'essai — la
    # personne resterait bloquée sur « Ajouter une méthode de paiement »
    # indéfiniment.
    pending_during_trial = (
        row is not None
        and row["status"] == "pending"
        and not TOUS_ABONNES
        and db.trial_active(current_user.id)
    )

    if pending_during_trial:
        body.append(_trial_view(db.trial_ends_at(current_user.id)))
        body.append(_resume_payment_block())
    elif _show_active_view(row):
        body.append(_active_view(row))
        body.append(_resiliation_modal(row["current_period_end"]))
    elif TOUS_ABONNES:
        body.append(_no_sub_view(True, row))
    elif db.trial_active(current_user.id):
        body.append(_trial_view(db.trial_ends_at(current_user.id)))
    elif db.trial_ends_at(current_user.id) is not None:
        body.append(_trial_ended_view())
    else:
        body.append(_no_sub_view(False, row))

    body.append(_salaire_modal)
    return account_shell("abonnement", html.Div(body))
