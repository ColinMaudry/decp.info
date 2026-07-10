"""Représentation canonique d'un filtre (AST booléen) et compilation en SQL DuckDB.

Ce module est indépendant de l'UI : plusieurs producteurs (filtres de colonne
AG Grid, futur champ de requête booléenne #97) construisent le même AST, compilé
ici en SQL paramétré. Les identifiants de colonnes sont validés contre le schéma ;
les valeurs passent toujours par le binding `?` (jamais concaténées).
"""

from dataclasses import dataclass

import polars as pl

from src.utils import logger
from src.utils.table_sql import tokenize_text_filter


@dataclass
class Condition:
    column: str
    operator: str
    value: object = None
    value2: object = None


@dataclass
class And:
    children: list


@dataclass
class Or:
    children: list


@dataclass
class Not:
    child: object


Node = object  # Condition | And | Or | Not | None


def ast_to_sql(node, schema: pl.Schema) -> tuple[str, list]:
    """Compile un AST en (where_sql, params). Nœud neutre -> ('TRUE', [])."""
    if node is None:
        return "TRUE", []
    if isinstance(node, And):
        return _join(node.children, "AND", schema)
    if isinstance(node, Or):
        return _join(node.children, "OR", schema)
    if isinstance(node, Not):
        sql, params = ast_to_sql(node.child, schema)
        if sql == "TRUE":
            return "TRUE", []
        return f"NOT ({sql})", params
    if isinstance(node, Condition):
        return _condition_to_sql(node, schema)
    logger.warning(f"Nœud AST inconnu ignoré : {node!r}")
    return "TRUE", []


def _join(children, op: str, schema: pl.Schema) -> tuple[str, list]:
    fragments: list[str] = []
    params: list = []
    for child in children:
        sql, child_params = ast_to_sql(child, schema)
        if sql == "TRUE":
            continue
        fragments.append(f"({sql})")
        params.extend(child_params)
    if not fragments:
        return "TRUE", []
    return f" {op} ".join(fragments), params


def _condition_to_sql(cond: Condition, schema: pl.Schema) -> tuple[str, list]:
    col = cond.column
    if col not in schema.names():
        logger.warning(f"Colonne inconnue ignorée : {col!r}")
        return "TRUE", []

    col_type = schema[col]
    quoted = f'"{col}"'

    if cond.operator == "blank":
        return f"({quoted} IS NULL OR {quoted} = '')", []
    if cond.operator == "notBlank":
        return f"({quoted} IS NOT NULL AND {quoted} <> '')", []

    is_numeric = col_type.is_numeric()
    col_is_date = col_type == pl.Date

    if is_numeric:
        return _numeric_to_sql(cond, col_type, quoted)

    # texte / date : traité comme texte (parité avec l'existant)
    if cond.operator == "contains":
        return tokenize_text_filter(col, str(cond.value), col_is_date)
    if cond.operator == "notContains":
        where, params = tokenize_text_filter(col, str(cond.value), col_is_date)
        return f"NOT ({where})", params

    target = f"CAST({quoted} AS VARCHAR)" if col_is_date else quoted
    op_map = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if cond.operator in op_map:
        return f"{quoted} IS NOT NULL AND {target} {op_map[cond.operator]} ?", [
            str(cond.value)
        ]
    if cond.operator == "startsWith":
        return f"{quoted} ILIKE ?", [f"{cond.value}%"]
    if cond.operator == "endsWith":
        return f"{quoted} ILIKE ?", [f"%{cond.value}"]
    logger.warning(f"Opérateur texte invalide : {cond.operator!r}")
    return "TRUE", []


def _coerce_number(value, col_type):
    try:
        return int(value) if col_type.is_integer() else float(value)
    except (TypeError, ValueError):
        logger.warning(f"Valeur numérique invalide ignorée : {value!r}")
        return None


def _numeric_to_sql(cond: Condition, col_type, quoted: str) -> tuple[str, list]:
    op_map = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if cond.operator in op_map:
        v = _coerce_number(cond.value, col_type)
        if v is None:
            return "TRUE", []
        return f"{quoted} IS NOT NULL AND {quoted} {op_map[cond.operator]} ?", [v]
    if cond.operator == "range":
        v1 = _coerce_number(cond.value, col_type)
        v2 = _coerce_number(cond.value2, col_type)
        if v1 is None or v2 is None:
            return "TRUE", []
        return f"{quoted} BETWEEN ? AND ?", [v1, v2]
    logger.warning(f"Opérateur numérique invalide : {cond.operator!r}")
    return "TRUE", []
