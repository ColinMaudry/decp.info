from dash import Dash, html, page_container, page_registry, dcc
import dash_bootstrap_components as dbc


app = Dash(external_stylesheets=[dbc.themes.UNITED], title="decp.info", use_pages=True)

app.index_string = """
<!DOCTYPE html>
<html>
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
                html.H1("decp.info"),
                html.Div(
                    [
                        dcc.Link(
                            page["name"], href=page["relative_path"], className="nav"
                        )
                        for page in page_registry.values()
                    ]
                ),
            ],
            className="navbar",
        ),
        page_container,
    ]
)
# @callback(
#     Output(component_id="table", component_property="data", allow_duplicate=True),
#     Input(component_id="search", component_property="value"),
#     prevent_initial_call=True,
# )
# def global_search(text):
#     new_df = df
#     new_df = new_df.filter(pl.col("objet").str.contains("(?i)" + text))
#     return new_df.to_dicts()

if __name__ == "__main__":
    app.run(debug=True)
