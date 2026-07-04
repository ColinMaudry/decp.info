import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, ctx, dcc, html, register_page
from flask_login import current_user

from src.auth import db as auth_db
from src.pages._compte_shell import account_guard, account_shell
from src.pages.a_propos.abonnement import _plan_card, subscription_terms
from src.subscriptions import client as frisbii_client
from src.subscriptions import db as sub_db
from src.subscriptions import plans
from src.utils.data import get_annuaire_data

register_page(
    __name__,
    path="/compte/abonnement/mes-infos",
    title="Mes informations | Abonnement | colibre",
    name="Mes informations de facturation",
    description="Informations de facturation pour votre abonnement colibre.",
)

_CGU_MARKDOWN = subscription_terms


def _csrf_input():
    from flask_wtf.csrf import generate_csrf

    return dcc.Input(type="hidden", name="csrf_token", value=generate_csrf())


def _trial_for(user_id):
    used = sub_db.has_used_trial(user_id)
    return lambda key: None if used else plans.trial_days(key)


def _selectable_cards(trial_for):
    cols = []
    for key in ("simple", "soutien"):
        meta = plans.plan_meta(key)
        if not meta:
            continue
        cols.append(
            dbc.Col(
                html.Div(
                    _plan_card(meta, trial_for(key)),
                    id=f"plan-card-{key}",
                    n_clicks=0,
                    className="plan-selectable",
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
        "d-none",
    )


@callback(
    Output("inf-plan-hidden", "value"),
    Output("plan-card-simple", "className"),
    Output("plan-card-soutien", "className"),
    Output("inf-plan-invite", "className"),
    Input("plan-card-simple", "n_clicks"),
    Input("plan-card-soutien", "n_clicks"),
    prevent_initial_call=True,
)
def _select_plan(_n_simple, _n_soutien):
    selected = "simple" if ctx.triggered_id == "plan-card-simple" else "soutien"
    return _selection_state(selected)


def _cgu_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Conditions générales d'utilisation")),
            dbc.ModalBody(
                dcc.Markdown(_CGU_MARKDOWN),
                style={"maxHeight": "60vh", "overflowY": "auto"},
            ),
            dbc.ModalFooter(
                dbc.Button(
                    "Fermer", id="inf-cgu-close", className="ms-auto", color="secondary"
                )
            ),
        ],
        id="inf-cgu-modal",
        size="lg",
        is_open=False,
    )


def layout(**query):
    guard = account_guard("/compte/abonnement/mes-infos", require_subscription=False)
    if guard is not None:
        return guard

    prefill: dict = {}
    try:
        prefill = frisbii_client.get_customer(f"colibre-{current_user.id}")
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
            dbc.Label("Nom de l'entreprise"),
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

    checkboxes = html.Div(
        [
            dcc.Markdown(
                "Si vous préférez régler par virement bancaire et une facturation annuelle plutôt qu'un réglement mensuel automatique par carte bancaire, [contactez-moi](/a-propos/contact)."
            ),
            dcc.Checklist(
                id="inf-cb-retractation",
                options=[
                    {
                        "label": "Je renonce à mon droit de rétractation légal de 14 jours.",
                        "value": "ok",
                    }
                ],
                value=[],
                className="mb-2",
            ),
            dcc.Checklist(
                id="inf-cb-cgu",
                options=[
                    {
                        "label": [
                            "J'ai lu et accepte les ",
                            html.A(
                                "conditions générales d'utilisation du service",
                                href="#",
                                id="inf-cgu-link",
                                style={"cursor": "pointer"},
                            ),
                            ".",
                        ],
                        "value": "ok",
                    }
                ],
                value=[],
                className="mb-4",
            ),
        ]
    )

    form = html.Form(
        method="POST",
        action="/subscriptions/subscribe",
        children=[
            _csrf_input(),
            html.Div(
                "Choisissez votre formule :",
                id="inf-plan-invite",
                className="fw-bold mb-2",
            ),
            _selectable_cards(_trial_for(current_user.id)),
            dcc.Input(type="hidden", id="inf-plan-hidden", name="plan", value=""),
            dbc.Row([col1, col2], className="g-4 mb-4"),
            checkboxes,
            html.Button(
                "Ajout d'une carte de paiement",
                id="inf-submit",
                type="submit",
                className="btn btn-primary",
                disabled=True,
            ),
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
                _cgu_modal(),
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
    Input("inf-plan-hidden", "value"),
)
def _toggle_submit(retractation, cgu, plan):
    return not (retractation and cgu and plan)


@callback(
    Output("inf-cgu-modal", "is_open"),
    Input("inf-cgu-link", "n_clicks"),
    Input("inf-cgu-close", "n_clicks"),
    State("inf-cgu-modal", "is_open"),
    prevent_initial_call=True,
)
def _toggle_cgu(_, __, is_open):
    return not is_open
