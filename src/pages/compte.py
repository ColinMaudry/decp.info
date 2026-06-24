from dash import dcc, register_page

register_page(
    __name__,
    path="/compte",
    title="Mon compte | decp.info",
    name="Mon compte",
    description="Redirection vers la gestion de compte.",
)


def layout(**_):
    return dcc.Location(href="/compte/admin", id="compte-root-redirect")
