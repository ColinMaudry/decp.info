import json
import os
import urllib.parse
from datetime import datetime

import polars as pl
from dash import Input, Output, State, callback, dcc, html, no_update, register_page

from src.figures import DataTable
from src.utils import (
    df,
    filter_table_data,
    get_default_hidden_columns,
    invert_columns,
    meta_content,
    schema,
    sort_table_data,
)
from utils import prepare_table_data

update_date = os.path.getmtime(os.getenv("DATA_FILE_PARQUET_PATH"))
update_date = datetime.fromtimestamp(update_date).strftime("%d/%m/%Y")


name = "Tableau"
register_page(
    __name__,
    path="/tableau",
    title=meta_content["title"],
    name=name,
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=1,
)

datatable = html.Div(
    className="marches_table",
    children=DataTable(
        dtid="table",
        page_size=20,
        page_action="custom",
        filter_action="custom",
        sort_action="custom",
        hidden_columns=get_default_hidden_columns(None),
        columns=[{"id": col, "name": col} for col in df.columns],
    ),
)

layout = [
    dcc.Location(id="url", refresh=False),
    html.Div(
        html.Details(
            children=[
                html.Summary(
                    html.H3("Mode d'emploi", style={"textDecoration": "underline"}),
                ),
                dcc.Markdown(
                    dangerously_allow_html=True,
                    children="""
    ##### Définition des colonnes

    Pour voir la définition d'une colonne, passez votre souris sur son en-tête.

    ##### Filtres

    Vous pouvez appliquer un filtre pour chaque colonne en entrant du texte sous le nom de la colonne, puis en tapant sur `Entrée`.

    - Champs textuels : la recherche est insensible à la casse (majuscules/minuscules) et retourne les valeurs qui contiennent
    le texte recherché. Exemple : `rennes` retourne "RENNES METROPOLE". Lorsque vous ouvrez une URL de vue, le format équivalent `icontains rennes` est utilisé.
    - Champs numériques : vous pouvez soit taper un nombre pour trouver les valeurs égales, soit le précéder de **>** ou **<** pour filtrer les valeurs supérieures ou inférieures. Exemple pour les offres reçues : `> 4` retourne les marchés ayant reçu plus de 4 offres.
    - Champs date : vous pouvez également utiliser **>** ou **<**. Exemples : `< 2024-01-31` pour "avant le 31 janvier 2024",
    `2024` pour "en 2024", `> 2022` pour "à partir de 2022". Lorsque vous ouvrez une URL de vue, le format équivalent `i<` ou `i>` est utilisé.

    Vous pouvez filtrer plusieurs colonnes à la fois. Vos filtres sont remis à zéro quand vous rafraîchissez la page.

    ##### Tri

    Pour trier une colonne, utilisez les flèches grises à côté des noms de colonnes. Chaque clic change le tri dans cet ordre : tri ascendant, tri descendant, pas de tri.

    ##### Partager une vue

    Une vue est un ensemble de filtres, de tris et de choix de colonnes que vous avez appliqué. Vous pouvez copier une adresse Web qui reproduit la vue courante à l'identique en cliquant sur l'icône <img src="/assets/copy.svg" alt="drawing" width="20"/>. En la collant dans la barre d'adresse d'un navigateur, vous ouvrez la vue Tableau avec les mêmes paramètres.

    Pratique pour partager une vue avec un·e collègue, sur les réseaux sociaux, ou la sauvegarder pour plus tard.

    ##### Télécharger le résultat

    Vous pouvez télécharger le résultat de vos filtres et tris, pour les colonnes affichées, en cliquant sur **Télécharger au format Excel**.

    ##### Liens

    Les liens dans les colonnes Identifiant unique, Acheteur et Titulaire vous permettent de consulter une vue qui leur est dédiée
    (informations, marchés attribués/remportés, etc.)

    """,
                ),
            ],
            id="instructions",
        ),
        id="header",
    ),
    # html.Div(
    #     [
    #         "Recherche dans objet : ",
    #         dcc.Input(id="search", value="", type="text"),
    #     ]
    # )]),
    dcc.Loading(
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        id="loading-home",
        type="default",
        children=[
            html.Div(
                [
                    html.P("lignes", id="nb_rows"),
                    html.Div(id="copy-container"),
                    dcc.Input(id="share-url", readOnly=True, style={"display": "none"}),
                    html.Button(
                        "Téléchargement désactivé au-delà de 65 000 lignes",
                        id="btn-download-data",
                        disabled=True,
                    ),
                    dcc.Download(id="download-data"),
                    dcc.Store(id="filtered_data", storage_type="memory"),
                    html.P("Données mises à jour le " + str(update_date)),
                ],
                className="table-menu",
            ),
            datatable,
        ],
    ),
]


