from dash import dcc, html, register_page

from src.pages._apropos_shell import apropos_shell
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/abonnement",
    title="Abonnement | À propos | decp.info",
    description="Conditions d'abonnement à decp.info : tarifs, facturation, résiliation et données personnelles.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    contenu = html.Div(
        [
            html.H2("Abonnement"),
            dcc.Markdown(
                """
L'accès aux fonctionnalités de base de decp.info est gratuit et sans inscription.
Un abonnement payant donne accès à des fonctionnalités supplémentaires qui nécessitent la création d'un compte.
"""
            ),
            html.H4("Fonctionnalités incluses"),
            dcc.Markdown(
                """
Les fonctionnalités accessibles aux abonnés évoluent au fil du développement du service.
La liste à jour est visible depuis la [page d'abonnement](/compte/abonnement).
"""
            ),
            html.H4("Tarifs"),
            dcc.Markdown(
                """
Deux formules sont proposées :

- **Abonnement** — 20 € HT / mois (soit 24 € TTC)
- **Abonnement de soutien** — 50 € HT / mois (soit 60 € TTC) — mêmes fonctionnalités, contribution renforcée au projet

La TVA applicable est de 20 %. Les prix TTC sont affichés lors de la souscription.
"""
            ),
            html.H4("Période d'essai"),
            dcc.Markdown(
                """
Une période d'essai gratuite peut être proposée lors de la souscription.
Sa durée est indiquée avant validation. Aucun prélèvement n'est effectué pendant cette période.
À son terme, l'abonnement est activé et facturé automatiquement.

La période d'essai est accordée une seule fois par utilisateur.
"""
            ),
            html.H4("Facturation et paiement"),
            dcc.Markdown(
                """
L'abonnement est facturé mensuellement, à la date anniversaire de la souscription.
Le paiement est traité par [Frisbii](https://www.frisbii.com), prestataire de paiement en ligne.
Les coordonnées bancaires sont conservées exclusivement par Frisbii et ne sont pas transmises à decp.info.
"""
            ),
            html.H4("Résiliation"),
            dcc.Markdown(
                """
L'abonnement peut être résilié à tout moment depuis l'espace [Mon compte](/compte/abonnement).
La résiliation prend effet à la fin de la période mensuelle en cours : l'accès aux fonctionnalités payantes est maintenu jusqu'à cette date, sans remboursement au prorata.
"""
            ),
            html.H4("Droit de rétractation"),
            dcc.Markdown(
                """
Conformément à l'article L221-18 du Code de la consommation, vous disposez d'un délai de 14 jours à compter de la souscription pour exercer votre droit de rétractation, sans motif à fournir.

Si vous avez demandé l'accès immédiat au service et que vous l'avez effectivement utilisé, une partie proportionnelle à l'utilisation peut être déduite du remboursement.

Pour exercer ce droit, [contactez-nous](/a-propos/contact).
"""
            ),
            html.H4("Données personnelles"),
            dcc.Markdown(
                """
La gestion de l'abonnement nécessite le traitement des données suivantes :

- adresse e-mail (identification du compte)
- historique de facturation (fourni par Frisbii)

Ces données sont utilisées uniquement pour la gestion de votre abonnement et ne sont pas transmises à des tiers à des fins commerciales.
Conformément au RGPD, vous pouvez demander l'accès, la rectification ou la suppression de vos données via la [page de contact](/a-propos/contact).
"""
            ),
            html.H4("Contact"),
            dcc.Markdown(
                "Pour toute question relative à votre abonnement : [page de contact](/a-propos/contact)."
            ),
        ]
    )
    return apropos_shell("abonnement", contenu)
