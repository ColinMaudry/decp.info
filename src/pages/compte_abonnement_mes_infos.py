import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, register_page
from flask_login import current_user

from src.auth import db as auth_db
from src.pages._compte_shell import account_guard, account_shell
from src.subscriptions import client as frisbii_client
from src.utils.data import get_annuaire_data

register_page(
    __name__,
    path="/compte/abonnement/mes-infos",
    title="Mes informations | Abonnement | colibre",
    name="Mes informations de facturation",
    description="Informations de facturation pour votre abonnement colibre.",
)

_CGU_MARKDOWN = """
L'accès aux fonctionnalités de base de colibre est gratuit et sans inscription.
Un abonnement payant donne accès à des fonctionnalités supplémentaires qui nécessitent la création d'un compte.

#### Fonctionnalités incluses

Les fonctionnalités accessibles aux abonnés évoluent au fil du développement du service.
La liste à jour est visible depuis la [page d'abonnement](/compte/abonnement).

#### Tarifs

Deux formules sont proposées :

- **Abonnement** — 20 € HT / mois (soit 24 € TTC)
- **Abonnement de soutien** — 50 € HT / mois (soit 60 € TTC) — mêmes fonctionnalités, contribution renforcée au projet

La TVA applicable est de 20 %. Les prix TTC sont affichés lors de la souscription.

#### Période d'essai

Une période d'essai gratuite peut être proposée lors de la souscription.
Sa durée est indiquée avant validation. Aucun prélèvement n'est effectué pendant cette période.
À son terme, l'abonnement est activé et facturé automatiquement.

La période d'essai est accordée une seule fois par utilisateur.

#### Facturation et paiement

L'abonnement est facturé mensuellement, à la date anniversaire de la souscription.
Le paiement est traité par [Frisbii](https://www.frisbii.com), prestataire européen de paiement en ligne.
Les coordonnées bancaires sont conservées exclusivement par Frisbii et ne sont pas transmises à colibre.

#### Résiliation

L'abonnement peut être résilié à tout moment depuis l'espace [Mon compte](/compte/abonnement).
La résiliation prend effet à la fin de la période mensuelle en cours : l'accès aux fonctionnalités payantes est maintenu jusqu'à cette date, sans remboursement au prorata.

#### Données stockées

La gestion de l'abonnement implique le traitement de données personnelles, réparties entre colibre et Frisbii (prestataire de paiement).

**Données stockées par colibre :**

- Adresse e-mail (identification du compte)
- Numéro SIRET (si renseigné, conservé pour pré-remplir les futures souscriptions et alimenter des fonctionnalités)

**Données stockées par Frisbii :**

- Informations de facturation : prénom, nom, adresse postale, code postal, ville, pays, nom de l'entreprise
- Informations de paiement : coordonnées bancaires (accessibles uniquement par Frisbii, jamais transmises à colibre)
- Historique des factures

Ces données sont utilisées uniquement pour la gestion de votre abonnement et ne sont pas transmises à des tiers à des fins commerciales.
Conformément au RGPD, vous pouvez demander l'accès, la rectification ou la suppression de vos données en [me contactant](/a-propos/contact).

#### Contact

Pour toute question relative à votre abonnement : [page de contact](/a-propos/contact).
"""


def _csrf_input():
    from flask_wtf.csrf import generate_csrf

    return dcc.Input(type="hidden", name="csrf_token", value=generate_csrf())


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

    plan = query.get("plan", "")
    if not plan:
        return dcc.Location(href="/compte/abonnement", id="inf-no-plan-redirect")

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
            dcc.Input(type="hidden", name="plan", value=plan),
            dbc.Row([col1, col2], className="g-4 mb-4"),
            checkboxes,
            html.Button(
                "Suivant",
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
)
def _toggle_submit(retractation, cgu):
    return not (retractation and cgu)


@callback(
    Output("inf-cgu-modal", "is_open"),
    Input("inf-cgu-link", "n_clicks"),
    Input("inf-cgu-close", "n_clicks"),
    State("inf-cgu-modal", "is_open"),
    prevent_initial_call=True,
)
def _toggle_cgu(_, __, is_open):
    return not is_open
