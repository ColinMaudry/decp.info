import json
import os
import urllib.parse
import uuid
from datetime import datetime

import dash_bootstrap_components as dbc
import polars as pl
from dash import (
    ClientsideFunction,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    dcc,
    html,
    no_update,
    register_page,
)

from figures import make_column_picker
from src.figures import DataTable
from src.utils import (
    add_canonical_link,
    columns,
    df,
    filter_table_data,
    get_default_hidden_columns,
    invert_columns,
    logger,
    meta_content,
    schema,
    sort_table_data,
)
from utils import prepare_table_data

update_date_timestamp = os.path.getmtime(os.getenv("DATA_FILE_PARQUET_PATH"))
update_date = datetime.fromtimestamp(update_date_timestamp).strftime("%d/%m/%Y")
update_date_iso = datetime.fromtimestamp(update_date_timestamp).isoformat()


name = "Tableau"
register_page(
    __name__,
    path="/tableau",
    title="Tableau des marchés publics | decp.info",
    name=name,
    description="Consultez, filtrez et exportez les données essentielles de la commande publique sous forme de tableau.",
    image_url=meta_content["image_url"],
    order=1,
)

datatable = html.Div(
    className="marches_table",
    children=DataTable(
        dtid="tableau_datatable",
        page_size=20,
        page_action="custom",
        filter_action="custom",
        sort_action="custom",
        hidden_columns=[],
        columns=[{"id": col, "name": col} for col in df.columns],
    ),
)

