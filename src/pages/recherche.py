from dash import Input, Output, State, callback, dcc, html, register_page

from src.figures import DataTable
from src.utils import (
    df_acheteurs,
    df_titulaires,
    meta_content,
    search_org,
    setup_table_columns,
)

name = "Recherche"

register_page(
    __name__,
    path="/",
    title="Recherche de marchés publics | decp.info",
    name=name,
    description="Explorez et analysez les données des marchés publics français avec cet outil libre et gratuit. Pour une commande publique accessible à toutes et tous.",
    image_url=meta_content["image_url"],
    order=0,
)

layout = html.Div(
    className="container",
    children=[
        html.Div(
            className="tagline",
            children=html.P("Recherchez un acheteur ou un titulaire de marché public"),
        ),
        html.Div(
            style={
                "display": "flex",
                "justifyContent": "center",
                "marginTop": "30px",
                "marginBottom": "30px",
            },
            children=[
                dcc.Input(
                    id="search",
                    type="text",
                    placeholder="Nom d'acheteur/entreprise, SIREN/SIRET, code département",
                    autoFocus=True,
                    style={
                        "margin": "0",
                        "width": "500px",
                        "border": "1px solid #ccc",
                        "borderRight": "none",
                        "borderRadius": "3px 0 0 3px",
                        "padding": "5px 10px",
                        "outline": "none",
                        "height": "34px",
                    },
                ),
                html.Button(
                    "=>",
                    id="search-button",
                    className="btn btn-primary",
                    style={
                        "border": "1px solid #ccc",
                        "borderRadius": "0 3px 3px 0",
                        "marginLeft": "0",
                        "height": "auto",  # Ensure it matches input height if necessary, often relying on padding/line-height
                    },
                ),
            ],
        ),
        html.P(
            [
                "...ou bien filtrez les marchés publics dans la vue ",
                dcc.Link("Tableau", href="/tableau"),
            ],
            style={"textAlign": "center"},
            id="mention_tableau",
        ),
        # html.Div(
        #     className="search_options",
        #     children=[dcc.RadioItems(options=["Acheteur(s)"])],
        # ),
        html.Div(id="search_results", className="wrapper"),
    ],
)


@callback(
    Output("search_results", "children"),
    Output("mention_tableau", "style"),
    Input("search", "n_submit"),
    Input("search-button", "n_clicks"),
    State("search", "value"),
    prevent_initial_call=True,
)
def update_search_results(n_submit, n_clicks, query):
    if query and len(query) >= 1:
        content = []

        for org_type in ["acheteur", "titulaire"]:
            if org_type == "acheteur":
                dff = df_acheteurs
            elif org_type == "titulaire":
                dff = df_titulaires
            else:
                raise ValueError(f"{org_type} is not supported")

            # Search acheteurs and titulaires using the same function
            results = search_org(dff, query, org_type=org_type)
            count = results.height

            # Format output
            columns, tooltip = setup_table_columns(results, hideable=False)

            org_content = [
                html.Div(
                    className=f"results_{org_type}",
                    children=[
                        html.H3(f"{org_type.title()}s : {count}"),
                        DataTable(
                            dtid=f"results_{org_type}_datatable",
                            columns=columns,
                            data=results.to_dicts(),
                            page_size=10,
                            sort_action="none",
                            filter_action="none",
                        ),
                    ],
                )
                if count > 0
                else html.P(f"Aucun {org_type} trouvé."),
            ]
            content.extend(org_content)
            style = {"textAlign": "center", "display": "none"}

        return content, style
    return html.P(""), {"textAlign": "center"}
