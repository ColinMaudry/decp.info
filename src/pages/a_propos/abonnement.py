import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask_login import current_user

from src.pages._apropos_shell import apropos_shell
from src.subscriptions import db as sub_db
from src.subscriptions import plans
from src.utils import TOUS_ABONNES
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/abonnement",
    title="Abonnement | À propos | colibre",
    description="Conditions d'abonnement à colibre : tarifs, facturation, résiliation et données personnelles.",
    image_url=META_CONTENT["image_url"],
)

abonnement_features = dcc.Markdown("""
    - sauvegarde de vues dans la page Tableau
    - vote pour les [fonctionnalités à développer](/a-propos/roadmap) en priorité (une fois la période d'essai terminée)
      """)


def _plan_card(meta: dict, trial: int | None):
    badge = (
        html.Div(f"{trial} jours d'essai gratuit", className="mb-3") if trial else None
    )
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4(meta["label"], className="mb-1"),
                html.P(
                    f"{meta['prix_ht']} € HT / mois "
                    f"({round(meta['prix_ht'] * 1.2, 2):g} € TTC)",
                    className="text-muted mb-3",
                ),
                html.P(meta["description"], className="mb-3"),
                badge,
            ],
            className="p-4",
        ),
        className="h-100",
    )


def _plan_cards(trial_for=plans.trial_days):
    cards = []
    for key in ("simple", "soutien"):
        meta = plans.plan_meta(key)
        if meta:
            cards.append(_plan_card(meta, trial_for(key)))
    return dbc.Row([dbc.Col(c, md=6) for c in cards], className="g-4 mb-4")


def _explainer():
    col_left = dbc.Col(
        [html.H4("Fonctionnalités réservées aux abonné·es :"), abonnement_features],
        md=6,
        style={
            "borderRight": "1px solid var(--bs-border-color)",
            "paddingRight": "2rem",
        },
    )
    col_right = dbc.Col(
        [
            html.H4("Ce que les abonnements permettent"),
            html.Ul(
                [
                    html.Li(
                        "passer plus de temps à développer colibre et moins de temps "
                        "à chercher des missions"
                    ),
                    html.Li(
                        "rédaction d'études à partir des données, par exemple sur les "
                        "acheteurs dont les données sont introuvables et les raisons "
                        "de cette non-publication."
                    ),
                    html.Li(
                        "fédération des bonnes volontés souhaitant militer pour une "
                        "législation plus ambitieuse sur la transparence de la "
                        "commande publique."
                    ),
                ]
            ),
        ],
        md=6,
        style={"paddingLeft": "2rem"},
    )
    return dbc.Row([col_left, col_right], className="align-items-start pt-2 mb-4")


def _subscribe_button(
    authenticated: bool, has_active_subscription: bool, tous_abonnes: bool
):
    if tous_abonnes:
        return html.Div(
            [
                dbc.Alert(
                    "Les fonctionnalités normalement accessibles contre un abonnement "
                    "mensuel sont accessibles à tous et toutes en attendant "
                    "la validation de mon dossier pour recevoir des paiements par carte bancaire.",
                    color="info",
                ),
                html.A(
                    "Je m'abonne",
                    href="#",
                    className="btn btn-secondary disabled",
                ),
            ],
            className="text-center my-4",
        )
    if authenticated and has_active_subscription:
        label, href = "Gérer mon abonnement", "/compte/abonnement"
    elif authenticated:
        label, href = "Je m'abonne", "/compte/abonnement/mes-infos"
    else:
        label, href = "Je m'abonne", "/inscription"
    return html.Div(
        html.A(label, href=href, className="btn btn-primary"),
        className="text-center my-4 btn-lg",
        style={"width": "fit-content", "margin": "auto"},
    )


subscription_terms = html.Div(
    [
        html.H2("Abonnement"),
        dcc.Markdown(
            """
L'accès aux fonctionnalités de base de colibre est gratuit et sans inscription. Il est également possible de créer un compte gratuitement via le menu [Connexion](/connexion). Une fois le compte créé,
il est possible de souscrire à un abonnement mensuel qui donne accès à des fonctionnalités supplémentaires. Cet abonnement s'adresse tant aux professionnel·les qu'aux particuliers.
"""
        ),
        html.H4("Tarifs"),
        dcc.Markdown(
            """
Deux formules sont proposées :

- **Abonnement** — 20 € HT / mois (soit 24 € TTC)
- **Abonnement de soutien ✊** — 50 € HT / mois (soit 60 € TTC) — mêmes fonctionnalités, contribution renforcée au projet

La TVA applicable en France est de 20 %.
"""
        ),
        html.H4("Modes de paiement"),
        dcc.Markdown(
            """
Les cartes bancaires des réseaux Visa et Mastercard sont acceptées.

Il est également possible de payer par virement bancaire à condition de payer un an d'abonnement.
"""
        ),
        html.H4("Période d'essai"),
        dcc.Markdown(
            """
Une période d'essai gratuite est proposée lors de la souscription.
Sa durée est indiquée avant validation. Aucun prélèvement n'est effectué pendant cette période.
À son terme, l'abonnement est activé et facturé automatiquement.

La période d'essai est accordée une seule fois par compte.
"""
        ),
        html.H4("Facturation et paiement"),
        dcc.Markdown(
            """
L'abonnement est facturé mensuellement, à la date anniversaire de la souscription, et donne lieu à l'émission d'une facture visible sur le compte de l'abonné·e.
Le paiement est traité par [Frisbii](https://www.frisbii.com), prestataire européen de paiement en ligne.
Les coordonnées bancaires sont conservées exclusivement par Frisbii et ne sont pas transmises à colibre.
"""
        ),
        html.H4("Résiliation"),
        dcc.Markdown(
            """
L'abonnement peut être résilié à tout moment depuis l'espace [Mon compte](/compte/abonnement).
La résiliation prend effet à la fin de la période mensuelle en cours : l'accès aux fonctionnalités payantes est maintenu jusqu'à cette date, sans remboursement au prorata.
"""
        ),
        html.H4("Données recueillies"),
        dcc.Markdown(
            """
La gestion de l'abonnement implique le traitement de données, réparties entre colibre et Frisbii (prestataire de paiement). Conformément au RGPD,
colibre ne receuille que les données strictement nécessaires
au bon fonctionnement du site et de la facturation.

**Données stockées par Colmo pour l'administration de colibre :**

- Adresse e-mail (identification du compte)
- Numéro SIRET (optionnel, si renseigné, conservé pour pré-remplir les futures souscriptions)

**Données stockées par Frisbii :**

- Informations de facturation : prénom et nom (et nom et SIRET de l'organisme si applicable), adresse postale, code postal, ville, pays
- Informations de paiement : coordonnées bancaires
- Historique des factures

Ces données sont utilisées uniquement pour la gestion de votre abonnement et ne sont pas transmises à des tiers à des fins commerciales.
Conformément au RGPD, vous pouvez demander l'accès, la rectification ou la suppression de vos données en [me contactant](/a-propos/contact).
"""
        ),
        html.H4("Contact"),
        dcc.Markdown(
            "Pour toute question relative à votre abonnement : [page de contact](/a-propos/contact)."
        ),
    ]
)


def layout(**_):
    authenticated = current_user.is_authenticated
    has_active = authenticated and sub_db.has_active_subscription(current_user.id)
    body = html.Div(
        [
            _plan_cards(),
            _subscribe_button(authenticated, has_active, TOUS_ABONNES),
            _explainer(),
            subscription_terms,
        ]
    )
    return apropos_shell("abonnement", body)
