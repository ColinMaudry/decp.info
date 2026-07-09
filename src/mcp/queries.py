# src/mcp/queries.py
import re

from src.api.filters import FilterError, build_where
from src.db import count_marches, query_marches
from src.db import schema as duckdb_schema
from src.mcp.serialization import to_json_records
from src.utils.data import DF_ACHETEURS, DF_TITULAIRES
from src.utils.search import search_org

PAGE_SIZE = 50
TOP_N = 10
ORG_FRAMES = {"acheteur": DF_ACHETEURS, "titulaire": DF_TITULAIRES}

# Colonnes renvoyées par rechercher_marches (sortie ciblée, pas SELECT *).
MARCHES_COLUMNS = [
    "uid",
    "objet",
    "montant",
    "dateNotification",
    "codeCPV",
    "acheteur_id",
    "acheteur_nom",
    "acheteur_departement_code",
    "titulaire_id",
    "titulaire_nom",
]

# (param nommé, colonne decp, opérateur du moteur de filtres API).
# `greater` = >=, `less` = <=, `contains` = LIKE %v%, `exact` = =.
_NAMED_FILTERS = [
    ("acheteur_id", "acheteur_id", "exact"),
    ("titulaire_id", "titulaire_id", "exact"),
    ("cpv", "codeCPV", "contains"),
    ("objet_contient", "objet", "contains"),
    ("montant_min", "montant", "greater"),
    ("montant_max", "montant", "less"),
    ("date_min", "dateNotification", "greater"),
    ("date_max", "dateNotification", "less"),
    ("departement", "acheteur_departement_code", "exact"),
]


def build_where_args(
    named: dict, filtres_avances: dict | None
) -> list[tuple[str, str]]:
    """Traduit les paramètres nommés + filtres avancés en tuples (col__op, valeur)."""
    args: list[tuple[str, str]] = []
    for param, col, op in _NAMED_FILTERS:
        value = named.get(param)
        if value is not None:
            args.append((f"{col}__{op}", str(value)))
    if filtres_avances:
        for key, value in filtres_avances.items():
            args.append((key, str(value)))
    return args


def search_marches(
    *,
    acheteur_id: str | None = None,
    titulaire_id: str | None = None,
    cpv: str | None = None,
    objet_contient: str | None = None,
    montant_min: float | None = None,
    montant_max: float | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    departement: str | None = None,
    page: int = 1,
    filtres_avances: dict | None = None,
) -> dict:
    """Recherche paginée de marchés. Même sémantique de filtres que l'API REST."""
    named = {
        "acheteur_id": acheteur_id,
        "titulaire_id": titulaire_id,
        "cpv": cpv,
        "objet_contient": objet_contient,
        "montant_min": montant_min,
        "montant_max": montant_max,
        "date_min": date_min,
        "date_max": date_max,
        "departement": departement,
    }
    args = build_where_args(named, filtres_avances)
    try:
        where_sql, params, order_sql = build_where(args, duckdb_schema)
    except FilterError as e:
        return {"error": str(e), "champ": e.field}

    page = max(1, int(page))
    offset = (page - 1) * PAGE_SIZE
    order_by = order_sql or '"dateNotification" DESC, "uid" DESC'
    df = query_marches(
        where_sql,
        params,
        columns=MARCHES_COLUMNS,
        order_by=order_by,
        limit=PAGE_SIZE,
        offset=offset,
    )
    total = count_marches(where_sql, params)
    return {
        "meta": {"page": page, "page_size": PAGE_SIZE, "total": total},
        "marches": to_json_records(df),
    }


def _extract_plain_text(html_str: str) -> str:
    """Extract plain text from HTML link, e.g. '<a...>123</a>' -> '123'."""
    match = re.search(r">([^<]+)<", html_str)
    return match.group(1) if match else html_str


def search_organisations(
    query: str, org_type: str = "acheteur", limite: int = 20
) -> list[dict]:
    """Recherche des organisations par nom, résout un nom -> id."""
    if org_type not in ORG_FRAMES:
        raise ValueError(
            f"type invalide: {org_type!r} (attendu 'acheteur' ou 'titulaire')"
        )
    df = search_org(ORG_FRAMES[org_type], query, org_type, track=False).head(limite)
    return [
        {
            "id": _extract_plain_text(r[f"{org_type}_id"]),
            "nom": _extract_plain_text(r[f"{org_type}_nom"]),
            "departement": r.get("Département"),
        }
        for r in df.to_dicts()
    ]
