from dash import Input, Output, callback, dash_table, dcc, html, register_page

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
    title=meta_content["title"],
    name=name,
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=0,
)

layout = html.Div(
    className="container",
    children=[
        dcc.Input(
            id="search",
            type="text",
            placeholder="Nom d'acheteur, d'entreprise, mot de clé de marché...",
        ),
        html.Div(
            className="search_options",
            children=[dcc.RadioItems(options=["Acheteur(s)"])],
        ),
        html.Div(id="search_results"),
    ],
)


@callback(
    Output("search_results", "children"),
    Input("search", "value"),
    prevent_initial_call=True,
)
def update_search_results(query):
    if len(query) >= 1:
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
                html.H3(f"{org_type.title()}s : {count}"),
                dash_table.DataTable(
                    columns=columns,
                    data=results.to_dicts(),
                    page_size=5,
                    style_table={"overflowX": "auto"},
                    markdown_options={"html": True},
                )
                if count > 0
                else html.P(f"Aucun {org_type} trouvé."),
            ]
            content.extend(org_content)

        return content
    else:
        return html.P("Tapez au moins 1 caractère")
