import polars as pl

from src.utils import logger
from src.utils.table import split_filter_part


def filter_query_to_sql(filter_query: str, schema: pl.Schema) -> tuple[str, list]:
    """Traduit le DSL de filtres de dash_table.DataTable en fragment SQL DuckDB.

    Retourne (where_clause, params) où where_clause est un fragment à injecter
    après WHERE et params est la liste des valeurs à passer à
    cursor.execute(sql, params). Les identifiants de colonnes sont validés
    contre le schéma fourni ; jamais concaténés avec des valeurs utilisateur.
    """
    if not filter_query:
        return "TRUE", []

    clauses: list[str] = []
    params: list = []

    for part in filter_query.split(" && "):
        col_name, operator, raw_value = split_filter_part(part)
        if not isinstance(col_name, str) or not isinstance(raw_value, str):
            continue

        if col_name not in schema.names():
            logger.warning(f"Colonne inconnue ignorée : {col_name!r}")
            continue

        col_type = schema[col_name]
        is_numeric = isinstance(
            col_type, (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64)
        )
        col_is_date = col_type == pl.Date
        quoted_col = f'"{col_name}"'

        if is_numeric:
            try:
                value = (
                    int(raw_value)
                    if isinstance(col_type, (pl.Int8, pl.Int16, pl.Int32, pl.Int64))
                    else float(raw_value)
                )
            except ValueError:
                logger.warning(f"Valeur numérique invalide ignorée : {raw_value!r}")
                continue

            if operator == "contains":
                clauses.append(f"{quoted_col} IS NOT NULL AND {quoted_col} = ?")
            elif operator == ">":
                clauses.append(f"{quoted_col} IS NOT NULL AND {quoted_col} > ?")
            elif operator == "<":
                clauses.append(f"{quoted_col} IS NOT NULL AND {quoted_col} < ?")
            else:
                logger.warning(f"Opérateur invalide pour numérique : {operator!r}")
                continue
            params.append(value)
            continue

        # String / Date : toujours traité comme texte (parité avec Polars)
        value = raw_value.strip('"')

        if operator == "contains":
            if value.endswith("*") and not value.startswith("*"):
                like = value[:-1] + "%"
            elif value.startswith("*") and not value.endswith("*"):
                like = "%" + value[1:]
            elif value.startswith("*") and value.endswith("*"):
                like = "%" + value[1:-1] + "%"
            else:
                like = "%" + value + "%"
            target = f"CAST({quoted_col} AS VARCHAR)" if col_is_date else quoted_col
            clauses.append(
                f"{quoted_col} IS NOT NULL AND {target} <> '' AND {target} ILIKE ?"
            )
            params.append(like)
        elif operator in (">", "<"):
            target = f"CAST({quoted_col} AS VARCHAR)" if col_is_date else quoted_col
            clauses.append(f"{quoted_col} IS NOT NULL AND {target} {operator} ?")
            params.append(value)
        else:
            logger.warning(f"Opérateur invalide pour chaîne : {operator!r}")
            continue

    if not clauses:
        return "TRUE", []
    return " AND ".join(clauses), params


def sort_by_to_sql(sort_by: list[dict] | None, schema: pl.Schema) -> str:
    """Traduit sort_by (format Dash) en clause ORDER BY DuckDB.

    Retourne '' si pas de tri (aucun ORDER BY à ajouter).
    """
    if not sort_by:
        return ""

    fragments: list[str] = []
    for entry in sort_by:
        col = entry.get("column_id")
        direction = entry.get("direction")
        if col not in schema.names():
            logger.warning(f"Tri sur colonne inconnue ignoré : {col!r}")
            continue
        if direction not in ("asc", "desc"):
            continue
        fragments.append(f'"{col}" {direction.upper()} NULLS LAST')

    return ", ".join(fragments)
