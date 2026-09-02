from datetime import date

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, ctx, dcc, html, register_page
from flask_login import current_user

from src.auth import db as auth_db
from src.pages._compte_shell import account_guard, account_shell
from src.pages.projet.abonnement import _plan_card, subscription_terms
from src.subscriptions import client as frisbii_client
from src.subscriptions import db as sub_db
from src.subscriptions import handles, plans
from src.utils.data import get_annuaire_data
from src.utils.frontend import format_date_french

register_page(
    __name__,
    path="/compte/abonnement/mes-infos",
    title="Mes informations | Abonnement | colibre",
    name="Mes informations de facturation",
    description="Informations de facturation pour votre abonnement colibre.",
)

_SUBSCRIPTION_TERMS = subscription_terms


def _csrf_input():
    from flask_wtf.csrf import generate_csrf

    return dcc.Input(type="hidden", name="csrf_token", value=generate_csrf())


_VENDEUR = "SAS Colmo (SIRET 98939335000016)"


def _jj_mm_aaaa(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _recap_lines(plan_key: str, today: date) -> list[tuple[str, str]]:
    """Récapitulatif de commande affiché avant la saisie de la carte bancaire.

    Reprend les informations exigées « in the checkout process » par l'organisme
    de validation des paiements : raison sociale complète, description de la
    prestation, date de début et durée de l'abonnement, prix et devise. Le
    panneau équivalent côté Frisbii est replié derrière « Aperçu des détails »,
    d'où ce doublon volontaire.

    Plus de ligne d'essai : l'essai est antérieur et sans lien avec cette
    commande, qui démarre et se facture le jour même.
    """
    meta = plans.plan_meta(plan_key)
    if meta is None:
        return []
    ttc = round(meta["prix_ht"] * 1.2, 2)
    return [
        ("Vendeur", _VENDEUR),
        ("Prestation", f"{meta['label']}. {meta['description']}"),
        ("Début de l'abonnement payant", _jj_mm_aaaa(today)),
        (
            "Durée",
            "1 mois, reconduit automatiquement chaque mois jusqu'à résiliation",
        ),
        (
            "Prix",
            f"{meta['prix_ht']:g} € HT par mois, soit {ttc:g} € TTC par mois "
            "(TVA 20 %), en euros (EUR)",
        ),
    ]


def _recap(plan_key: str | None, today: date | None = None):
    lines = _recap_lines(plan_key, today or date.today()) if plan_key else []
    if not lines:
        return html.Div(
            "Choisissez une formule ci-dessus pour afficher le récapitulatif.",
            className="text-muted mb-4",
        )
    return dbc.Card(
        dbc.CardBody(
            [html.H5("Récapitulatif de votre commande", className="mb-3")]
            + [
                html.Div(
                    [html.Span(f"{label} : ", className="fw-bold"), html.Span(value)],
                    className="mb-1",
                )
                for label, value in lines
            ]
        ),
        className="mb-4",
    )


def _mode_for(row) -> str:
    # "trial" couvre le même cas que db._ACCESS_STATUSES : une ligne
    # subscriptions ne devrait plus jamais porter ce statut (l'essai
    # applicatif n'en crée aucune), mais "status" reste éditable depuis
    # l'admin (src/admin/tables.py, "trial" compris) et une base déployée
    # avant ce chantier peut porter des lignes historiques à ce statut.
    # Accessoirement, webhooks.map_subscription peut aussi le renvoyer si un
    # plan Frisbii restait configuré avec un essai malgré no_trial=True.
    if row is not None and row["status"] in ("active", "trial", "pending"):
        return "configure"
    return "subscribe"


_DEFAULT_PLAN = "simple"


def _initial_plan(mode: str, row) -> str:
    """Formule pré-sélectionnée à l'ouverture de la page.

    En souscription, la formule de base est retenue par défaut : le
    récapitulatif de commande est ainsi visible dès l'arrivée sur la page,
    sans clic préalable sur une carte.
    """
    if mode == "configure" and row is not None:
        return row["plan"]
    return _DEFAULT_PLAN


def _submit_label(mode: str, plan_key: str | None) -> str:
    if mode == "configure":
        return "Mettre à jour mon abonnement"
    meta = plans.plan_meta(plan_key) if plan_key else None
    if meta is None:
        return "Commencer mon abonnement"
    ttc = round(meta["prix_ht"] * 1.2, 2)
    return f"Commencer mon abonnement ({ttc:g} € TTC / mois)"


def _submit_button(mode: str, plan_key: str | None):
    return html.Button(
        _submit_label(mode, plan_key),
        id="inf-submit",
        type="submit",
        className="btn btn-secondary",
        disabled=(mode == "subscribe"),
    )


def _selectable_cards(selected=None):
    cols = []
    for key in ("simple", "soutien"):
        meta = plans.plan_meta(key)
        if not meta:
            continue
        base = "plan-selectable selected" if key == selected else "plan-selectable"
        cols.append(
            dbc.Col(
                html.Div(
                    _plan_card(meta),
                    id=f"plan-card-{key}",
                    n_clicks=0,
                    className=base,
                ),
                md=6,
            )
        )
    return dbc.Row(cols, className="g-4 mb-2")


def _selection_state(selected):
    base = "plan-selectable"
    return (
        selected,
        f"{base} selected" if selected == "simple" else base,
        f"{base} selected" if selected == "soutien" else base,
    )


def _change_hint(selected: str, sub_info: dict | None) -> tuple[str, str]:
    sub_info = sub_info or {}
    current = sub_info.get("current_plan")
    if (
        not current
        or sub_info.get("status") not in ("active", "trial")  # cf. _mode_for
        or selected == current
    ):
        return "d-none", ""
    echeance = sub_info.get("echeance")
    return (
        "text-muted mt-2",
        f"Le changement d'abonnement sera appliqué à la prochaine échéance : {echeance}.",
    )


@callback(
    Output("inf-plan-hidden", "value"),
    Output("plan-card-simple", "className"),
    Output("plan-card-soutien", "className"),
    Output("inf-change-hint", "className"),
    Output("inf-change-hint", "children"),
    Output("inf-recap", "children"),
    Output("inf-submit", "children"),
    Input("plan-card-simple", "n_clicks"),
    Input("plan-card-soutien", "n_clicks"),
    State("inf-sub-info", "data"),
    prevent_initial_call=True,
)
def _select_plan(_n_simple, _n_soutien, sub_info):
    selected = "simple" if ctx.triggered_id == "plan-card-simple" else "soutien"
    value, cls_simple, cls_soutien = _selection_state(selected)
    hint_cls, hint_txt = _change_hint(selected, sub_info)
    sub_info = sub_info or {}
    mode = sub_info.get("mode")
    recap = _recap(selected) if mode == "subscribe" else None
    return (
        value,
        cls_simple,
        cls_soutien,
        hint_cls,
        hint_txt,
        recap,
        _submit_label(mode, selected),
    )


def _legal_note():
    return dcc.Markdown(
        """\\* Champ obligatoire

 Méthodes de paiement proposées :

 - Visa, Mastercard
 - Expérimental : Google Pay, Apple Pay

 Si vous préférez régler par virement bancaire et une facturation annuelle plutôt qu'un réglement mensuel, [envoyez un message](/projet/contact) en indiquant vos noms et adresses ou votre SIRET."""
    )


def _consent_checklists(hidden: bool = False):
    default_value = ["ok"] if hidden else []
    return html.Div(
        [
            dcc.Checklist(
                id="inf-cb-retractation",
                options=[
                    {
                        "label": "Je renonce à mon droit de rétractation légal de 14 jours.",
                        "value": "ok",
                    }
                ],
                value=default_value,
                className="mb-2",
            ),
            dcc.Checklist(
                id="inf-cb-cgu",
                options=[
                    {
                        "label": html.Span(
                            [
                                "J'ai lu et accepte les ",
                                html.A(
                                    "conditions d'utilisation du service",
                                    href="/projet/mentions-legales"
                                    "#conditions-utilisation",
                                    target="_blank",
                                    id="inf-cgu-link",
                                ),
                                ".",
                            ]
                        ),
                        "value": "ok",
                    }
                ],
                value=default_value,
                className="mb-2",
            ),
            dcc.Checklist(
                id="inf-cb-cgv",
                options=[
                    {
                        "label": html.Span(
                            [
                                "J'ai lu et accepte les ",
                                html.A(
                                    "conditions d'abonnement",
                                    href="#",
                                    id="inf-cgv-link",
                                    style={"cursor": "pointer"},
                                ),
                                ".",
                            ]
                        ),
                        "value": "ok",
                    }
                ],
                value=default_value,
                className="mb-4",
            ),
        ],
        className="d-none" if hidden else None,
    )


def _cgv_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Conditions d'abonnement")),
            dbc.ModalBody(
                _SUBSCRIPTION_TERMS,
                style={"maxHeight": "60vh", "overflowY": "auto"},
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Fermer", id="inf-cgv-close", className="ms-auto", color="secondary"
                )
            ),
        ],
        id="inf-cgv-modal",
        size="lg",
        is_open=False,
    )


