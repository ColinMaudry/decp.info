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
from flask_login import current_user

from src.db import query_marches, schema
from src.figures import DataTable, make_column_picker
from src.pages._compte_shell import current_user_has_subscription
from src.saved_views import db as saved_views_db
from src.saved_views import ui as saved_views_ui
from src.utils import get_data_update_timestamp, logger
from src.utils.seo import META_CONTENT
from src.utils.table import (
    COLUMNS,
    build_view_query,
    filter_table_data,
    get_default_hidden_columns,
    invert_columns,
    prepare_table_data,
    sort_table_data,
    write_styled_excel,
)
from src.utils.tracking import track_search

update_date_timestamp = get_data_update_timestamp(
    os.getenv("DATA_FILE_PARQUET_PATH", ""),
    os.getenv("DUCKDB_PATH", "./decp.duckdb"),
)
if update_date_timestamp is not None:
    update_date = datetime.fromtimestamp(update_date_timestamp).strftime("%d/%m/%Y")
    update_date_iso = datetime.fromtimestamp(update_date_timestamp).isoformat()
else:
    update_date = "date inconnue"
    update_date_iso = ""


NAME = "Tableau"
register_page(
    __name__,
    path="/tableau",
    title="Tableau des marchés publics | decp.info",
    name=NAME,
    description="Consultez, filtrez et exportez les données essentielles de la commande publique sous forme de tableau.",
    image_url=META_CONTENT["image_url"],
    order=1,
)

DATATABLE = html.Div(
    className="marches_table",
    children=DataTable(
        dtid="tableau_datatable",
        persisted_props=["filter_query", "sort_by"],
        persistence_type="local",
        persistence=True,
        page_size=20,
        page_action="custom",
        filter_action="custom",
        sort_action="custom",
        hidden_columns=[],
        columns=[{"id": col, "name": col} for col in schema.names()],
    ),
)


def _help_button_legend():
    """Légende en tête du mode d'emploi : chaque bouton de la barre d'outils,
    reproduit à l'identique (mais inerte), en face de sa fonction."""
    rows = [
        (
            dbc.Button("Colonnes", color="secondary", size="sm"),
            "Choisir les colonnes affichées.",
        ),
        (
            dbc.Button("Sauvegarder la vue", color="secondary", size="sm"),
            "Enregistrer les filtres, tris et colonnes actuels sous un nom (abonnés).",
        ),
        (
            dbc.Button("Mes vues ▾", color="secondary", size="sm"),
            "Rouvrir une vue que vous avez enregistrée (abonnés).",
        ),
        (
            dbc.Button("Partager la vue", color="secondary", size="sm"),
            "Copier l'adresse de la vue actuelle pour la partager ou la conserver.",
        ),
        (
            dbc.Button("Télécharger (Excel)", color="secondary", size="sm"),
            "Télécharger les données filtrées et triées au format Excel.",
        ),
        (
            dbc.Button("Réinitialiser", color="danger", outline=True, size="sm"),
            "Supprimer tous les filtres et tris.",
        ),
        (
            dbc.Button("Mode d'emploi", color="secondary", outline=True, size="sm"),
            "Ouvrir cette aide.",
        ),
    ]
    return html.Div(
        className="help-legend",
        children=[
            html.P("Les boutons de la barre d'outils", className="fw-bold mb-2"),
            html.Table(
                className="help-legend-table",
                children=html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(btn, className="help-legend-btn"),
                                html.Td(desc, className="help-legend-desc"),
                            ]
                        )
                        for btn, desc in rows
                    ]
                ),
            ),
        ],
    )