layout = [
    dcc.Location(id="tableau_url", refresh=False),
    dcc.Store(id="filter-cleanup-trigger"),
    dcc.Store(id="tableau-hidden-columns", storage_type="local"),
    dcc.Store(id="tableau-filters", storage_type="local"),
    dcc.Store(id="tableau-sort", storage_type="local"),
    dcc.Store(id="tableau-table"),
    html.Script(
        type="application/ld+json",
        id="dataset_jsonld",
        children=[
            json.dumps(
                {
                    "@context": "https://schema.org/",
                    "@type": "Dataset",
                    "name": "Données essentielles des marchés publics français (DECP)",
                    "description": "Données de marchés publics exhaustives décrivant les marchés publics attribués en France depuis 2018.",
                    "url": "https://decp.info",
                    "sameAs": "https://www.data.gouv.fr/datasets/608c055b35eb4e6ee20eb325",
                    "keywords": [
                        "marchés publics",
                        "commande publique",
                        "decp",
                        "public procurement",
                    ],
                    "license": "https://www.etalab.gouv.fr/licence-ouverte-open-licence",
                    "isAccessibleForFree": True,
                    "creator": {
                        "@type": "Organization",
                        "url": "https://colmo.tech",
                        "name": "Colmo",
                        "sameAs": "https://annuaire-entreprises.data.gouv.fr/entreprise/colmo-989393350",
                        "contactPoint": {
                            "@type": "ContactPoint",
                            "contactType": "Support et contact commercial",
                            "email": "colin@colmo.tech",
                        },
                    },
                    "includedInDataCatalog": {
                        "@type": "DataCatalog",
                        "name": "data.gouv.fr",
                    },
                    "distribution": [
                        {
                            "@type": "DataDownload",
                            "encodingFormat": "CSV",
                            "contentUrl": "https://www.data.gouv.fr/api/1/datasets/r/22847056-61df-452d-837d-8b8ceadbfc52",
                        },
                        {
                            "@type": "DataDownload",
                            "encodingFormat": "Parquet",
                            "contentUrl": "https://www.data.gouv.fr/api/1/datasets/r/11cea8e8-df3e-4ed1-932b-781e2635e432",
                        },
                    ],
                    "temporalCoverage": f"2018-01-01/{update_date_iso[:10]}",
                    "spatialCoverage": {
                        "@type": "Place",
                        "address": {"countryCode": "FR"},
                    },
                },
                indent=2,
            )
        ],
    ),
    dcc.Markdown(
        f"Ce tableau vous permet d'appliquer un filtre sur une ou plusieurs colonnes, et ainsi produire la liste de marchés dont vous avez besoin ([exemple de filtre](/tableau?filtres=%7Bacheteur_id%7D+icontains+24350013900189+%26%26+%7BdateNotification%7D+icontains+2025%2A+%26%26+%7Bmontant%7D+i%3C+40000+%26%26+%7Bobjet%7D+icontains+voirie&colonnes=uid%2Cacheteur_id%2Cacheteur_nom%2Ctitulaire_id%2Ctitulaire_nom%2Cobjet%2Cmontant%2CdureeMois%2CdateNotification%2Cacheteur_departement_code%2CsourceDataset)). Par défaut seules quelques colonnes sont affichées, mais vous pouvez en afficher jusqu'à {str(df.width)} en cliquant sur le bouton **Colonnes affichées**. Cet outil est assez puissant, je vous recommande de lire le mode d'emploi pour en tirer pleinement partie.",
        style={"maxWidth": "1000px"},
    ),
    html.Div(
        [],
        id="header",
    ),
    dcc.Loading(
        overlay_style={"visibility": "visible", "filter": "blur(2px)"},
        id="loading-home",
        type="default",
        children=[
            html.Div(
                [
                    # Modal du mode d'emploi
                    dbc.Button("Mode d'emploi", id="tableau_help_open"),
                    dbc.Modal(
                        [
                            dbc.ModalHeader(dbc.ModalTitle("Header")),
                            dbc.ModalBody(
                                dcc.Markdown(
                                    dangerously_allow_html=True,
                                    children=f"""
            ##### Définition des colonnes

            Pour voir la définition d'une colonne, passez votre souris sur son en-tête.

            ##### Appliquer des filtres

            Vous pouvez appliquer un filtre pour chaque colonne en entrant du texte sous le nom de la colonne, puis en tapant sur `Entrée`.

            - Champs textuels : la recherche retourne les valeurs qui contiennent le texte recherché et n'est pas sensible à la casse (majuscules/minuscules).
                - Exemple : `rennes` retourne "RENNES METROPOLE".
                - Les guillemets simples (apostrophe du 4) doivent être prédédées d'une barre oblique (AltGr + 8). Exemple : `services d\\\'assurances`
            - Champs numériques (Durée en mois, Montant, ...) : vous pouvez...
                - soit taper un nombre pour trouver les valeurs strictement égales. Exemple : `12` ne retourne que des 12
                - soit le précéder de **>** ou **<** pour filtrer les valeurs supérieures ou inférieures. Exemple pour les offres reçues : `> 4` retourne les marchés ayant reçu plus de 4 offres.
            - Champs date (Date de notification, ...) : vous pouvez également utiliser **>** ou **<**. Exemples :
                - `< 2024-01-31` pour "avant le 31 janvier 2024"
                - `2024` pour "en 2024", `> 2022` pour "à partir de 2022".
            - Pour les champs textuels et les champs dates :
                - pour chercher du texte qui **commence par** votre texte, entrez `texte*`. C'est par exemple utile pour filtrer des acheteurs ou titulaires par numéro SIREN (`123456789*`) ou les marchés sur une année en particulier (`2024*`)
                - pour chercher du texte qui **finit par** votre texte, entrez `*texte`

            Vous pouvez filtrer plusieurs colonnes à la fois. Vos filtres sont remis à zéro quand vous rafraîchissez la page.

            ##### Trier les données

            Pour trier une colonne, utilisez les flèches grises à côté des noms de colonnes. Chaque clic change le tri dans cet ordre :

            1. tri croissant
            2. tri décroissant
            3. pas de tri

            ##### Afficher plus de colonnes

            Par défaut, un nombre réduit de colonnes est affiché pour ne pas surcharger la page. Mais vous avez le choix parmi {str(df.width)} colonnes, ce serait dommage de vous limiter !

            Pour afficher plus de colonnes, cliquez sur le bouton **Colonnes affichées** et cochez les colonnes pour les afficher.

            ##### Partager une vue

            Une vue est un ensemble de filtres, de tris et de choix de colonnes que vous avez appliqués. Cliquez sur l'icône <img src="/assets/copy.svg" alt="drawing" width="20"/> pour copier une adresse Web qui reproduit la vue courante à l'identique : en la collant dans la barre d'adresse d'un navigateur, vous ouvrez la vue Tableau avec les mêmes paramètres.

            Pratique pour partager une vue avec un·e collègue, sur les réseaux sociaux, ou la sauvegarder pour plus tard.

            ##### Télécharger le résultat

            Vous pouvez télécharger le résultat de vos filtres et tris, pour les colonnes affichées, en cliquant sur **Télécharger au format Excel**.

            ##### Liens

            Les liens dans les colonnes Identifiant unique, Acheteur et Titulaire vous permettent de consulter une vue qui leur est dédiée
            (informations, marchés attribués/remportés, etc.)

            """,
                                ),
                            ),
                            dbc.ModalFooter(
                                dbc.Button(
                                    "Fermer",
                                    id="tableau_help_close",
                                    className="ms-auto",
                                    n_clicks=0,
                                )
                            ),
                        ],
                        id="tableau_help",
                        is_open=False,
                        fullscreen="md-down",
                        scrollable=True,
                        size="lg",
                    ),
                    # Bouton modal des colonnes affichées
                    dbc.Button(
                        "Colonnes affichées",
                        id="tableau_columns_open",
                        className="column_list",
                    ),
                    html.P("lignes", id="nb_rows"),
                    html.Div(id="copy-container"),
                    dcc.Input(id="share-url", readOnly=True, style={"display": "none"}),
                    dbc.Button(
                        "Téléchargement désactivé au-delà de 65 000 lignes",
                        id="btn-download-data",
                        disabled=True,
                    ),
                    dcc.Download(id="download-data"),
                    dcc.Store(id="filtered_data", storage_type="memory"),
                    html.P("Données mises à jour le " + str(update_date)),
                    dbc.Button(
                        "Remise à zéro",
                        title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                        id="btn-tableau-reset",
                    ),
                ],
                className="table-menu",
            ),
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Choix des colonnes à afficher")),
                    dbc.ModalBody(
                        id="tableau_columns_body",
                        children=make_column_picker("tableau"),
                    ),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Fermer",
                            id="tableau_columns_close",
                            className="ms-auto",
                            n_clicks=0,
                        )
                    ),
                ],
                id="tableau_columns",
                is_open=False,
                fullscreen="md-down",
                scrollable=True,
                size="xl",
            ),
            datatable,
        ],
    ),
]