@callback(
    Output("table", "data"),
    Output("table", "columns"),
    Output("table", "tooltip_header"),
    Output("table", "data_timestamp"),
    Output("nb_rows", "children"),
    Output("btn-download-data", "disabled"),
    Output("btn-download-data", "children"),
    Output("btn-download-data", "title"),
    Input("table", "page_current"),
    Input("table", "page_size"),
    Input("table", "filter_query"),
    Input("table", "sort_by"),
    State("table", "data_timestamp"),
)
def update_table(page_current, page_size, filter_query, sort_by, data_timestamp):
    # if ctx.triggered_id != "url":
    #     search_params = None
    # else:
    #     search_params = urllib.parse.parse_qs(search_params.lstrip("?"))
    return prepare_table_data(
        None, data_timestamp, filter_query, page_current, page_size, sort_by
    )


@callback(
    Output("download-data", "data"),
    Input("btn-download-data", "n_clicks"),
    State("table", "filter_query"),
    State("table", "sort_by"),
    State("table", "hidden_columns"),
    prevent_initial_call=True,
)
def download_data(n_clicks, filter_query, sort_by, hidden_columns: list = None):
    lff: pl.LazyFrame = df.lazy()  # start from the original data

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        lff = filter_table_data(lff, filter_query)

    if len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    def to_bytes(buffer):
        lff.collect(engine="streaming").write_excel(buffer, worksheet="DECP")

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.xlsx")


@callback(
    Output("table", "filter_query"),
    Output("table", "sort_by"),
    Output("table", "hidden_columns"),
    Output("url", "search", allow_duplicate=True),
    Input("url", "search"),
    prevent_initial_call=True,
)
def restore_view_from_url(search):
    if not search:
        return no_update, no_update, no_update, no_update

    params = urllib.parse.parse_qs(search.lstrip("?"))
    print("params", params)

    filter_query = no_update
    sort_by = no_update
    hidden_columns = no_update

    if "filtres" in params:
        filter_query = params["filtres"][0]

    if "tris" in params:
        try:
            sort_by = json.loads(params["tris"][0])
        except json.JSONDecodeError:
            pass

    if "colonnes" in params:
        columns = params["colonnes"][0].split(",")
        verified_columns = [column for column in columns if column in schema.names()]
        hidden_columns = invert_columns(verified_columns)

    return filter_query, sort_by, hidden_columns, ""


@callback(
    Output("share-url", "value"),
    Output("copy-container", "children"),
    Input("table", "filter_query"),
    Input("table", "sort_by"),
    Input("table", "hidden_columns"),
    State("url", "href"),
)
def sync_url_and_reset_button(filter_query, sort_by, hidden_columns, href):
    if not href:
        return no_update, no_update

    # Extract base URL (remove existing query params)
    base_url = href.split("?")[0]

    params = {}
    if filter_query:
        params["filtres"] = filter_query

    if sort_by:
        params["tris"] = json.dumps(sort_by)

    if hidden_columns:
        columns = invert_columns(hidden_columns)
        columns = ",".join(columns)
        params["colonnes"] = columns

    query_string = urllib.parse.urlencode(params)
    full_url = f"{base_url}?{query_string}" if query_string else base_url

    copy_button = dcc.Clipboard(
        id="btn-copy-url",
        target_id="share-url",
        title="Copier l'URL de cette vue",
        style={
            "display": "inline-block",
            "fontSize": 20,
            "verticalAlign": "top",
            "cursor": "pointer",
        },
        className="fa fa-link",
    )

    return full_url, copy_button


@callback(
    Output("copy-container", "children", allow_duplicate=True),
    Input("btn-copy-url", "n_clicks", allow_optional=True),
    prevent_initial_call=True,
)
def show_confirmation(n_clicks):
    if n_clicks:
        return html.Span(
            "Adresse de la vue copiée",
            style={"color": "green", "fontWeight": "bold", "marginLeft": "10px"},
        )
    return no_update
