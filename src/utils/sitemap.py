"""Génération du sitemap.xml.

Le sitemap est servi comme un **index** (`/sitemap.xml`) pointant vers des
sous-sitemaps paginés, car Google limite chaque fichier à 50 000 URLs / 50 Mo.
Les identifiants d'acheteurs (~30k) et de titulaires (~200k) sont lus depuis
DuckDB et mis en cache : la génération est trop coûteuse pour être refaite à
chaque requête de crawler.
"""

from xml.sax.saxutils import escape

from src.db import get_cursor
from src.utils.cache import cache

BASE_URL = "https://colibre.fr"
URLS_PER_SITEMAP = 50_000

# Pages statiques indexables.
STATIC_PAGES = [
    "/",
    "/observatoire",
    "/tableau",
    "/a-propos",
    "/etapes",
]

# (segment d'URL, table DuckDB, colonne identifiant)
ORG_SITEMAPS = {
    "acheteurs": ("acheteurs_departement", "acheteur_id"),
    "titulaires": ("titulaires_departement", "titulaire_id"),
}


@cache.memoize(timeout=3600 * 24)
def _org_ids(table: str, id_col: str) -> list[str]:
    """Identifiants distincts non nuls d'une table d'organisations, triés."""
    rows = (
        get_cursor()
        .execute(
            f"SELECT DISTINCT {id_col} FROM {table} "
            f"WHERE {id_col} IS NOT NULL ORDER BY {id_col}"
        )
        .fetchall()
    )
    return [str(r[0]) for r in rows]


def _chunk_count(n: int) -> int:
    """Nombre de sous-sitemaps nécessaires pour n URLs (au moins 1)."""
    return max(1, -(-n // URLS_PER_SITEMAP))


def _urlset(locs: list[str]) -> str:
    body = "".join(f"  <url>\n    <loc>{escape(loc)}</loc>\n  </url>\n" for loc in locs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}"
        "</urlset>"
    )


def build_index() -> str:
    """Index listant tous les sous-sitemaps."""
    children = ["/sitemap-pages.xml"]
    for segment, (table, id_col) in ORG_SITEMAPS.items():
        pages = _chunk_count(len(_org_ids(table, id_col)))
        children += [f"/sitemap-{segment}-{i}.xml" for i in range(1, pages + 1)]

    body = "".join(
        f"  <sitemap>\n    <loc>{BASE_URL}{c}</loc>\n  </sitemap>\n" for c in children
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}"
        "</sitemapindex>"
    )


def build_pages() -> str:
    """Sous-sitemap des pages statiques."""
    return _urlset([f"{BASE_URL}{p}" for p in STATIC_PAGES])


def build_org_page(segment: str, page: int) -> str | None:
    """Sous-sitemap n° `page` (1-indexé) pour un type d'organisation.

    Retourne None si le segment est inconnu ou la page hors limites.
    """
    if segment not in ORG_SITEMAPS:
        return None
    table, id_col = ORG_SITEMAPS[segment]
    ids = _org_ids(table, id_col)
    if page < 1 or (page - 1) * URLS_PER_SITEMAP >= max(1, len(ids)):
        return None
    start = (page - 1) * URLS_PER_SITEMAP
    chunk = ids[start : start + URLS_PER_SITEMAP]
    return _urlset([f"{BASE_URL}/{segment}/{org_id}" for org_id in chunk])
