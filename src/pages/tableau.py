import json
import os
from datetime import datetime

import dash_bootstrap_components as dbc
from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
    register_page,
)
from flask_login import current_user

from src.db import schema
from src.figures import ag_grid, make_column_picker
from src.pages._compte_shell import current_user_has_subscription
from src.saved_views import db as saved_views_db
from src.saved_views import ui as saved_views_ui
from src.utils import get_data_update_timestamp, logger
from src.utils.grid import fetch_grid_page, grid_column_defs
from src.utils.query_ast import (
    ast_from_dict,
    ast_to_dict,
    ast_to_filtermodel,
    filtermodel_to_ast,
)
from src.utils.seo import META_CONTENT
from src.utils.table import (
    COLUMNS,
    get_default_hidden_columns,
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
    title="Tableau des marchés publics | colibre",
    name=NAME,
    description="Consultez, filtrez et exportez les données essentielles de la commande publique sous forme de tableau.",
    image_url=META_CONTENT["image_url"],
    order=1,
)

DATATABLE = html.Div(
    className="marches_table",
    children=ag_grid(
        "tableau_grid", grid_column_defs(get_default_hidden_columns("tableau"))
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
    dcc.Store(id="tableau-hidden-columns", storage_type="local"),
    dcc.Store(id="tableau-table"),
    dcc.Store(id="tableau-total"),
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
                    "url": "https://colibre.fr",
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
        f"Ce tableau contient tous les marchés attribués en France. Il vous permet d'appliquer un filtre sur une ou plusieurs colonnes, et ainsi produire la liste de marchés dont vous avez besoin. Par défaut seules quelques colonnes sont affichées, mais vous pouvez en afficher jusqu'à {len(schema.names())} en cliquant sur le bouton **Colonnes**. Cet outil est assez puissant, je vous recommande de lire le mode d'emploi pour en tirer pleinement partie.",
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

            ##### Filtrer les colonnes

            Chaque colonne a son propre filtre : saisissez une valeur dans le champ situé juste sous son en-tête (le filtre « flottant »), ou cliquez sur l'icône entonnoir dans l'en-tête pour ouvrir le filtre complet.

            - Champs textuels : contient (par défaut), égal à, ne contient pas, commence par, se termine par...
            - Champs numériques (Durée en mois, Montant, nombre d'offres...) : égal à, supérieur à, inférieur à, entre (plage)...
            - Champs date (Date de notification...) : égal à, avant, après, entre (plage)...

            Dans le filtre complet (icône entonnoir), vous pouvez combiner deux conditions sur la même colonne avec **ET** ou **OU**.

            Vous pouvez filtrer plusieurs colonnes à la fois ; les filtres de colonnes différentes se cumulent toujours (ET).

            ##### Trier les données

            Cliquez sur l'en-tête d'une colonne pour la trier. Chaque clic change le tri dans cet ordre :

            1. tri croissant
            2. tri décroissant
            3. pas de tri

            Pour trier sur plusieurs colonnes à la fois, maintenez la touche `Maj` (Shift) enfoncée en cliquant sur les en-têtes suivants : la première colonne triée a la priorité, la suivante ne départage qu'au sein des groupes de valeurs identiques de la précédente, et ainsi de suite.

            ##### Défilement

            Le tableau charge les lignes au fur et à mesure que vous faites défiler la page, plutôt que par pages numérotées. Les en-têtes de colonnes (et leurs filtres) restent toujours visibles en haut du tableau pendant le défilement.

            ##### Afficher plus de colonnes

            Par défaut, un nombre réduit de colonnes est affiché pour ne pas surcharger la page. Mais vous avez le choix parmi {len(schema.names())} colonnes, ce serait dommage de vous limiter !

            Pour afficher plus de colonnes, cliquez sur le bouton **Colonnes** et cochez les colonnes à afficher.

            ##### Vues sauvegardées (abonnés)

            Une vue est un ensemble de filtres, de tris et de colonnes affichées que vous avez appliqués. Si vous êtes abonné, le bouton **Sauvegarder la vue** vous permet d'enregistrer la configuration actuelle sous un nom, et le menu **Mes vues** de la rappeler d'un clic plus tard.

            ##### Télécharger le résultat

            Vous pouvez télécharger le résultat de vos filtres et tris, pour les colonnes affichées, en cliquant sur **Télécharger (Excel)**.

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
    Output("tableau_grid", "getRowsResponse"),
    Output("tableau-total", "data"),
    Input("tableau_grid", "getRowsRequest"),
    prevent_initial_call=True,
)
def get_rows_tableau(request):
    if request is None:
        return no_update, no_update
    filter_model = request.get("filterModel") or None
    sort_model = request.get("sortModel") or None
    # AG Grid renvoie une nouvelle requête getRowsRequest pour chaque bloc de
    # défilement infini, avec le même filterModel tant que le filtre ne change
    # pas. Ne compter qu'une recherche par changement de filtre/tri (bloc 0),
    # pas une par bloc chargé au défilement.
    if filter_model and request.get("startRow", 0) == 0:
        track_search(json.dumps(filter_model), "tableau")
    rows, total = fetch_grid_page(
        filter_model,
        sort_model,
        request.get("startRow", 0),
        request.get("endRow", 100),
    )
    return {"rowData": rows, "rowCount": total}, total


@callback(
    Output("nb_rows", "children"),
    Output("btn-download-data", "disabled"),
    Output("download-hint", "children"),
    Input("tableau-total", "data"),
)
def update_meta(total):
    total = total or 0
    too_many = total > 65000
    hint = (
        " · Filtrez sous 65 000 lignes pour activer le téléchargement"
        if too_many
        else ""
    )
    return f"{total} lignes", too_many, hint


@callback(
    Output("download-data", "data"),
    Input("btn-download-data", "n_clicks"),
    State("tableau_grid", "filterModel"),
    State("tableau_grid", "columnState"),
    prevent_initial_call=True,
)
def download_data(n_clicks, filter_model, column_state):
    from src.utils.grid import export_dataframe

    sort_model = [
        {"colId": c["colId"], "sort": c["sort"]}
        for c in (column_state or [])
        if c.get("sort")
    ]
    hidden_columns = [c["colId"] for c in (column_state or []) if c.get("hide")]
    if filter_model:
        track_search(json.dumps(filter_model), "tab download")
    df = export_dataframe(filter_model, sort_model, hidden_columns)

    def to_bytes(buffer):
        write_styled_excel(df, buffer)

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.xlsx")


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
    Output("tableau_grid", "columnDefs"),
    Input("tableau-hidden-columns", "data"),
)
def apply_hidden_columns(hidden_columns):
    if hidden_columns is None:
        hidden_columns = get_default_hidden_columns("tableau")
    return grid_column_defs(hidden_columns)


@callback(
    Output("tableau_column_list", "selected_rows"),
    Input("tableau-hidden-columns", "data"),
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
    Output("tableau_grid", "filterModel", allow_duplicate=True),
    Input("btn-tableau-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_view(n_clicks):
    return {}


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
    State("tableau_grid", "filterModel"),
    State("tableau_grid", "columnState"),
    prevent_initial_call=True,
)
def save_view(_n, name, filter_model, column_state):
    has_sub = current_user_has_subscription()
    clean_name, error = saved_views_ui.prepare_view_to_save(has_sub, name)
    if error:
        return True, html.Span(error, style={"color": "red"}), no_update
    # On stocke l'AST canonique (indépendant de l'UI), pas le filterModel brut
    # d'AG Grid : cf. spec de conception, "l'AST (JSON) + columnState,
    # indépendant de l'UI".
    ast = filtermodel_to_ast(filter_model, schema)
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": column_state or []})
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
    Output("tableau_grid", "filterModel"),
    Output("tableau_grid", "columnState"),
    Output("tableau-hidden-columns", "data", allow_duplicate=True),
    Input({"type": "saved-view-item", "index": ALL}, "n_clicks"),
    State({"type": "saved-view-item", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def apply_saved_view(n_clicks, ids):
    triggered = ctx.triggered_id
    if not triggered or not any(n_clicks):
        return no_update, no_update, no_update
    row = saved_views_db.get(triggered["index"], current_user.id)
    if not row:
        return no_update, no_update, no_update
    try:
        view = json.loads(row["query"])
        # L'AST canonique est stocké (pas le filterModel brut d'AG Grid) :
        # cf. save_view. `ast_from_dict(None)` -> None et
        # `ast_to_filtermodel(None, schema)` -> {} si la vue est d'un ancien
        # format (sans clé "ast") : dégradation propre, la vue se rappelle
        # sans filtre plutôt que de planter.
        ast = ast_from_dict(view.get("ast"))
        filter_model = ast_to_filtermodel(ast, schema)
        column_state = view.get("columnState") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        # Vue enregistrée avant la migration vers AG Grid (Task 10) : row["query"]
        # est encore une query string (ex. "filtres=a&tris=b"), pas du JSON. On
        # échoue proprement plutôt que de planter le callback ; pas de
        # migration automatique de l'ancien format.
        logger.warning(
            "Vue sauvegardée au format pré-migration, impossible de l'appliquer : "
            f"id={row['id']!r} name={row['name']!r}"
        )
        return no_update, no_update, no_update
    # tableau-hidden-columns pilote les cases à cocher du sélecteur de colonnes
    # (update_checkboxes_from_hidden_columns) et la régénération des
    # columnDefs (apply_hidden_columns) ; sans cette sortie, ce store restait
    # désynchronisé du columnState rappelé (revue finale #41). Même extraction
    # que download_data.
    hidden_columns = [c["colId"] for c in column_state if c.get("hide")]
    return filter_model, column_state, hidden_columns


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
