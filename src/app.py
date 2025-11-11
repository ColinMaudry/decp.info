import logging

import dash_bootstrap_components as dbc
import tomllib
from dash import Dash, dcc, html, page_container, page_registry
from dotenv import load_dotenv
from flask import send_from_directory

load_dotenv()

app = Dash(
    external_stylesheets=[dbc.themes.SIMPLEX],
    title="decp.info",
    use_pages=True,
    compress=True,
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

app.layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.A(children=html.H1("decp.info"), href="/"),
                        html.P(
                            children=html.A(
                                version,
                                href="https://github.com/ColinMaudry/decp.info?tab=readme-ov-file#notes-de-version",
                                target="_blank",
                            ),
                            className="version",
                        ),
                    ],
                    className="logo",
                ),
                html.Div(
                    id="announcements",
                    children=html.P(
                        "ℹ️  Le formulaire de contact a été remplacé par une adresse email"
                    ),
                ),
                html.Div(
                    [
                        dcc.Link(
                            page["name"], href=page["relative_path"], className="nav"
                        )
                        for page in page_registry.values()
                        if page["name"] not in ["Acheteur", "Titulaire", "Marché"]
                    ]
                ),
            ],
            className="navbar",
        ),
        page_container,
    ]
)

if __name__ == "__main__":
    app.run(debug=True)
