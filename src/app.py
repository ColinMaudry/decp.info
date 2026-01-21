import logging
import os

import dash_bootstrap_components as dbc
import tomllib
from dash import Dash, Input, Output, State, dcc, html, page_container, page_registry
from dotenv import load_dotenv
from flask import send_from_directory

load_dotenv()

app = Dash(
    external_stylesheets=[dbc.themes.SIMPLEX],
    title="decp.info",
    use_pages=True,
    compress=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    ],
)
# COSMO (belle font, blue),
# UNITED (rouge, ubuntu font),
# LUMEN (gros séparateur, blue clair),
# SIMPLEX (rouge, séparateur)


# robots.txt
@app.server.route("/robots.txt")
def robots():
    return send_from_directory("./assets", "robots.txt", mimetype="text/plain")


logger = logging.getLogger("decp.info")
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

with open("./pyproject.toml", "rb") as f:
    pyproject = tomllib.load(f)
    version = "v" + pyproject["project"]["version"]


app.index_string = """
<!DOCTYPE html>
<html lang="fr">
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script type="application/javascript">
            console.log("Matomo");
            var _paq = window._paq = window._paq || [];
            /* tracker methods like "setCustomDimension" should be called before "trackPageView" */
            _paq.push(['trackPageView']);
            _paq.push(['enableLinkTracking']);
            (function() {
                var u="//analytics.maudry.com/";
                _paq.push(['setTrackerUrl', u+'matomo.php']);
                _paq.push(['setSiteId', '14']);
                var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0];
                g.async=true; g.src=u+'matomo.js'; s.parentNode.insertBefore(g,s);
            })();
        </script>
    </body>
</html>
"""

navbar = dbc.Navbar(
    dbc.Container(
        fluid=True,
        children=[
            dbc.NavItem(
                children=[
                    dcc.Link(html.H1("decp.info"), href="/", className="logo"),
                    html.P(
                        [
                            html.A(
                                version,
                                href="https://github.com/ColinMaudry/decp.info/blob/main/CHANGELOG.md",
                            )
                        ],
                        className="version",
                    ),
                ],
                style={"min-width": "230px"},
            ),
            dbc.NavItem(
                [dcc.Markdown(os.getenv("ANNOUNCEMENTS"), id="announcements")],
                style={
                    "max-width": "1200px",
                    "display": "inline-block",
                },
            ),
            dbc.NavbarToggler(id="navbar-toggler"),
            dbc.Collapse(
                dbc.Nav(
                    [
                        dbc.NavItem(
                            dbc.NavLink(
                                page["name"].replace(" ", " "),
                                href=page["relative_path"],
                                active="exact",
                            )
                        )
                        for page in page_registry.values()
                        if page["name"] not in ["Acheteur", "Titulaire", "Marché"]
                    ],
                    className="ms-auto",
                    navbar=True,
                ),
                id="navbar-collapse",
                navbar=True,
            ),
        ],
    ),
    color="light",
    dark=False,
    className="mb-4",
    expand="md",
)

app.layout = html.Div(
    [
        dcc.Location(id="url-tracker"),
        navbar,
        dbc.Container(
            page_container,
            id="page-content-container",
            className="mb-4",
        ),
    ]
)


@app.callback(
    Output("navbar-collapse", "is_open"),
    [Input("navbar-toggler", "n_clicks")],
    [State("navbar-collapse", "is_open")],
)
def toggle_navbar_collapse(n, is_open):
    if n:
        return not is_open
    return is_open


@app.callback(
    Output("page-content-container", "fluid"),
    Input("url-tracker", "pathname"),
)
def toggle_container_fluid(pathname):
    if pathname == "/tableau":
        return True
    return False


if __name__ == "__main__":
    app.run(debug=True)
