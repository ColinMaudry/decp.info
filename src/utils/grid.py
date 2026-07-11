"""Datasource server-side pour AG Grid (infinite row model)."""

import polars as pl

from src.db import count_marches, count_unique_marches, query_marches, schema
from src.figures import DATA_SCHEMA
from src.utils.cache import cache
from src.utils.query_ast import ast_to_sql, filtermodel_to_ast, sort_model_to_sql
from src.utils.table import postprocess_page


@cache.memoize()
def _cached_count(where_sql: str, params: tuple) -> int:
    """Cache le COUNT(*) sur (where_sql, params).

    AG Grid envoie une requête par bloc de défilement infini ; pour un même
    filtre, tous les blocs partagent le même (where_sql, params) et donc le
    même total — inutile de recompter un COUNT(*) sur ~1,5M lignes à chaque
    bloc chargé (cf. `src.utils.table._fetch_page_sql`, même schéma).
    """
    return count_marches(where_sql, params)


@cache.memoize()
def _cached_unique_count(where_sql: str, params: tuple) -> int:
    """Cache le COUNT(DISTINCT uid) sur (where_sql, params), même raison que
    `_cached_count`."""
    return count_unique_marches(where_sql, params)


def fetch_grid_page(
    filter_model,
    sort_model,
    start_row: int,
    end_row: int,
    base_where_sql: str = "TRUE",
    base_params: tuple = (),
) -> tuple[list[dict], int, int]:
    """Renvoie (row_data, total_count, total_unique_count) pour un bloc [start_row, end_row)."""
    ast = filtermodel_to_ast(filter_model, schema)
    filter_sql, filter_params = ast_to_sql(ast, schema)
    where_sql = f"({base_where_sql}) AND ({filter_sql})"
    params = [*base_params, *filter_params]

    order_by = sort_model_to_sql(sort_model, schema) or None
    total = _cached_count(where_sql, tuple(params))
    total_unique = _cached_unique_count(where_sql, tuple(params))

    limit = max(0, end_row - start_row)
    page = query_marches(
        where_sql=where_sql,
        params=params,
        order_by=order_by,
        limit=limit,
        offset=start_row,
    )
    page = postprocess_page(page)
    return page.to_dicts(), total, total_unique


def export_dataframe(filter_model, sort_model, hidden_columns) -> pl.DataFrame:
    """Renvoie les lignes filtrées/triées pour l'export Excel.

    Colonnes masquées exclues, valeurs brutes (non post-traitées HTML).
    """
    ast = filtermodel_to_ast(filter_model, schema)
    filter_sql, params = ast_to_sql(ast, schema)
    order_by = sort_model_to_sql(sort_model, schema) or None
    visible = [c for c in schema.names() if c not in set(hidden_columns or [])]
    return query_marches(
        where_sql=filter_sql,
        params=params,
        columns=visible,
        order_by=order_by,
    )


_LINK_COLUMNS = {
    "marche",
    "uid",
    "acheteur_id",
    "acheteur_nom",
    "titulaire_id",
    "titulaire_nom",
    "sourceDataset",
}

# Colonnes oui/non (cf. `booleans_to_strings` dans src.db) : valeur très
# courte, pas besoin de place.
_BOOLEAN_LIKE_COLUMNS = {
    "attributionAvance",
    "marcheInnovant",
    "sousTraitanceDeclaree",
    "considerationsSociales",
    "considerationsEnvironnementales",
}

# Codes/identifiants qui ne suivent pas le pattern de suffixe `_id`/`_code`
# (ex. codeCPV, idAccordCadre) mais restent des valeurs courtes.
_SHORT_CODE_COLUMNS = {
    "uid",
    "id",
    "codeCPV",
    "idAccordCadre",
    "lieuExecution_typeCode",
    "sourceFile",
}

# Colonnes "nom" qui ne suivent pas le suffixe `_nom` (ex. sourceDataset).
_WIDE_LABEL_COLUMNS = {"sourceDataset"}


def _filter_for(col_type) -> str:
    if col_type.is_numeric():
        return "agNumberColumnFilter"
    if col_type == pl.Date:
        return "agDateColumnFilter"
    return "agTextColumnFilter"


def _column_width(col: str, col_type) -> dict:
    """Largeur par défaut selon la nature de la colonne.

    `columnSize="responsiveSizeToFit"` (cf. ag_grid()) étire les colonnes
    proportionnellement à cette largeur pour remplir l'espace disponible :
    sans ça, les codes/booléens s'étirent autant que les noms/libellés.
    """
    if col == "montant":
        return {"width": 150, "maxWidth": 200}
    if col_type == pl.Date:
        return {"width": 140, "maxWidth": 160}
    if col_type.is_numeric():
        return {"width": 120, "maxWidth": 150}
    if col in _BOOLEAN_LIKE_COLUMNS:
        return {"width": 110, "maxWidth": 140}
    if col in _SHORT_CODE_COLUMNS or col.endswith(("_id", "_code")):
        return {"width": 130, "maxWidth": 170}
    if col in _WIDE_LABEL_COLUMNS or col.endswith("_nom"):
        return {"width": 200}
    return {"width": 170}


def grid_column_defs(hidden_columns=None):
    """columnDefs dérivés du schéma DuckDB.

    'marche' (colonne loupe ajoutée par postprocess_page) est placée en tête.
    """
    hidden = set(hidden_columns or [])
    defs = [
        {
            "field": "marche",
            "headerName": "",
            "cellRenderer": "markdown",
            "filter": False,
            "sortable": False,
            "maxWidth": 60,
            "pinned": "left",
        }
    ]
    for col in schema.names():
        meta = DATA_SCHEMA.get(col, {})
        col_type = schema[col]
        col_def = {
            "field": col,
            "headerName": meta.get("title", col),
            "filter": _filter_for(col_type),
            "floatingFilter": True,
            "sortable": True,
            "hide": col in hidden,
        }
        if meta.get("description"):
            col_def["headerTooltip"] = (
                f"{meta.get('title', col)} ({col}) — {meta['description']}"
            )
        if col in _LINK_COLUMNS:
            col_def["cellRenderer"] = "markdown"
        if col != "objet":
            col_def.update(_column_width(col, col_type))
        if col == "objet":
            # autoHeight n'est pas supporté avec rowModelType="infinite" (la
            # grille doit pouvoir calculer la position des lignes non
            # chargées, donc une hauteur de ligne fixe) : cf. ag_grid(),
            # rowHeight fixe côté dashGridOptions plutôt qu'autoHeight ici.
            col_def["wrapText"] = True
            col_def["minWidth"] = 360
            # Le texte tronqué par la hauteur de ligne fixe reste consultable
            # en entier via l'infobulle native AG Grid au survol.
            col_def["tooltipField"] = "objet"
        defs.append(col_def)
    return defs
