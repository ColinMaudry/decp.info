from dash import html, register_page

title = "Statistiques"

register_page(
    __name__, path="/statistiques", title=f"decp.info - {title}", name=title, order=2
)

layout = [html.H2(title)]
