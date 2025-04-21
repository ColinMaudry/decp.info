from dash import register_page, html, page_registry

title = "À propos"

register_page(
    __name__, path="/a-propos", title=f"decp.info - {title}", name=title, order=3
)

layout = [html.H2(title)]