def layout(**query):
    from src.utils import TOUS_ABONNES

    # Sous TOUS_ABONNES, la souscription payante est désactivée : cette page
    # carte bancaire n'a plus de sens, on renvoie vers la page abonnement.
    if TOUS_ABONNES:
        return dcc.Location(
            href="/compte/abonnement", id="mes-infos-tous-abonnes-redirect"
        )

    guard = account_guard("/compte/abonnement/mes-infos", require_subscription=False)
    if guard is not None:
        return guard

    row = sub_db.get_current(current_user.id)
    mode = _mode_for(row)
    selected = _initial_plan(mode, row)
    echeance = (
        format_date_french(row["current_period_end"])
        if mode == "configure" and row["current_period_end"]
        else None
    )
    sub_info: dict = {"mode": mode}
    if mode == "configure":
        sub_info.update(
            {"current_plan": selected, "status": row["status"], "echeance": echeance}
        )

    prefill: dict = {}
    try:
        prefill = frisbii_client.get_customer(handles.customer_handle(current_user.id))
    except frisbii_client.FrisbiiError:
        prefill = {}
    stored_siret = auth_db.get_siret(current_user.id) or ""

    col1 = dbc.Col(
        [
            dbc.Label("Prénom *"),
            dbc.Input(
                id="inf-prenom",
                name="first_name",
                type="text",
                required=True,
                value=prefill.get("first_name", ""),
                className="mb-3",
            ),
            dbc.Label("Nom *"),
            dbc.Input(
                id="inf-nom",
                name="last_name",
                type="text",
                required=True,
                value=prefill.get("last_name", ""),
                className="mb-3",
            ),
            dbc.Label("SIRET"),
            dbc.InputGroup(
                [
                    dbc.Input(
                        id="inf-siret",
                        name="siret",
                        type="text",
                        maxLength=14,
                        placeholder="14 chiffres",
                        value=stored_siret,
                    ),
                    dbc.Button(
                        "Récupérer les autres infos",
                        id="inf-siret-btn",
                        color="secondary",
                        type="button",
                        n_clicks=0,
                    ),
                ],
                className="mb-1",
            ),
            html.Div(id="inf-siret-msg", className="small mb-3"),
            dbc.Label("Nom de l'organisme"),
            dbc.Input(
                id="inf-entreprise",
                name="company",
                type="text",
                value=prefill.get("company", ""),
                className="mb-3",
            ),
        ],
        md=6,
    )

    col2 = dbc.Col(
        [
            dbc.Label("Adresse ligne 1 *"),
            dbc.Input(
                id="inf-adresse1",
                name="address",
                type="text",
                required=True,
                value=prefill.get("address", ""),
                className="mb-3",
            ),
            dbc.Label("Adresse ligne 2"),
            dbc.Input(
                id="inf-adresse2",
                name="address2",
                type="text",
                value=prefill.get("address2", ""),
                className="mb-3",
            ),
            dbc.Label("Code postal *"),
            dbc.Input(
                id="inf-cp",
                name="postal_code",
                type="text",
                required=True,
                value=prefill.get("postal_code", ""),
                className="mb-3",
            ),
            dbc.Label("Ville *"),
            dbc.Input(
                id="inf-ville",
                name="city",
                type="text",
                required=True,
                value=prefill.get("city", ""),
                className="mb-3",
            ),
            dbc.Label("Pays *"),
            dbc.Select(
                id="inf-pays",
                name="country",
                value=prefill.get("country", "FR"),
                options=[
                    {"label": "France", "value": "FR"},
                    {"label": "Allemagne", "value": "DE"},
                    {"label": "Autriche", "value": "AT"},
                    {"label": "Belgique", "value": "BE"},
                    {"label": "Chypre", "value": "CY"},
                    {"label": "Croatie", "value": "HR"},
                    {"label": "Espagne", "value": "ES"},
                    {"label": "Estonie", "value": "EE"},
                    {"label": "Finlande", "value": "FI"},
                    {"label": "Grèce", "value": "GR"},
                    {"label": "Irlande", "value": "IE"},
                    {"label": "Italie", "value": "IT"},
                    {"label": "Lettonie", "value": "LV"},
                    {"label": "Lituanie", "value": "LT"},
                    {"label": "Luxembourg", "value": "LU"},
                    {"label": "Malte", "value": "MT"},
                    {"label": "Pays-Bas", "value": "NL"},
                    {"label": "Portugal", "value": "PT"},
                    {"label": "Slovaquie", "value": "SK"},
                    {"label": "Slovénie", "value": "SI"},
                ],
                className="mb-3",
            ),
        ],
        md=6,
    )

    form = html.Form(
        method="POST",
        action="/subscriptions/subscribe"
        if mode == "subscribe"
        else "/subscriptions/update",
        children=[
            _csrf_input(),
            html.Div(
                "Choisissez votre formule :"
                if mode == "subscribe"
                else "Votre formule :",
                id="inf-plan-invite",
                className="fw-bold mb-2",
            ),
            _selectable_cards(selected=selected),
            html.Div(id="inf-change-hint", className="d-none"),
            dcc.Store(id="inf-sub-info", data=sub_info),
            dcc.Input(
                type="hidden", id="inf-plan-hidden", name="plan", value=selected or ""
            ),
            dbc.Row([col1, col2], className="g-4 mb-4"),
            _legal_note(),
            # Toujours présent, même vide en mode "configure" : _select_plan
            # référence inf-recap en Output inconditionnellement.
            html.Div(
                _recap(selected) if mode == "subscribe" else None,
                id="inf-recap",
                className="mt-4",
            ),
            _consent_checklists(hidden=(mode == "configure")),
            _submit_button(mode, selected),
        ],
    )

    return account_shell(
        "abonnement",
        html.Div(
            [
                html.H2("Mes informations de facturation", className="mb-4"),
                dbc.Alert(
                    "Informations récupérées depuis le prestataire de paiement, vous pouvez les modifier si besoin.",
                    color="info",
                    className="mb-4",
                )
                if prefill
                else None,
                form,
                _cgv_modal(),
            ]
        ),
    )