@callback(
    Output("tableau_datatable", "data"),
    Output("tableau_datatable", "columns"),
    Output("tableau_datatable", "tooltip_header"),
    Output("tableau_datatable", "data_timestamp"),
    Output("nb_rows", "children"),
    Output("btn-download-data", "disabled"),
    Output("btn-download-data", "children"),
    Output("btn-download-data", "title"),
    Input("tableau_datatable", "page_current"),
    Input("tableau_datatable", "page_size"),
    Input("tableau-filters", "data"),
    Input("tableau-sort", "data"),
    State("tableau_datatable", "data_timestamp"),
)
def update_table(page_current, page_size, filter_query, sort_by, data_timestamp):
    # if ctx.triggered_id != "url":
    #     search_params = None
    # else:
    #     search_params = urllib.parse.parse_qs(search_params.lstrip("?"))
    return prepare_table_data(
        None, data_timestamp, filter_query, page_current, page_size, sort_by, "tableau"
    )


@callback(
    Output("download-data", "data"),
    Input("btn-download-data", "n_clicks"),
    State("tableau_datatable", "filter_query"),
    State("tableau_datatable", "sort_by"),
    State("tableau_datatable", "hidden_columns"),
    prevent_initial_call=True,
)
def download_data(n_clicks, filter_query, sort_by, hidden_columns: list = None):
    lff: pl.LazyFrame = df.lazy()  # start from the original data

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        lff = filter_table_data(lff, filter_query, "tab download")

    if len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    def to_bytes(buffer):
        lff.collect(engine="streaming").write_excel(buffer, worksheet="DECP")

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.xlsx")


