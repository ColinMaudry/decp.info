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


def orgs_departement(org_type: str, code: str | None, page: int) -> tuple[list, int]:
    """Organismes d'un département, triés par nombre de marchés décroissant.

    `code=None` cible les organismes sans département renseigné : la colonne
    vaut NULL, et `= ?` ne matche jamais NULL, d'où le IS NULL explicite.
    """
    table = _TABLES_ORGS[org_type]
    filtre = (
        f"{org_type}_departement_code IS NULL"
        if code is None
        else f"{org_type}_departement_code = ?"
    )
    params = [] if code is None else [code]
    cur = get_cursor()
    total = cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {filtre}", params
    ).fetchone()[0]
    rows = cur.execute(
        f"SELECT {org_type}_id, {org_type}_nom, nb_marches FROM {table} "
        f"WHERE {filtre} ORDER BY nb_marches DESC, {org_type}_id "
        "LIMIT ? OFFSET ?",
        [*params, pagination.PAGE_SIZE, pagination.offset(page)],
    ).fetchall()
    return rows, total
