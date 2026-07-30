"""Arithmétique de pagination des pages SEO rendues côté serveur.

Isolée de Flask et de DuckDB pour être testable seule. `PAGE_SIZE` est une
constante de module afin que les tests puissent la monkeypatcher plutôt que de
fabriquer des centaines de lignes de données.
"""

PAGE_SIZE = 100


def parse_page(raw: str | None) -> int:
    """Numéro de page depuis la query string.

    Lève `ValueError` sur toute valeur non strictement positive ou non
    numérique ; l'appelant traduit en 404.
    """
    if raw is None:
        return 1
    if not raw.isdigit():
        raise ValueError(f"numéro de page invalide : {raw!r}")
    page = int(raw)
    if page < 1:
        raise ValueError(f"numéro de page invalide : {raw!r}")
    return page


def page_count(total: int) -> int:
    """Nombre de pages nécessaires pour `total` entrées (au moins 1)."""
    return max(1, -(-total // PAGE_SIZE))


def offset(page: int) -> int:
    """OFFSET SQL correspondant à une page 1-indexée."""
    return (page - 1) * PAGE_SIZE