@callback(
    Output("tableau_datatable", "filter_query"),
    Output("tableau_datatable", "sort_by"),
    Output("tableau-hidden-columns", "data"),
    Output("tableau_url", "search"),
    Output("filter-cleanup-trigger", "data"),
    Input("tableau_url", "search"),
    State("tableau-filters", "data"),
    State("tableau-sort", "data"),
)
def restore_view_from_url(search, stored_filters, stored_sort):
    if not search and not stored_filters:
        return no_update, no_update, no_update, no_update, no_update

    params = urllib.parse.parse_qs(search.lstrip("?")) if search else {}
    logger.debug("params " + json.dumps(params, indent=2))

    filter_query = no_update
    sort_by = no_update
    hidden_columns = no_update
    trigger_cleanup = no_update

    if "filtres" in params:
        filter_query = params["filtres"][0]
        trigger_cleanup = str(uuid.uuid4())
    elif stored_filters:
        filter_query = stored_filters
        trigger_cleanup = str(uuid.uuid4())

    if "tris" in params:
        try:
            sort_by = json.loads(params["tris"][0])
        except json.JSONDecodeError:
            pass
    elif stored_sort:
        sort_by = stored_sort

    if "colonnes" in params:
        table_columns = params["colonnes"][0].split(",")
        verified_columns = [
            column for column in table_columns if column in schema.names()
        ]
        hidden_columns = invert_columns(verified_columns)

    return filter_query, sort_by, hidden_columns, "", trigger_cleanup


clientside_callback(
    ClientsideFunction(
        namespace="clientside",
        function_name="clean_filters",
    ),
    Output("filter-cleanup-trigger", "data", allow_duplicate=True),
    Input("filter-cleanup-trigger", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("share-url", "value"),
    Output("copy-container", "children"),
    Input("tableau_datatable", "filter_query"),
    Input("tableau_datatable", "sort_by"),
    Input("tableau_datatable", "hidden_columns"),
    State("tableau_url", "href"),
    prevent_initial_call=True,
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
        table_columns = invert_columns(hidden_columns)
        table_columns = ",".join(table_columns)
        params["colonnes"] = table_columns

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


@callback(
    Output("tableau_help", "is_open"),
    [Input("tableau_help_open", "n_clicks"), Input("tableau_help_close", "n_clicks")],
    [State("tableau_help", "is_open")],
)
def toggle_tableau_help(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open


@callback(
    Output("tableau-hidden-columns", "data", allow_duplicate=True),
    Input("tableau_column_list", "selected_rows"),
    prevent_initial_call=True,
)
def update_hidden_columns_from_checkboxes(selected_columns):
    if selected_columns:
        selected_columns = [columns[i] for i in selected_columns]
        hidden_columns = [col for col in columns if col not in selected_columns]
        return hidden_columns
    else:
        return []


@callback(
    Output("tableau_datatable", "hidden_columns"),
    Input(
        "tableau-hidden-columns",
        "data",
    ),
)
def store_hidden_columns(hidden_columns):
    return hidden_columns


@callback(
    Output("tableau_column_list", "selected_rows"),
    Input("tableau_datatable", "hidden_columns"),
    State("tableau_column_list", "selected_rows"),  # pour éviter la boucle infinie
)
def update_checkboxes_from_hidden_columns(hidden_cols, current_checkboxes):
    hidden_cols = hidden_cols or get_default_hidden_columns("tableau")

    # Show all columns that are NOT hidden
    visible_cols = [columns.index(col) for col in columns if col not in hidden_cols]
    return visible_cols


@callback(
    Output("tableau_columns", "is_open"),
    Input("tableau_columns_open", "n_clicks"),
    Input("tableau_columns_close", "n_clicks"),
    State("tableau_columns", "is_open"),
)
def toggle_tableau_columns(click_open, click_close, is_open):
    if click_open or click_close:
        return not is_open
    return is_open


@callback(Output("tableau-filters", "data"), Input("tableau_datatable", "filter_query"))
def sync_filters_to_local_storage(filter_query):
    return filter_query


@callback(Output("tableau-sort", "data"), Input("tableau_datatable", "sort_by"))
def sync_sort_to_local_storage(sort_by):
    return sort_by


@callback(
    Output("tableau_datatable", "filter_query", allow_duplicate=True),
    Output("tableau_datatable", "sort_by", allow_duplicate=True),
    Input("btn-tableau-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_view(n_clicks):
    return "", []


@callback(Input("tableau_url", "pathname"))
def cb_add_canonical_link(pathname):
    add_canonical_link(pathname)
