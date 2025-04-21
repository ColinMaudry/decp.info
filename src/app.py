from dash import Dash, html, page_container, page_registry, dcc
import dash_bootstrap_components as dbc


app = Dash(external_stylesheets=[dbc.themes.UNITED], title="decp.info", use_pages=True)


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
