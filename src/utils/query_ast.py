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

    is_numeric = col_type.is_numeric()
    col_is_date = col_type == pl.Date

    if cond.operator == "blank":
        if is_numeric or col_is_date:
            return f"{quoted} IS NULL", []
        return f"({quoted} IS NULL OR {quoted} = '')", []
    if cond.operator == "notBlank":
        if is_numeric or col_is_date:
            return f"{quoted} IS NOT NULL", []
        return f"({quoted} IS NOT NULL AND {quoted} <> '')", []

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
    if cond.operator == "range":
        return f"{quoted} IS NOT NULL AND {target} BETWEEN ? AND ?", [
            str(cond.value),
            str(cond.value2),
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


_TEXT_TYPE = {
    "contains": "contains",
    "notContains": "notContains",
    "equals": "eq",
    "notEqual": "neq",
    "startsWith": "startsWith",
    "endsWith": "endsWith",
    "blank": "blank",
    "notBlank": "notBlank",
}
_NUM_TYPE = {
    "equals": "eq",
    "notEqual": "neq",
    "lessThan": "lt",
    "lessThanOrEqual": "lte",
    "greaterThan": "gt",
    "greaterThanOrEqual": "gte",
    "inRange": "range",
    "blank": "blank",
    "notBlank": "notBlank",
}


def _leaf(column: str, spec: dict):
    """Convertit une condition AG Grid unitaire en Condition."""
    ftype = spec.get("filterType", "text")
    ag_type = spec.get("type")
    if ftype == "date":
        op = _NUM_TYPE.get(ag_type)
        if op == "range":
            return Condition(column, "range", spec.get("dateFrom"), spec.get("dateTo"))
        return Condition(column, op, spec.get("dateFrom")) if op else None
    if ftype == "number":
        op = _NUM_TYPE.get(ag_type)
        if op == "range":
            return Condition(column, "range", spec.get("filter"), spec.get("filterTo"))
        return Condition(column, op, spec.get("filter")) if op else None
    # texte
    op = _TEXT_TYPE.get(ag_type)
    return Condition(column, op, spec.get("filter")) if op else None


def filtermodel_to_ast(filter_model, schema):
    """Traduit un filterModel AG Grid en AST. Colonnes combinées en And."""
    if not filter_model:
        return None
    children = []
    for column, spec in filter_model.items():
        if column not in schema.names():
            logger.warning(f"Filtre sur colonne inconnue ignoré : {column!r}")
            continue
        if "operator" in spec:  # deux conditions
            c1 = _leaf(column, spec.get("condition1", {}))
            c2 = _leaf(column, spec.get("condition2", {}))
            parts = [c for c in (c1, c2) if c is not None]
            if not parts:
                continue
            node = And(parts) if spec["operator"] == "AND" else Or(parts)
        else:
            node = _leaf(column, spec)
            if node is None:
                continue
        children.append(node)
    return And(children) if children else None
