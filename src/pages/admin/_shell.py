from dash import html


def not_admin():
    return html.Div(
        html.H2("404", id="admin-404-heading"), className="py-5 text-center"
    )
