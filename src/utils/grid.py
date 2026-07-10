"""Datasource server-side pour AG Grid (infinite row model)."""

from src.db import count_marches, query_marches, schema
from src.utils.query_ast import ast_to_sql, filtermodel_to_ast, sort_model_to_sql
from src.utils.table import postprocess_page


def fetch_grid_page(
    filter_model,
    sort_model,
    start_row: int,
    end_row: int,
    base_where_sql: str = "TRUE",
    base_params: tuple = (),
) -> tuple[list[dict], int]:
    """Renvoie (row_data, total_count) pour un bloc [start_row, end_row)."""
    ast = filtermodel_to_ast(filter_model, schema)
    filter_sql, filter_params = ast_to_sql(ast, schema)
    where_sql = f"({base_where_sql}) AND ({filter_sql})"
    params = [*base_params, *filter_params]

    order_by = sort_model_to_sql(sort_model, schema) or None
    total = count_marches(where_sql, params)

    limit = max(0, end_row - start_row)
    page = query_marches(
        where_sql=where_sql,
        params=params,
        order_by=order_by,
        limit=limit,
        offset=start_row,
    )
    page = postprocess_page(page)
    return page.to_dicts(), total
