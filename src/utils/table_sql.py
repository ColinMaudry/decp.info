from datetime import datetime, timedelta

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
        is_numeric = col_type.is_numeric()
        col_is_date = col_type == pl.Date
        quoted_col = f'"{col_name}"'

        if is_numeric:
            try:
                value = int(raw_value) if col_type.is_integer() else float(raw_value)
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
            logger.warning(f"Tri sur direction inconnue ignoré : {direction!r}")
            continue
        fragments.append(f'"{col}" {direction.upper()} NULLS LAST')

    return ", ".join(fragments)


def dashboard_filters_to_sql(
    dashboard_year=None,
    dashboard_acheteur_id=None,
    dashboard_acheteur_categorie=None,
    dashboard_acheteur_departement_code=None,
    dashboard_titulaire_id=None,
    dashboard_titulaire_categorie=None,
    dashboard_titulaire_departement_code=None,
    dashboard_marche_type=None,
    dashboard_marche_objet=None,
    dashboard_marche_code_cpv=None,
    dashboard_marche_considerations_sociales=None,
    dashboard_marche_considerations_environnementales=None,
    dashboard_marche_techniques=None,
    dashboard_marche_innovant=None,
    dashboard_marche_sous_traitance_declaree=None,
    dashboard_montant_min=None,
    dashboard_montant_max=None,
) -> tuple[str, list]:
    """Traduit les filtres du tableau de bord en (where_clause, params) DuckDB."""
    clauses: list[str] = []
    params: list = []

    if dashboard_year:
        clauses.append('YEAR("dateNotification") = ?')
        params.append(int(dashboard_year))
    else:
        clauses.append('"dateNotification" > ?')
        params.append(datetime.now() - timedelta(days=365))

    return " AND ".join(clauses), params
