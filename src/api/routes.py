from flask_smorest import Blueprint

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
