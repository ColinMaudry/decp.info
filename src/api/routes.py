from flask import g, request
from flask_smorest import Blueprint, abort

from src.api import tracking
from src.api.auth import require_token
from src.api.filters import FilterError, build_where
from src.db import count_marches, query_marches
from src.db import schema as duckdb_schema

bp = Blueprint(
    "api_v1",
    "api_v1",
    url_prefix="/api/v1",
    description="API privée decp.info — accès tabulaire aux marchés publics.",
)

MAX_PAGE_SIZE = 1000


def _parse_pagination():
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "50"))
    except ValueError:
        abort(400, message="page et page_size doivent être des entiers")
    if page < 1:
        abort(400, message="page doit être >= 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        abort(
            400,
            message=f"page_size doit être dans [1, {MAX_PAGE_SIZE}]",
        )
    return page, page_size


def _parse_columns():
    raw = request.args.get("columns")
    if not raw:
        return None
    cols = [c.strip() for c in raw.split(",") if c.strip()]
    unknown = [c for c in cols if c not in duckdb_schema]
    if unknown:
        abort(400, message=f"Colonnes inconnues : {unknown}")
    return cols


def _build_links(page, page_size, total):
    base = request.path
    qs = request.args.to_dict(flat=False)
    qs.pop("page", None)

    def url_for(p):
        from urllib.parse import urlencode

        params = [(k, v) for k, vs in qs.items() for v in vs]
        params.append(("page", str(p)))
        return f"{base}?{urlencode(params)}"

    prev_url = url_for(page - 1) if page > 1 else None
    next_url = None
    if total is None or page * page_size < total:
        next_url = url_for(page + 1)
    return {"prev": prev_url, "next": next_url}


@bp.after_request
def _track_consumption(response):
    token_id = getattr(g, "token_id", None)
    if token_id is not None:
        tracking.enqueue_counter_update(token_id)
        tracking.enqueue_matomo_event(
            token_id=token_id,
            path=request.path,
            query_string=request.query_string.decode("utf-8", errors="replace"),
            status_code=response.status_code,
            user_agent=request.headers.get("User-Agent", ""),
        )
    return response


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


@bp.route("/data")
@require_token
def data():
    """Endpoint tabulaire : filtres dynamiques sur les colonnes DECP."""
    import polars as pl
    import polars.selectors as cs

    page, page_size = _parse_pagination()
    columns = _parse_columns()
    count = request.args.get("count", "true").lower() != "false"

    try:
        where_sql, params, order_sql = build_where(
            list(request.args.items(multi=True)), duckdb_schema
        )
    except FilterError as e:
        abort(400, message=str(e), errors={"field": e.field})

    df = query_marches(
        where_sql=where_sql,
        params=params,
        columns=columns,
        order_by=order_sql,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    # JSON ne sérialise pas date/datetime nativement → cast en string ISO
    df_ready = df.with_columns(cs.temporal().cast(pl.String))

    total = count_marches(where_sql, params) if count else None
    meta = {"page": page, "page_size": page_size}
    if total is not None:
        meta["total"] = total

    return {
        "data": df_ready.to_dicts(),
        "meta": meta,
        "links": _build_links(page, page_size, total),
    }