layout = [
    dcc.Location(id="tableau_url", refresh=False),
    dcc.Store(id="filter-cleanup-trigger-tableau"),
    dcc.Store(id="tableau-hidden-columns", storage_type="local"),
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
                    **(
                        {"temporalCoverage": f"2018-01-01/{update_date_iso[:10]}"}
                        if update_date_iso
                        else {}
                    ),
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
        f"Ce tableau contient tous les marchés attribués en France. Il vous permet d'appliquer un filtre sur une ou plusieurs colonnes, et ainsi produire la liste de marchés dont vous avez besoin (exemples : [marchés de voirie < 40 k€ en 2025](/tableau?filtres=%7Bacheteur_id%7D+icontains+24350013900189+%26%26+%7BdateNotification%7D+icontains+2025%2A+%26%26+%7Bmontant%7D+i%3C+40000+%26%26+%7Bobjet%7D+icontains+voirie&colonnes=uid%2Cacheteur_id%2Cacheteur_nom%2Ctitulaire_id%2Ctitulaire_nom%2Cobjet%2Cmontant%2CdureeMois%2CdateNotification%2Cacheteur_departement_code%2CsourceDataset), [marchés > 500 k€ avec clause sociale attribués à des PME à plus de 100 km dans le Var](/tableau?filtres=%7Btitulaire_categorie%7D+icontains+PME+%26%26+%7Btitulaire_distance%7D+i%3E+100+%26%26+%7Bmontant%7D+i%3E+500000+%26%26+%7Bacheteur_departement_code%7D+icontains+83+%26%26+%7BconsiderationsSociales%7D+icontains+clause&colonnes=uid%2Cacheteur_id%2Cacheteur_nom%2Ctitulaire_id%2Ctitulaire_nom%2Cobjet%2Cmontant%2CdureeMois%2CdateNotification%2CconsiderationsSociales%2Ctitulaire_distance%2Cacheteur_departement_code%2Ctitulaire_categorie%2CsourceDataset)). Par défaut seules quelques colonnes sont affichées, mais vous pouvez en afficher jusqu'à {len(schema.names())} en cliquant sur le bouton **Colonnes**. Cet outil est assez puissant, je vous recommande de lire le mode d'emploi pour en tirer pleinement partie.",
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
                    dbc.Button(
                        "⍰ Mode d'emploi",
                        id="tableau_help_open",
                        color="secondary",
                        outline=True,
                        size="sm",
                    ),
                    dbc.Modal(
                        [
                            dbc.ModalHeader(dbc.ModalTitle("Mode d'emploi")),
                            dbc.ModalBody(
                                [
                                    _help_button_legend(),
                                    html.Hr(),
                                    dcc.Markdown(
                                        dangerously_allow_html=True,
                                        children=f"""
            ##### Définition des colonnes

            Pour voir la définition d'une colonne, passez votre souris sur son en-tête.

            ##### Vos réglages sont persistents

            Les filtres, les tris et le choix de colonnes sont automatiquement enregistrés dans votre navigateur et persistent même si vous changez de page ou si vous fermez votre navigateur. À votre retour, vous retrouverez cette page comme vous l'avez laissée.

            ##### Appliquer des filtres

            Vous pouvez appliquer un filtre pour chaque colonne en entrant du texte sous le nom de la colonne, puis en tapant sur `Entrée`.

            - Champs textuels : la recherche retourne les valeurs qui contiennent le texte recherché, n'est sensible ni à la casse (majuscules/minuscules), ni à l'accentuation.
                - `rennes` => le texte contient "rennes"
                - `metro* *pole` => le texte contient un mot qui commence par "metro" et un mot qui finit par "pole"
                - `metropole rennes` => le texte contient les mots "metropole" et "rennes", n'importe où dans le texte
                - `métropole+rennes` => le texte contient "metropole rennes" ou "métropole rennes", collé et dans cet ordre
                - `metropole+rennes travaux distri*` => le texte contient "metropole rennes", "travaux" et un mot qui commence par "distri"
                - Les guillemets simples (apostrophe du 4) doivent être prédédées d'une barre oblique (AltGr + 8). Exemple : `services d\\\'assurances`
            - Champs numériques (Durée en mois, Montant, ...) : vous pouvez...
                - soit taper un nombre pour trouver les valeurs strictement égales. Exemple : `12` ne retourne que des 12
                - soit le précéder de **>** ou **<** pour filtrer les valeurs supérieures ou inférieures. Exemple pour les offres reçues : `> 4` retourne les marchés ayant reçu plus de 4 offres.
            - Champs date (Date de notification, ...) :
                - `< 2024-01-31` pour "avant le 31 janvier 2024"
                - `2024` pour "en 2024", `> 2022` pour "à partir de 2022"

            Vous pouvez filtrer plusieurs colonnes à la fois.

            ##### Trier les données

            Pour trier une colonne, utilisez les flèches grises à côté des noms de colonnes. Chaque clic change le tri dans cet ordre :

            1. tri croissant
            2. tri décroissant
            3. pas de tri

            Les tris sont appliqués dans l'ordre : la première colonne que vous triez a la priorité sur la seconde, qui triera uniquement au sein des groupes de valeurs de la première colonne.

            ##### Afficher plus de colonnes

            Par défaut, un nombre réduit de colonnes est affiché pour ne pas surcharger la page. Mais vous avez le choix parmi {len(schema.names())} colonnes, ce serait dommage de vous limiter !

            Pour afficher plus de colonnes, cliquez sur le bouton **Choisir les colonnes** et cochez les colonnes pour les afficher.

            ##### Partager une vue

            Une vue est un ensemble de filtres, de tris et de choix de colonnes que vous avez appliqués. Cliquez sur **Partager** pour copier une adresse Web qui reproduit la vue courante à l'identique : en la collant dans la barre d'adresse d'un navigateur, vous ouvrez la vue Tableau avec les mêmes paramètres.

            Pratique pour partager une vue avec un·e collègue, sur les réseaux sociaux, ou la sauvegarder pour plus tard.

            ##### Télécharger le résultat

            Vous pouvez télécharger le résultat de vos filtres et tris, pour les colonnes affichées, en cliquant sur **Télécharger au format Excel**.

            ##### Liens

            Les liens dans les colonnes Identifiant unique, Acheteur et Titulaire vous permettent de consulter une vue qui leur est dédiée
            (informations, marchés attribués/remportés, etc.)

            """,
                                    ),
                                ],
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
                        "Colonnes",
                        id="tableau_columns_open",
                        color="secondary",
                        size="sm",
                        className="column_list",
                        title="Choisir les colonnes à afficher et masquer",
                    ),
                    html.Div(
                        id="saved-views-bar",
                        style={"display": "none"},
                        className="d-inline-flex align-items-center gap-2",
                        children=[
                            dbc.Button(
                                "Sauvegarder la vue",
                                id="btn-save-view",
                                color="secondary",
                                size="sm",
                                title="Enregistrer les filtres, tris et colonnes actuels sous un nom",
                            ),
                            dbc.DropdownMenu(
                                id="saved-views-menu",
                                label="Mes vues",
                                color="secondary",
                                size="sm",
                                children=[],
                                className="d-inline-block",
                            ),
                        ],
                    ),
                    dcc.Store(id="saved-views-refresh"),
                    dbc.Modal(
                        id="save-view-modal",
                        is_open=False,
                        children=[
                            dbc.ModalHeader(dbc.ModalTitle("Sauvegarder la vue")),
                            dbc.ModalBody(
                                [
                                    dbc.Label("Nom de la vue"),
                                    dcc.Input(
                                        id="save-view-name",
                                        type="text",
                                        className="form-control",
                                    ),
                                    html.Hr(className="my-3"),
                                    dbc.Label("Ou remplacer une vue existante"),
                                    dbc.Select(
                                        id="overwrite-view-select",
                                        options=[],
                                        placeholder="Sélectionner une vue…",
                                    ),
                                    html.Div(id="save-view-feedback", className="mt-2"),
                                ]
                            ),
                            dbc.ModalFooter(
                                dbc.Button(
                                    "Enregistrer",
                                    id="btn-save-view-confirm",
                                    color="primary",
                                )
                            ),
                        ],
                    ),
                    html.Div(id="copy-container"),
                    dcc.Input(id="share-url", readOnly=True, style={"display": "none"}),
                    dbc.Button(
                        "Télécharger (Excel)",
                        id="btn-download-data",
                        color="secondary",
                        size="sm",
                        disabled=True,
                    ),
                    dcc.Download(id="download-data"),
                    dcc.Store(id="filtered_data", storage_type="memory"),
                    dbc.Button(
                        "Réinitialiser",
                        id="btn-tableau-reset",
                        color="danger",
                        outline=True,
                        size="sm",
                        title="Supprime tous les filtres et les tris. Autrement ils sont conservés même si vous fermez la page.",
                    ),
                ],
                className="table-toolbar",
            ),
            html.Div(
                className="table-meta",
                children=[
                    html.Span(id="nb_rows"),
                    html.Span(" · Données mises à jour le " + str(update_date)),
                    html.Span(id="download-hint"),
                ],
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
            DATATABLE,
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
    Output("filter-cleanup-trigger-tableau", "data", allow_duplicate=True),
    Output("download-hint", "children"),
    Input("tableau_url", "href"),
    Input("tableau_datatable", "page_current"),
    Input("tableau_datatable", "page_size"),
    Input("tableau_datatable", "filter_query"),
    Input("tableau_datatable", "sort_by"),
    State("tableau_datatable", "data_timestamp"),
    prevent_initial_call=True,
)
def update_table(href, page_current, page_size, filter_query, sort_by, data_timestamp):
    result = list(
        prepare_table_data(
            None,
            data_timestamp,
            filter_query,
            page_current,
            page_size,
            sort_by,
            "tableau",
        )
    )
    # Libellé court et constant ; la raison d'un éventuel blocage est affichée
    # en clair dans la ligne d'infos (fiable cross-browser, contrairement à une
    # infobulle sur bouton désactivé). index 5 = disabled, 6 = children, 7 = title.
    result[6] = "Télécharger (Excel)"
    download_blocked_too_many = result[5] and result[7]
    download_hint = (
        " · Filtrez sous 65 000 lignes pour activer le téléchargement"
        if download_blocked_too_many
        else ""
    )
    result.append(download_hint)
    return tuple(result)


@callback(
    Output("download-data", "data"),
    Input("btn-download-data", "n_clicks"),
    State("tableau_datatable", "filter_query"),
    State("tableau_datatable", "sort_by"),
    State("tableau_datatable", "hidden_columns"),
    prevent_initial_call=True,
)
def download_data(n_clicks, filter_query, sort_by, hidden_columns: list | None = None):
    lff: pl.LazyFrame = query_marches().lazy()

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        track_search(filter_query, "tab download")
        lff = filter_table_data(lff, filter_query)

    if sort_by and len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    def to_bytes(buffer):
        write_styled_excel(lff.collect(engine="streaming"), buffer)

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.xlsx")


@callback(
    Output("tableau_datatable", "filter_query"),
    Output("tableau_datatable", "sort_by"),
    Output("tableau-hidden-columns", "data"),
    Output("tableau_url", "search"),
    Output("filter-cleanup-trigger-tableau", "data"),
    Input("tableau_url", "search"),
    State("tableau_datatable", "filter_query"),
    State("tableau_datatable", "sort_by"),
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


# Pour nettoyer les icontains et i< des filtres
# voir aussi src/assets/dash_clientside.js
clientside_callback(
    ClientsideFunction(
        namespace="clientside",
        function_name="clean_filters",
    ),
    Output("filter-cleanup-trigger-tableau", "data", allow_duplicate=True),
    Input("filter-cleanup-trigger-tableau", "data"),
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

    query_string = build_view_query(filter_query, sort_by, hidden_columns)
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
        children=[
            dbc.Button(
                "Partager la vue",
                color="secondary",
                size="sm",
                title="Copier l'adresse de cette vue (filtres, tris, choix de colonnes) pour la partager.",
            )
        ],
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
        selected_columns = [COLUMNS[i] for i in selected_columns]
        hidden_columns = [col for col in COLUMNS if col not in selected_columns]
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
    if hidden_columns is None:
        hidden_columns = get_default_hidden_columns("tableau")
    return hidden_columns


@callback(
    Output("tableau_column_list", "selected_rows"),
    Input("tableau_datatable", "hidden_columns"),
    State("tableau_column_list", "selected_rows"),  # pour éviter la boucle infinie
)
def update_checkboxes_from_hidden_columns(hidden_cols, current_checkboxes):
    hidden_cols = hidden_cols or get_default_hidden_columns("tableau")

    # Show all columns that are NOT hidden
    visible_cols = [COLUMNS.index(col) for col in COLUMNS if col not in hidden_cols]
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


@callback(
    Output("tableau_datatable", "filter_query", allow_duplicate=True),
    Output("tableau_datatable", "sort_by", allow_duplicate=True),
    Input("btn-tableau-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_view(n_clicks):
    return "", []


@callback(
    Output("saved-views-bar", "style"),
    Input("tableau_url", "pathname"),
)
def toggle_saved_views_bar(_pathname):
    return saved_views_ui.bar_style(current_user_has_subscription())


@callback(
    Output("save-view-modal", "is_open"),
    Input("btn-save-view", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_save_view_modal(_open):
    return True


@callback(
    Output("save-view-modal", "is_open", allow_duplicate=True),
    Output("save-view-feedback", "children"),
    Output("saved-views-refresh", "data"),
    Input("btn-save-view-confirm", "n_clicks"),
    State("save-view-name", "value"),
    State("tableau_datatable", "filter_query"),
    State("tableau_datatable", "sort_by"),
    State("tableau_datatable", "hidden_columns"),
    prevent_initial_call=True,
)
def save_view(_n, name, filter_query, sort_by, hidden_columns):
    has_sub = current_user_has_subscription()
    clean_name, error = saved_views_ui.prepare_view_to_save(has_sub, name)
    if error:
        return True, html.Span(error, style={"color": "red"}), no_update
    query = build_view_query(filter_query, sort_by, hidden_columns)
    saved_views_db.upsert(current_user.id, "tableau", clean_name, query)
    return (
        False,
        html.Span(f"Vue « {clean_name} » enregistrée.", style={"color": "green"}),
        clean_name,
    )


@callback(
    Output("saved-views-menu", "children"),
    Input("tableau_url", "pathname"),
    Input("saved-views-refresh", "data"),
)
def populate_saved_views_menu(_pathname, _refresh):
    if not current_user_has_subscription():
        return []
    views = saved_views_db.list_views(current_user.id, "tableau")
    return saved_views_ui.saved_views_items(views)


@callback(
    Output("overwrite-view-select", "options"),
    Input("save-view-modal", "is_open"),
)
def populate_overwrite_select(is_open):
    if not is_open or not current_user_has_subscription():
        return []
    views = saved_views_db.list_views(current_user.id, "tableau")
    return [{"label": v["name"], "value": v["name"]} for v in views]


clientside_callback(
    "function(val) { return val != null ? val : window.dash_clientside.no_update; }",
    Output("save-view-name", "value"),
    Input("overwrite-view-select", "value"),
    prevent_initial_call=True,
)
