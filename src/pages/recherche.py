from dash import Input, Output, callback, dcc, html, register_page

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
    title=meta_content["title"],
    name=name,
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=0,
)

layout = html.Div(
    className="container",
    children=[
        html.Div(
            className="tagline",
            children=html.P(
                "Exploration et téléchargement des données des marchés publics"
            ),
        ),
        dcc.Input(
            id="search",
            type="text",
            placeholder="Nom d'acheteur/entreprise, SIREN/SIRET, code département",
            autoFocus=True,
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

        return content
    else:
        return html.P("")
