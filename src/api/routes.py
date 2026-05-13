from flask_smorest import Blueprint

from src.api.auth import require_token
from src.db import schema as duckdb_schema

bp = Blueprint(
    "api_v1",
    "api_v1",
    url_prefix="/api/v1",
    description="API privée decp.info — accès tabulaire aux marchés publics.",
)


@bp.route("/health")
def health():
    """Sonde de santé, sans authentification."""
    return {"status": "ok"}


@bp.route("/schema")
@require_token
def schema():
    """Liste des colonnes disponibles dans le dataset DECP."""
    cols = [{"name": name, "type": str(dtype)} for name, dtype in duckdb_schema.items()]
    return {"columns": cols}
