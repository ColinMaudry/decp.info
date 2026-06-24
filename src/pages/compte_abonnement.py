from dash import html, register_page

from src.pages._compte_shell import account_guard, account_shell

register_page(
    __name__,
    path="/compte/abonnement",
    title="Abonnement | decp.info",
    name="Abonnement",
    description="Gestion de votre abonnement decp.info.",
)


def layout(**_):
    guard = account_guard("/compte/abonnement", require_subscription=False)
    if guard is not None:
        return guard

    contenu = html.Div(
        [
            html.H2("Abonnement"),
            html.P("La gestion de l'abonnement arrive bientôt."),
        ]
    )
    return account_shell("abonnement", contenu)
