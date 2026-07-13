"""Logique de grille AG Grid scopée à une entité (acheteur/titulaire).

Factorise ce qui est commun aux pages acheteur.py et titulaire.py :
- scope SQL (WHERE acheteur_id/titulaire_id + année),
- datasource server-side (réutilise fetch_grid_page du Lot 1),
- export Excel filtré (réutilise export_dataframe),
- columnDefs + réapplication de la disposition persistée,
- fabrique de grille à id pattern-matching (persistance filterModel par fiche).

Les callbacks Dash sont enregistrés par register_entity_grid_callbacks()
(cf. module séparé de wiring) ; ici, seules des fonctions pures testables.
"""

from dash import no_update

from src.figures import (
    AG_GRID_LOCALE_FR,  # noqa: F401  (réexport pratique)
    ag_grid,
)
from src.utils.grid import (
    apply_persisted_layout,
    export_dataframe,
    fetch_grid_page,
    grid_column_defs,
)

_TOUTES = "Toutes les années"


def grid_type(org_type: str) -> str:
    """Valeur de la clé `type` de l'id pattern-matching de la grille."""
    return f"{org_type}-grid"


def entity_scope(org_type: str, entity_id: str, year) -> tuple[str, list]:
    """WHERE SQL + params liés scopant les requêtes à cette entité (+ année).

    Reproduit _acheteur_scope/_titulaire_scope des pages, unifié par org_type.
    """
    if org_type == "titulaire":
        where_sql = "titulaire_id = ? AND titulaire_typeIdentifiant = 'SIRET'"
    else:
        where_sql = "acheteur_id = ?"
    params: list = [entity_id]
    if year and year != _TOUTES:
        where_sql += ' AND YEAR("dateNotification") = ?'
        params.append(int(year))
    return where_sql, params


def _sort_model_from_column_state(column_state) -> list:
    """Extrait le sortModel AG Grid d'un columnState (comme tableau.download_data)."""
    return [
        {"colId": c["colId"], "sort": c["sort"]}
        for c in (column_state or [])
        if c.get("sort")
    ]


def entity_grid_column_defs(hidden_columns, column_state) -> list[dict]:
    """columnDefs du schéma DECP + disposition (largeur/ordre) persistée."""
    defs = grid_column_defs(hidden_columns)
    return apply_persisted_layout(defs, column_state)


def fetch_entity_page(org_type, entity_id, year, request) -> tuple:
    """Datasource server-side scopé pour la grille entité.

    Renvoie ({"rowData": ..., "rowCount": total}, total, total_unique).
    """
    if request is None:
        return no_update, no_update, no_update
    base_where_sql, base_params = entity_scope(org_type, entity_id, year)
    rows, total, total_unique = fetch_grid_page(
        request.get("filterModel") or None,
        request.get("sortModel") or None,
        request.get("startRow", 0),
        request.get("endRow", 100),
        base_where_sql=base_where_sql,
        base_params=tuple(base_params),
    )
    return {"rowData": rows, "rowCount": total}, total, total_unique


def export_entity_dataframe(org_type, entity_id, year, filter_model, column_state):
    """DataFrame filtré/trié (état courant de la grille) pour l'export Excel."""
    base_where_sql, base_params = entity_scope(org_type, entity_id, year)
    sort_model = _sort_model_from_column_state(column_state)
    hidden_columns = [c["colId"] for c in (column_state or []) if c.get("hide")]
    return export_dataframe(
        filter_model,
        sort_model,
        hidden_columns,
        base_where_sql=base_where_sql,
        base_params=tuple(base_params),
    )


def clear_sort(column_state) -> list[dict]:
    """columnState avec le tri effacé (sort/sortIndex à None), largeur/ordre/
    épinglage préservés. Approche #47-safe de tableau.reset_view."""
    return [{**col, "sort": None, "sortIndex": None} for col in (column_state or [])]


def build_entity_grid(org_type, entity_id, year, hidden_columns, column_state):
    """Grille AG Grid à id pattern-matching, scopée à (entité, année).

    L'id inclut entity_id + year → une entrée localStorage de filterModel par
    fiche/année (persistance native scopée). columnState n'est PAS persisté
    nativement (géré par un store global partagé) : persisted_props=["filterModel"].
    """
    grid_id = {
        "type": grid_type(org_type),
        "entity_id": entity_id,
        "year": year or _TOUTES,
    }
    defs = entity_grid_column_defs(hidden_columns, column_state)
    return ag_grid(grid_id, defs, persisted_props=["filterModel"])
