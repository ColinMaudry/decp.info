"""Requêtes DuckDB paginées des pages SEO.

Toutes les requêtes portent un ORDER BY explicite : sans ordre déterministe,
LIMIT/OFFSET peut afficher une même ligne sur deux pages et en omettre une
autre.
"""

from src.db import get_cursor
from src.seo import pagination

_TABLES_MARCHES = {
    "acheteur": "acheteurs_marches",
    "titulaire": "titulaires_marches",
}
_TABLES_ORGS = {
    "acheteur": "acheteurs_departement",
    "titulaire": "titulaires_departement",
}


def marches_org(org_type: str, org_id: str, page: int) -> tuple[list, int]:
    """Marchés d'un organisme pour la page demandée, et total toutes pages."""
    table = _TABLES_MARCHES[org_type]
    cur = get_cursor()
    total = cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {org_type}_id = ?", [org_id]
    ).fetchone()[0]
    rows = cur.execute(
        f"SELECT uid, objet FROM {table} WHERE {org_type}_id = ? "
        "ORDER BY uid LIMIT ? OFFSET ?",
        [org_id, pagination.PAGE_SIZE, pagination.offset(page)],
    ).fetchall()
    return rows, total


def org_nom(org_type: str, org_id: str) -> str | None:
    """Raison sociale d'un organisme, ou None s'il est inconnu."""
    table = _TABLES_ORGS[org_type]
    row = (
        get_cursor()
        .execute(
            f"SELECT {org_type}_nom FROM {table} WHERE {org_type}_id = ? LIMIT 1",
            [org_id],
        )
        .fetchone()
    )
    return row[0] if row else None