@callback(
    Output("inf-entreprise", "value"),
    Output("inf-adresse1", "value"),
    Output("inf-cp", "value"),
    Output("inf-ville", "value"),
    Output("inf-siret-msg", "children"),
    Output("inf-siret-msg", "className"),
    Input("inf-siret-btn", "n_clicks"),
    State("inf-siret", "value"),
    prevent_initial_call=True,
)
def _lookup_siret(_, siret):
    empty = ("", "", "", "")
    if not siret or not siret.strip():
        return *empty, "Veuillez saisir un SIRET.", "small text-danger mb-3"
    data = get_annuaire_data(siret.strip())
    if data is None:
        return (
            *empty,
            "SIRET introuvable dans l'annuaire des entreprises.",
            "small text-danger mb-3",
        )
    etablissement = data.get("matching_etablissements")
    if not etablissement:
        return (
            *empty,
            "Aucun établissement trouvé pour ce SIRET.",
            "small text-danger mb-3",
        )
    etab = etablissement[0]
    return (
        data.get("nom_raison_sociale", ""),
        etab.get("adresse", ""),
        etab.get("code_postal", ""),
        etab.get("libelle_commune", ""),
        "Informations récupérées.",
        "small text-success mb-3",
    )


@callback(
    Output("inf-submit", "disabled"),
    Input("inf-cb-retractation", "value"),
    Input("inf-cb-cgu", "value"),
    Input("inf-cb-cgv", "value"),
    Input("inf-plan-hidden", "value"),
)
def _toggle_submit(retractation, cgu, cgv, plan):
    return not (retractation and cgu and cgv and plan)


@callback(
    Output("inf-cgv-modal", "is_open"),
    Input("inf-cgv-link", "n_clicks"),
    Input("inf-cgv-close", "n_clicks"),
    State("inf-cgv-modal", "is_open"),
    prevent_initial_call=True,
)
def _toggle_cgv(_, __, is_open):
    return not is_open
