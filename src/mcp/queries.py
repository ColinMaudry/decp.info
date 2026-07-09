# src/mcp/queries.py
import re

from src.mcp.serialization import (
    to_json_records,  # noqa: F401 (utilisé aux tâches suivantes)
)
from src.utils.data import DF_ACHETEURS, DF_TITULAIRES
from src.utils.search import search_org

PAGE_SIZE = 50
TOP_N = 10
ORG_FRAMES = {"acheteur": DF_ACHETEURS, "titulaire": DF_TITULAIRES}


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
