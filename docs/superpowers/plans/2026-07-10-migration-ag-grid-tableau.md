# Migration AG Grid — `tableau.py` (Lot 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la `DataTable` de la page `/tableau` par une grille `dash-ag-grid` (scroll infini, server-side) en préservant toutes les fonctionnalités, avec un moteur de requête AST → SQL DuckDB comme socle canonique.

**Architecture:** AG Grid n'est qu'une grille d'affichage en `rowModelType="infinite"` ; c'est un callback Dash qui reçoit `getRowsRequest` (filterModel + sortModel), le compile via un AST booléen en SQL DuckDB paramétré, et renvoie `getRowsResponse`. Le même AST alimente l'export Excel et les vues sauvegardées. Le DSL de filtre historique et l'URL riche sont retirés.

**Tech Stack:** Dash 3.4, dash-ag-grid, DuckDB, Polars, flask-caching, SQLite (vues), pytest + DashComposite/Selenium.

**Spec de référence:** `docs/superpowers/specs/2026-07-09-migration-ag-grid-design.md`

## Global Constraints

- Périmètre = **`tableau.py` uniquement**. Ne pas toucher `acheteur.py`, `titulaire.py`, `observatoire.py`, `recherche.py`, `admin/liste.py`, `figures.make_table`.
- Imports internes toujours préfixés `src.` (ex. `src.utils.query_ast`).
- **Apparence de base d'AG Grid** : aucun thème/override CSS custom dans ce lot.
- **Scroll infini** (pas de pagination numérotée) ; grille à hauteur fixe, jamais `domLayout: "autoHeight"`.
- **Export Excel** via DuckDB (AST→SQL), pas de pipeline Polars.
- Sécurité : identifiants de colonnes validés contre `schema.names()`, valeurs **toujours** liées via `?` (jamais concaténées).
- Lancer `pre-commit run --files <fichiers>` avant chaque `git add`/commit (le hook prettier/ruff peut reformater — re-`git add` puis committer).
- Tests par fichier pendant le lot ; `uv run pytest` complet **uniquement** à la dernière tâche.
- Ne pas supprimer `filter_query_to_sql` / `clean_filters` (encore utilisés par les autres pages) — seulement les débrancher de `tableau.py`.

**Fonctions réutilisables (ne pas réécrire) :**

- `src/db.py` : `schema` (pl.Schema), `query_marches(where_sql, params, columns, order_by, limit, offset)`, `count_marches(where_sql, params)`, `count_unique_marches(where_sql, params)`.
- `src/utils/table_sql.py` : `tokenize_text_filter(column, text, col_is_date=False) -> (where_clause, params)`, `sort_by_to_sql(sort_by, schema) -> str`.
- `src/utils/table.py` : `postprocess_page(dff) -> pl.DataFrame`, `setup_table_columns(dff, hideable, exclude) -> (columns, tooltip)`, `get_default_hidden_columns(page) -> list`, `invert_columns(columns) -> list`, `write_styled_excel(df, buffer, worksheet="DECP")`, `COLUMNS` (= `schema.names()`).
- `src/figures.py` : `make_column_picker(page)`, `DATA_SCHEMA` (dict `{col: {title, description, type, name}}`).
- `src/saved_views/db.py` : `list_views(user_id, table_name)`, `get(view_id, user_id)`, `upsert(user_id, table_name, name, query)`.
- `src/pages/_compte_shell.py` : `current_user_has_subscription()`.

---

## File Structure

- **Create** `src/utils/query_ast.py` — types AST (`Condition/And/Or/Not`), `ast_to_sql`, `filtermodel_to_ast`, `sort_model_to_sql`, sérialisation `ast_to_dict`/`ast_from_dict`.
- **Create** `src/utils/grid.py` — `fetch_grid_page(...)` (colle filterModel/sortModel → SQL → page + total) et `grid_column_defs(...)`.
- **Create** `tests/test_query_ast.py`, `tests/test_grid.py`.
- **Modify** `src/figures.py` — ajouter la fabrique `ag_grid(...)`.
- **Modify** `src/pages/tableau.py` — layout + callbacks réécrits.
- **Modify** `src/saved_views/*` si besoin (le champ `query` stocke désormais un JSON).
- **Modify** `pyproject.toml` / `uv.lock` — dépendance `dash-ag-grid`.
- **Modify** `src/assets/dash_clientside.js` — retirer l'usage `clean_filters` côté tableau (garder la fonction pour les autres pages).

---

## Task 1: Ajouter la dépendance `dash-ag-grid`

**Files:**

- Modify: `pyproject.toml`, `uv.lock`

- [ ] **Step 1: Ajouter la dépendance**

Run: `uv add dash-ag-grid`
Expected: `pyproject.toml` gagne `dash-ag-grid` dans `dependencies`, `uv.lock` mis à jour.

- [ ] **Step 2: Vérifier l'import et la version**

Run: `uv run python -c "import dash_ag_grid as dag; print(dag.__version__)"`
Expected: une version s'affiche (35.x attendu), pas d'erreur.

- [ ] **Step 3: Vérifier la compatibilité Dash (démarrage app)**

Run: `uv run python -c "import dash_ag_grid; from src import app; print('ok')"`
Expected: `ok` (pas de conflit de version Dash au chargement).

- [ ] **Step 4: Commit**

```bash
pre-commit run --files pyproject.toml uv.lock
git add pyproject.toml uv.lock
git commit -m "build: ajouter la dépendance dash-ag-grid (#41)"
```

---

## Task 2: Types AST + `ast_to_sql`

Compilateur canonique AST → SQL DuckDB paramétré. Réutilise `tokenize_text_filter` pour les feuilles texte (insensibilité casse/accents, `*`, `+`, multi-mots) ; mirroir de la logique numérique/date de `filter_query_to_sql`.

**Files:**

- Create: `src/utils/query_ast.py`
- Test: `tests/test_query_ast.py`

**Interfaces:**

- Produces:

  - `Condition(column: str, operator: str, value=None, value2=None)` — operators : `"contains"`, `"notContains"`, `"eq"`, `"neq"`, `"gt"`, `"gte"`, `"lt"`, `"lte"`, `"range"`, `"blank"`, `"notBlank"`.
  - `And(children: list)`, `Or(children: list)`, `Not(child)`.
  - `ast_to_sql(node, schema) -> tuple[str, list]` — renvoie `(where_sql, params)`. `node=None` ou `And([])` → `("TRUE", [])`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_query_ast.py
import polars as pl
import pytest
from src.utils.query_ast import Condition, And, Or, Not, ast_to_sql

SCHEMA = pl.Schema(
    {
        "acheteur_nom": pl.String,
        "objet": pl.String,
        "montant": pl.Float64,
        "dureeMois": pl.Int64,
        "dateNotification": pl.Date,
    }
)


def _run(node):
    """Compile et retourne (sql, params)."""
    return ast_to_sql(node, SCHEMA)


def test_none_is_true():
    assert _run(None) == ("TRUE", [])


def test_empty_and_is_true():
    assert _run(And([])) == ("TRUE", [])


def test_text_contains_uses_ilike_and_params():
    sql, params = _run(Condition("objet", "contains", "voirie"))
    assert "ILIKE ?" in sql
    assert params == ["%voirie%"]


def test_text_contains_multiword_is_and():
    sql, params = _run(Condition("objet", "contains", "metropole rennes"))
    assert sql.count("ILIKE ?") == 2
    assert params == ["%metropole%", "%rennes%"]


def test_text_contains_wildcard_and_phrase():
    _, params = _run(Condition("objet", "contains", "distri* metropole+rennes"))
    assert params == ["distri%", "%metropole rennes%"]


def test_text_notcontains_negates():
    sql, params = _run(Condition("objet", "notContains", "construction"))
    assert "NOT (" in sql
    assert params == ["%construction%"]


def test_numeric_gt():
    sql, params = _run(Condition("montant", "gt", 40000))
    assert '"montant" > ?' in sql
    assert params == [40000.0]


def test_numeric_eq_int_column():
    sql, params = _run(Condition("dureeMois", "eq", "12"))
    assert '"dureeMois" = ?' in sql
    assert params == [12]


def test_numeric_range():
    sql, params = _run(Condition("montant", "range", 100, 200))
    assert params == [100.0, 200.0]
    assert "BETWEEN" in sql or ("> ?" in sql and "< ?" in sql)


def test_numeric_invalid_value_is_true():
    # valeur non numérique -> condition neutralisée (TRUE), pas d'exception
    assert _run(Condition("montant", "gt", "abc")) == ("TRUE", [])


def test_date_gt_casts_varchar():
    sql, params = _run(Condition("dateNotification", "gt", "2022"))
    assert "VARCHAR" in sql
    assert params == ["2022"]


def test_blank_and_notblank():
    sql_b, _ = _run(Condition("objet", "blank"))
    assert "IS NULL" in sql_b
    sql_nb, _ = _run(Condition("objet", "notBlank"))
    assert "IS NOT NULL" in sql_nb


def test_unknown_column_is_true():
    assert _run(Condition("colonne_inexistante", "contains", "x")) == ("TRUE", [])


def test_and_or_not_grouping():
    node = And(
        [
            Or([Condition("objet", "contains", "beton"), Condition("objet", "contains", "ciment")]),
            Not(Condition("objet", "contains", "demolition")),
        ]
    )
    sql, params = _run(node)
    assert " OR " in sql and " AND " in sql and "NOT (" in sql
    assert params == ["%beton%", "%ciment%", "%demolition%"]
```

- [ ] **Step 2: Lancer les tests (échec attendu)**

Run: `uv run pytest tests/test_query_ast.py -q`
Expected: FAIL (`ModuleNotFoundError: src.utils.query_ast`).

- [ ] **Step 3: Écrire l'implémentation**

```python
# src/utils/query_ast.py
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

    target = f'CAST({quoted} AS VARCHAR)' if col_is_date else quoted
    op_map = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if cond.operator in op_map:
        return f"{quoted} IS NOT NULL AND {target} {op_map[cond.operator]} ?", [str(cond.value)]
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
```

- [ ] **Step 4: Lancer les tests (succès attendu)**

Run: `uv run pytest tests/test_query_ast.py -q`
Expected: PASS (tous).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/utils/query_ast.py tests/test_query_ast.py
git add src/utils/query_ast.py tests/test_query_ast.py
git commit -m "feat(query): AST de filtre + compilateur ast_to_sql (#41)"
```

---

## Task 3: `filtermodel_to_ast`

Traduit le `filterModel` d'AG Grid en AST. Chaque colonne devient une (ou deux) `Condition`, combinées entre colonnes par `And`. Une colonne à deux conditions utilise `operator` `AND`/`OR`.

**Files:**

- Modify: `src/utils/query_ast.py`
- Test: `tests/test_query_ast.py`

**Interfaces:**

- Produces: `filtermodel_to_ast(filter_model: dict | None, schema) -> Node` (renvoie `And([...])` ou `None` si vide).

- [ ] **Step 1: Ajouter les tests qui échouent**

```python
# tests/test_query_ast.py  (append)
from src.utils.query_ast import filtermodel_to_ast, ast_to_sql


def test_filtermodel_empty_is_none():
    assert filtermodel_to_ast(None, SCHEMA) is None
    assert filtermodel_to_ast({}, SCHEMA) is None


def test_filtermodel_text_contains():
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "voirie"}}
    _, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA)
    assert params == ["%voirie%"]


def test_filtermodel_number_greaterthan():
    fm = {"montant": {"filterType": "number", "type": "greaterThan", "filter": 40000}}
    sql, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA)
    assert '"montant"' in sql and params == [40000.0]


def test_filtermodel_number_inrange():
    fm = {"montant": {"filterType": "number", "type": "inRange", "filter": 100, "filterTo": 200}}
    _, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA)
    assert params == [100.0, 200.0]


def test_filtermodel_date_uses_datefrom():
    fm = {"dateNotification": {"filterType": "date", "type": "greaterThan", "dateFrom": "2022-01-01"}}
    _, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA)
    assert params == ["2022-01-01"]


def test_filtermodel_two_conditions_or():
    fm = {
        "objet": {
            "filterType": "text",
            "operator": "OR",
            "condition1": {"filterType": "text", "type": "contains", "filter": "beton"},
            "condition2": {"filterType": "text", "type": "contains", "filter": "ciment"},
        }
    }
    sql, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA)
    assert " OR " in sql and params == ["%beton%", "%ciment%"]


def test_filtermodel_multiple_columns_are_anded():
    fm = {
        "objet": {"filterType": "text", "type": "contains", "filter": "voirie"},
        "montant": {"filterType": "number", "type": "greaterThan", "filter": 1000},
    }
    sql, params = ast_to_sql(filtermodel_to_ast(fm, SCHEMA), SCHEMA)
    assert " AND " in sql and set(params) == {"%voirie%", 1000.0}
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `uv run pytest tests/test_query_ast.py -q -k filtermodel`
Expected: FAIL (`filtermodel_to_ast` non défini).

- [ ] **Step 3: Implémenter**

```python
# src/utils/query_ast.py  (append)

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
```

- [ ] **Step 4: Lancer (succès attendu)**

Run: `uv run pytest tests/test_query_ast.py -q`
Expected: PASS (tous, y compris Task 2).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/utils/query_ast.py tests/test_query_ast.py
git add src/utils/query_ast.py tests/test_query_ast.py
git commit -m "feat(query): filtermodel_to_ast (filterModel AG Grid -> AST) (#41)"
```

---

## Task 4: `sort_model_to_sql` + sérialisation AST

`sortModel` AG Grid = `[{"colId": "montant", "sort": "desc"}]`. On l'adapte vers `sort_by_to_sql` existant (qui attend `[{"column_id", "direction"}]`). On ajoute aussi la (dé)sérialisation JSON de l'AST pour les vues sauvegardées.

**Files:**

- Modify: `src/utils/query_ast.py`
- Test: `tests/test_query_ast.py`

**Interfaces:**

- Produces:

  - `sort_model_to_sql(sort_model: list | None, schema) -> str` (fragment ORDER BY, `''` si vide).
  - `ast_to_dict(node) -> dict | None` / `ast_from_dict(data) -> Node` (round-trip JSON).

- [ ] **Step 1: Ajouter les tests qui échouent**

```python
# tests/test_query_ast.py  (append)
from src.utils.query_ast import sort_model_to_sql, ast_to_dict, ast_from_dict


def test_sort_model_to_sql():
    sm = [{"colId": "montant", "sort": "desc"}, {"colId": "dureeMois", "sort": "asc"}]
    out = sort_model_to_sql(sm, SCHEMA)
    assert out == '"montant" DESC NULLS LAST, "dureeMois" ASC NULLS LAST'


def test_sort_model_empty():
    assert sort_model_to_sql(None, SCHEMA) == ""
    assert sort_model_to_sql([], SCHEMA) == ""


def test_ast_dict_roundtrip():
    node = And([Or([Condition("objet", "contains", "beton")]), Not(Condition("objet", "contains", "x"))])
    restored = ast_from_dict(ast_to_dict(node))
    assert ast_to_sql(restored, SCHEMA) == ast_to_sql(node, SCHEMA)


def test_ast_dict_none():
    assert ast_to_dict(None) is None
    assert ast_from_dict(None) is None
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `uv run pytest tests/test_query_ast.py -q -k "sort_model or roundtrip or dict_none"`
Expected: FAIL.

- [ ] **Step 3: Implémenter**

```python
# src/utils/query_ast.py  (append)
from src.utils.table_sql import sort_by_to_sql


def sort_model_to_sql(sort_model, schema) -> str:
    if not sort_model:
        return ""
    sort_by = [
        {"column_id": s.get("colId"), "direction": s.get("sort")} for s in sort_model
    ]
    return sort_by_to_sql(sort_by, schema)


def ast_to_dict(node):
    if node is None:
        return None
    if isinstance(node, Condition):
        return {"t": "cond", "column": node.column, "operator": node.operator,
                "value": node.value, "value2": node.value2}
    if isinstance(node, And):
        return {"t": "and", "children": [ast_to_dict(c) for c in node.children]}
    if isinstance(node, Or):
        return {"t": "or", "children": [ast_to_dict(c) for c in node.children]}
    if isinstance(node, Not):
        return {"t": "not", "child": ast_to_dict(node.child)}
    return None


def ast_from_dict(data):
    if data is None:
        return None
    t = data.get("t")
    if t == "cond":
        return Condition(data["column"], data["operator"], data.get("value"), data.get("value2"))
    if t == "and":
        return And([ast_from_dict(c) for c in data["children"]])
    if t == "or":
        return Or([ast_from_dict(c) for c in data["children"]])
    if t == "not":
        return Not(ast_from_dict(data["child"]))
    return None
```

- [ ] **Step 4: Lancer (succès attendu)**

Run: `uv run pytest tests/test_query_ast.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/utils/query_ast.py tests/test_query_ast.py
git add src/utils/query_ast.py tests/test_query_ast.py
git commit -m "feat(query): sort_model_to_sql + sérialisation AST (#41)"
```

---

## Task 5: `fetch_grid_page` (datasource server-side)

Fonction pure qui prend une requête AG Grid infinite et renvoie la page + le total, en réutilisant la couche DuckDB et `postprocess_page`. C'est le cœur du callback `getRows`.

**Files:**

- Create: `src/utils/grid.py`
- Test: `tests/test_grid.py`

**Interfaces:**

- Consumes: `filtermodel_to_ast`, `ast_to_sql`, `sort_model_to_sql` (Task 2-4) ; `query_marches`, `count_marches`, `postprocess_page`.
- Produces: `fetch_grid_page(filter_model, sort_model, start_row, end_row, base_where_sql="TRUE", base_params=()) -> tuple[list[dict], int]` — `(row_data, total_count)`.

- [ ] **Step 1: Écrire le test (utilise `tests/test.parquet` via `src.db`)**

```python
# tests/test_grid.py
from src.utils.grid import fetch_grid_page


def test_fetch_grid_page_returns_rows_and_count():
    rows, total = fetch_grid_page(None, None, 0, 20)
    assert isinstance(rows, list)
    assert isinstance(total, int)
    assert total >= len(rows)
    if rows:
        # postprocess_page ajoute une colonne 'marche' avec un lien
        assert "marche" in rows[0]


def test_fetch_grid_page_filter_reduces_count():
    _, total_all = fetch_grid_page(None, None, 0, 1)
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "zzzzzznope"}}
    rows, total_filtered = fetch_grid_page(fm, None, 0, 20)
    assert total_filtered <= total_all
    assert rows == [] and total_filtered == 0


def test_fetch_grid_page_offset_slicing():
    rows, _ = fetch_grid_page(None, None, 0, 5)
    assert len(rows) <= 5
```

> Note : `tests/test.parquet` est petit et peut ne pas contenir toutes les colonnes ; les tests ci-dessus n'assument que `objet`/`uid`.

- [ ] **Step 2: Lancer (échec attendu)**

Run: `uv run pytest tests/test_grid.py -q`
Expected: FAIL (`src.utils.grid` absent).

- [ ] **Step 3: Implémenter**

```python
# src/utils/grid.py
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
```

- [ ] **Step 4: Lancer (succès attendu)**

Run: `uv run pytest tests/test_grid.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/utils/grid.py tests/test_grid.py
git add src/utils/grid.py tests/test_grid.py
git commit -m "feat(grid): fetch_grid_page datasource server-side AG Grid (#41)"
```

---

## Task 6: `grid_column_defs` + fabrique `ag_grid`

Construit les `columnDefs` (type de filtre par colonne, headerTooltip = définition, cellRenderer markdown pour les liens, colonnes masquées) et la fabrique du composant `dag.AgGrid`.

**Files:**

- Modify: `src/utils/grid.py` (ajout `grid_column_defs`)
- Modify: `src/figures.py` (ajout `ag_grid`)
- Test: `tests/test_grid.py`

**Interfaces:**

- Consumes: `schema`, `DATA_SCHEMA` (`src/figures.py`), `get_default_hidden_columns`.
- Produces:
  - `grid_column_defs(hidden_columns: list[str] | None = None) -> list[dict]`.
  - `ag_grid(grid_id: str, column_defs: list[dict]) -> dag.AgGrid`.

Mapping type de filtre (depuis `schema[col]`) : numérique → `agNumberColumnFilter` ; `pl.Date` → `agDateColumnFilter` ; sinon `agTextColumnFilter`.

- [ ] **Step 1: Écrire le test**

```python
# tests/test_grid.py  (append)
from src.utils.grid import grid_column_defs


def test_column_defs_have_field_and_filter():
    defs = grid_column_defs(hidden_columns=[])
    by_field = {d["field"]: d for d in defs}
    assert "objet" in by_field
    # filtre texte par défaut
    assert by_field["objet"]["filter"] == "agTextColumnFilter"
    # montant est numérique
    assert by_field["montant"]["filter"] == "agNumberColumnFilter"
    # headerTooltip présent (définition de colonne)
    assert "headerTooltip" in by_field["objet"]


def test_column_defs_hidden_flag():
    defs = grid_column_defs(hidden_columns=["objet"])
    by_field = {d["field"]: d for d in defs}
    assert by_field["objet"]["hide"] is True
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `uv run pytest tests/test_grid.py -q -k column_defs`
Expected: FAIL.

- [ ] **Step 3: Implémenter `grid_column_defs`**

```python
# src/utils/grid.py  (append)
import polars as pl

from src.figures import DATA_SCHEMA

_LINK_COLUMNS = {"marche", "uid", "acheteur_id", "acheteur_nom", "titulaire_id", "titulaire_nom", "sourceFile"}


def _filter_for(col_type) -> str:
    if col_type.is_numeric():
        return "agNumberColumnFilter"
    if col_type == pl.Date:
        return "agDateColumnFilter"
    return "agTextColumnFilter"


def grid_column_defs(hidden_columns=None):
    """columnDefs dérivés du schéma DuckDB.

    'marche' (colonne loupe ajoutée par postprocess_page) est placée en tête.
    """
    hidden = set(hidden_columns or [])
    defs = [
        {
            "field": "marche",
            "headerName": "",
            "cellRenderer": "markdown",
            "filter": False,
            "sortable": False,
            "maxWidth": 60,
            "pinned": "left",
        }
    ]
    for col in schema.names():
        meta = DATA_SCHEMA.get(col, {})
        col_type = schema[col]
        col_def = {
            "field": col,
            "headerName": meta.get("title", col),
            "filter": _filter_for(col_type),
            "floatingFilter": True,
            "sortable": True,
            "hide": col in hidden,
        }
        if meta.get("description"):
            col_def["headerTooltip"] = f"{meta.get('title', col)} ({col}) — {meta['description']}"
        if col in _LINK_COLUMNS:
            col_def["cellRenderer"] = "markdown"
        defs.append(col_def)
    return defs
```

- [ ] **Step 4: Lancer (succès attendu)**

Run: `uv run pytest tests/test_grid.py -q`
Expected: PASS.

- [ ] **Step 5: Ajouter la fabrique `ag_grid` dans `figures.py`**

```python
# src/figures.py  (append, en tête ajouter: import dash_ag_grid as dag)

def ag_grid(grid_id: str, column_defs: list[dict]) -> "dag.AgGrid":
    """Grille AG Grid server-side (infinite) pour la page Tableau.

    Apparence de base d'AG Grid (aucun thème custom au Lot 1).
    """
    return dag.AgGrid(
        id=grid_id,
        columnDefs=column_defs,
        defaultColDef={"resizable": True, "minWidth": 120, "floatingFilter": True},
        rowModelType="infinite",
        dangerously_allow_code=True,  # rend le HTML <a> des cellules liens
        dashGridOptions={
            "cacheBlockSize": 100,
            "maxBlocksInCache": 10,
            "rowBuffer": 0,
            "infiniteInitialRowCount": 100,
            "suppressCellFocus": True,
        },
        columnSize="responsiveSizeToFit",
        style={"height": "70vh", "width": "100%"},
        persistence=True,
        persistence_type="local",
        persisted_props=["filterModel", "columnState"],
    )
```

- [ ] **Step 6: Vérifier l'import de la fabrique**

Run: `uv run python -c "from src.figures import ag_grid; from src.utils.grid import grid_column_defs; print(type(ag_grid('t', grid_column_defs([]))).__name__)"`
Expected: `AgGrid`.

- [ ] **Step 7: Commit**

```bash
pre-commit run --files src/utils/grid.py src/figures.py tests/test_grid.py
git add src/utils/grid.py src/figures.py tests/test_grid.py
git commit -m "feat(grid): columnDefs + fabrique ag_grid (#41)"
```

---

## Task 7: Réécrire le layout + le callback `getRows` de `tableau.py`

Remplacer le composant `DATATABLE` (DataTable) par la grille AG Grid, et le callback `update_table` par un callback `getRowsResponse ← getRowsRequest`. Mettre à jour `nb_rows` et le bouton de téléchargement via un `dcc.Store` du dernier total.

**Files:**

- Modify: `src/pages/tableau.py`

**Interfaces:**

- Consumes: `ag_grid`, `grid_column_defs`, `fetch_grid_page`.
- Produces: composant grille `id="tableau_grid"` ; `dcc.Store id="tableau-total"`.

- [ ] **Step 1: Remplacer le composant table**

Dans `src/pages/tableau.py`, remplacer le bloc `DATATABLE = html.Div(... DataTable(...))` (≈ lignes 65-79) par :

```python
from src.figures import make_column_picker, ag_grid  # (remplace l'import DataTable)
from src.utils.grid import fetch_grid_page, grid_column_defs

DATATABLE = html.Div(
    className="marches_table",
    children=ag_grid("tableau_grid", grid_column_defs(get_default_hidden_columns("tableau"))),
)
```

Ajouter `get_default_hidden_columns` à l'import depuis `src.utils.table` (déjà importé) et un store dans `layout` (à côté des autres `dcc.Store`) :

```python
dcc.Store(id="tableau-total"),
```

- [ ] **Step 2: Remplacer le callback `update_table` par le datasource**

Supprimer l'ancien `@callback def update_table(...)` (≈ lignes 436-478) et le remplacer par :

```python
@callback(
    Output("tableau_grid", "getRowsResponse"),
    Output("tableau-total", "data"),
    Input("tableau_grid", "getRowsRequest"),
    prevent_initial_call=True,
)
def get_rows_tableau(request):
    if request is None:
        return no_update, no_update
    filter_model = request.get("filterModel") or None
    sort_model = request.get("sortModel") or None
    if filter_model:
        track_search(json.dumps(filter_model), "tableau")
    rows, total = fetch_grid_page(
        filter_model,
        sort_model,
        request.get("startRow", 0),
        request.get("endRow", 100),
    )
    return {"rowData": rows, "rowCount": total}, total
```

- [ ] **Step 3: Mettre à jour `nb_rows` + bouton téléchargement depuis le total**

Ajouter un callback qui réagit au store `tableau-total` :

```python
@callback(
    Output("nb_rows", "children"),
    Output("btn-download-data", "disabled"),
    Output("download-hint", "children"),
    Input("tableau-total", "data"),
)
def update_meta(total):
    total = total or 0
    too_many = total > 65000
    hint = " · Filtrez sous 65 000 lignes pour activer le téléchargement" if too_many else ""
    return f"{total} lignes", too_many, hint
```

- [ ] **Step 4: Vérifier que la page se charge (smoke test manuel)**

Run: `uv run pytest tests/test_main.py::test_001_logo_and_search -q` (démarre l'app en intégration ; vérifie qu'aucune erreur d'import/callback ne casse le boot).
Expected: PASS. Si échec pour cause d'ID manquant, corriger les références d'ID.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/tableau.py
git add src/pages/tableau.py
git commit -m "feat(tableau): grille AG Grid + datasource getRows server-side (#41)"
```

---

## Task 8: Sélecteur de colonnes → `columnState`/`hide`

Piloter la visibilité des colonnes de la grille depuis le sélecteur existant (`make_column_picker`) via la prop `columnDefs` (ou `columnState`) au lieu de `hidden_columns` de la DataTable.

**Files:**

- Modify: `src/pages/tableau.py`

**Interfaces:**

- Consumes: `grid_column_defs`, `make_column_picker`, `get_default_hidden_columns`, `invert_columns`, `COLUMNS`.

- [ ] **Step 1: Adapter les callbacks colonnes**

Remplacer les callbacks qui écrivaient `Output("tableau_datatable", "hidden_columns")` par un callback qui régénère `columnDefs` :

```python
@callback(
    Output("tableau_grid", "columnDefs"),
    Input("tableau-hidden-columns", "data"),
)
def apply_hidden_columns(hidden_columns):
    if hidden_columns is None:
        hidden_columns = get_default_hidden_columns("tableau")
    return grid_column_defs(hidden_columns)
```

Conserver les callbacks existants qui alimentent `tableau-hidden-columns` depuis les cases à cocher (`update_hidden_columns_from_checkboxes`, `update_checkboxes_from_hidden_columns`) — ils manipulent `COLUMNS`/`selected_rows`, indépendants d'AG Grid. Supprimer `store_hidden_columns` s'il ne cible plus que l'ancienne table.

- [ ] **Step 2: Test intégration du picker**

Run: `uv run pytest tests/test_main.py -q -k tableau` (s'il existe un test tableau ; sinon vérification manuelle décrite en Task 12).
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
pre-commit run --files src/pages/tableau.py
git add src/pages/tableau.py
git commit -m "feat(tableau): sélecteur de colonnes piloté par columnDefs (#41)"
```

---

## Task 9: Export Excel via DuckDB (AST→SQL)

Réécrire `download_data` pour partir du `filterModel`/`sortModel`/`columnState` courants de la grille, compiler en SQL, tirer les lignes de DuckDB et styler l'Excel.

**Files:**

- Modify: `src/pages/tableau.py`
- Modify: `src/utils/grid.py` (ajout `export_dataframe`)
- Test: `tests/test_grid.py`

**Interfaces:**

- Produces: `export_dataframe(filter_model, sort_model, hidden_columns) -> pl.DataFrame` (lignes filtrées/triées, colonnes masquées exclues, **non** post-traitées HTML — valeurs brutes pour l'Excel).

- [ ] **Step 1: Test `export_dataframe`**

```python
# tests/test_grid.py  (append)
from src.utils.grid import export_dataframe


def test_export_dataframe_excludes_hidden_columns():
    df = export_dataframe(None, None, hidden_columns=["objet"])
    assert "objet" not in df.columns


def test_export_dataframe_applies_filter():
    fm = {"objet": {"filterType": "text", "type": "contains", "filter": "zzzzzznope"}}
    df = export_dataframe(fm, None, hidden_columns=[])
    assert df.height == 0
```

- [ ] **Step 2: Lancer (échec attendu)**

Run: `uv run pytest tests/test_grid.py -q -k export`
Expected: FAIL.

- [ ] **Step 3: Implémenter `export_dataframe`**

```python
# src/utils/grid.py  (append)

def export_dataframe(filter_model, sort_model, hidden_columns) -> "pl.DataFrame":
    ast = filtermodel_to_ast(filter_model, schema)
    filter_sql, params = ast_to_sql(ast, schema)
    order_by = sort_model_to_sql(sort_model, schema) or None
    visible = [c for c in schema.names() if c not in set(hidden_columns or [])]
    return query_marches(
        where_sql=filter_sql,
        params=params,
        columns=visible,
        order_by=order_by,
    )
```

- [ ] **Step 4: Réécrire le callback `download_data`**

```python
# src/pages/tableau.py  (remplace download_data)
@callback(
    Output("download-data", "data"),
    Input("btn-download-data", "n_clicks"),
    State("tableau_grid", "filterModel"),
    State("tableau_grid", "columnState"),
    prevent_initial_call=True,
)
def download_data(n_clicks, filter_model, column_state):
    from src.utils.grid import export_dataframe
    sort_model = [
        {"colId": c["colId"], "sort": c["sort"]}
        for c in (column_state or []) if c.get("sort")
    ]
    hidden_columns = [c["colId"] for c in (column_state or []) if c.get("hide")]
    df = export_dataframe(filter_model, sort_model, hidden_columns)

    def to_bytes(buffer):
        write_styled_excel(df, buffer)

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.xlsx")
```

> `columnState` porte à la fois le tri (`sort`/`sortIndex`) et la visibilité (`hide`) : une seule `State` suffit pour les deux.

- [ ] **Step 5: Lancer les tests**

Run: `uv run pytest tests/test_grid.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/utils/grid.py src/pages/tableau.py tests/test_grid.py
git add src/utils/grid.py src/pages/tableau.py tests/test_grid.py
git commit -m "feat(tableau): export Excel via DuckDB (AST->SQL) (#41)"
```

---

## Task 10: Vues sauvegardées (AST + columnState) et retrait de l'URL riche

Les vues stockent désormais un JSON `{filterModel, columnState}` dans la colonne `query`. Le rappel applique `filterModel` + `columnState` à la grille. Retirer `restore_view_from_url`, `sync_url_and_reset_button`, le bouton « Partager la vue » et le clientside `clean_filters` de `tableau.py`.

**Files:**

- Modify: `src/pages/tableau.py`
- Modify: `src/saved_views/ui.py` si `prepare_view_to_save` référence l'ancien format (sinon inchangé).

- [ ] **Step 1: Sauvegarde de vue au nouveau format**

Réécrire `save_view` pour stocker le JSON de la vue :

```python
@callback(
    Output("save-view-modal", "is_open", allow_duplicate=True),
    Output("save-view-feedback", "children"),
    Output("saved-views-refresh", "data"),
    Input("btn-save-view-confirm", "n_clicks"),
    State("save-view-name", "value"),
    State("tableau_grid", "filterModel"),
    State("tableau_grid", "columnState"),
    prevent_initial_call=True,
)
def save_view(_n, name, filter_model, column_state):
    has_sub = current_user_has_subscription()
    clean_name, error = saved_views_ui.prepare_view_to_save(has_sub, name)
    if error:
        return True, html.Span(error, style={"color": "red"}), no_update
    query = json.dumps({"filterModel": filter_model or {}, "columnState": column_state or []})
    saved_views_db.upsert(current_user.id, "tableau", clean_name, query)
    return (
        False,
        html.Span(f"Vue « {clean_name} » enregistrée.", style={"color": "green"}),
        clean_name,
    )
```

- [ ] **Step 2: Rappel d'une vue → applique filterModel + columnState**

Remplacer `restore_view_from_url` par un callback déclenché par la sélection dans le menu « Mes vues » (le menu `saved-views-menu` produit des items ; réutiliser leur `id`/`value` existant). Exemple de callback de rappel :

```python
@callback(
    Output("tableau_grid", "filterModel"),
    Output("tableau_grid", "columnState"),
    Input({"type": "saved-view-item", "index": ALL}, "n_clicks"),
    State({"type": "saved-view-item", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def apply_saved_view(n_clicks, ids):
    triggered = ctx.triggered_id
    if not triggered or not any(n_clicks):
        return no_update, no_update
    row = saved_views_db.get(triggered["index"], current_user.id)
    if not row:
        return no_update, no_update
    view = json.loads(row["query"])
    return view.get("filterModel") or {}, view.get("columnState") or []
```

> Adapter les `id`/pattern-matching au format réel produit par `saved_views_ui.saved_views_items` (lire `src/saved_views/ui.py`). Importer `ctx`, `ALL` depuis `dash`.

- [ ] **Step 3: Retirer l'URL riche et le clientside**

Supprimer de `tableau.py` :

- le callback `restore_view_from_url` (bloc `?filtres/tris/colonnes`),
- le callback `sync_url_and_reset_button` et le composant `dcc.Clipboard`/bouton « Partager la vue » (`copy-container`, `share-url`),
- `show_confirmation`,
- le `clientside_callback` `clean_filters` (Output `filter-cleanup-trigger-tableau`) et le `dcc.Store(id="filter-cleanup-trigger-tableau")`,
- l'`Output(..., "filter-cleanup-trigger-tableau", ...)` résiduel.

Adapter le bouton **Réinitialiser** :

```python
@callback(
    Output("tableau_grid", "filterModel", allow_duplicate=True),
    Input("btn-tableau-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_view(n_clicks):
    return {}
```

- [ ] **Step 4: Smoke test app**

Run: `uv run pytest tests/test_main.py::test_001_logo_and_search -q`
Expected: PASS (aucun ID orphelin, pas de callback cassé).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/tableau.py src/saved_views/ui.py
git add src/pages/tableau.py src/saved_views/ui.py
git commit -m "feat(tableau): vues sauvegardées en JSON AST, retrait URL riche (#41)"
```

---

## Task 11: Mode d'emploi + nettoyage

Réécrire l'aide (`dcc.Markdown`) pour décrire les filtres de colonne AG Grid ; retirer les exemples d'URL riche codés en dur et la légende des boutons devenus obsolètes.

**Files:**

- Modify: `src/pages/tableau.py`

- [ ] **Step 1: Réécrire le corps du mode d'emploi**

Dans le `dcc.Markdown` du modal `tableau_help`, remplacer les sections « Appliquer des filtres » (syntaxe DSL `icontains`), « Partager une vue » et l'intro avec les deux liens `?filtres=…` par une description des **filtres de colonne** AG Grid : cliquer sur l'icône filtre / saisir dans le champ flottant sous l'en-tête, opérateurs contient/égal/commence par, filtres numériques `<`/`>`/plage, tri par clic d'en-tête, sélecteur de colonnes, scroll infini, export Excel. Retirer les deux liens d'exemple du `dcc.Markdown` d'intro (≈ ligne 204).

- [ ] **Step 2: Mettre à jour `_help_button_legend`**

Retirer la ligne « Partager la vue » de `_help_button_legend()` (le bouton a été supprimé).

- [ ] **Step 3: Vérifier l'absence de références mortes**

Run: `uv run python -c "import src.pages.tableau; print('ok')"`
Expected: `ok`.
Run: `rg -n "filter_query|hidden_columns|tableau_datatable|clean_filters|Partager" src/pages/tableau.py`
Expected: aucune occurrence résiduelle liée à l'ancienne table.

- [ ] **Step 4: Commit**

```bash
pre-commit run --files src/pages/tableau.py
git add src/pages/tableau.py
git commit -m "docs(tableau): mode d'emploi réécrit pour AG Grid (#41)"
```

---

## Task 12: Test d'intégration end-to-end + suite complète

Valider le parcours complet via DashComposite/Selenium, puis lancer toute la suite.

**Files:**

- Create: `tests/test_tableau_ag_grid.py`

- [ ] **Step 1: Écrire le test d'intégration**

```python
# tests/test_tableau_ag_grid.py
from src.app import app


def test_tableau_grid_loads_and_filters(dash_duo):
    dash_duo.start_server(app)
    dash_duo.wait_for_page("http://localhost:{}/tableau".format(dash_duo.server_port))
    # La grille AG Grid est présente
    dash_duo.wait_for_element(".ag-root", timeout=8)
    # Au moins une ligne rendue (row) après chargement du premier bloc
    dash_duo.wait_for_element(".ag-center-cols-container .ag-row", timeout=8)
    assert dash_duo.get_logs() == [] or all(
        "SEVERE" not in log["level"] for log in dash_duo.get_logs()
    )
```

> Ajuster les sélecteurs si besoin (`.ag-root-wrapper`, `.ag-header-cell`). Ces tests nécessitent Chromium (cf. CLAUDE.md).

- [ ] **Step 2: Lancer le test d'intégration**

Run: `uv run pytest tests/test_tableau_ag_grid.py -q`
Expected: PASS.

- [ ] **Step 3: Vérification manuelle (drive de l'app)**

Utiliser la compétence `run` / `verify` pour lancer l'app (`uv run run.py`) et vérifier sur `/tableau` : chargement de la grille, en-têtes figés au scroll, filtre de colonne (texte `voirie`, numérique `> 40000`), tri par clic d'en-tête, scroll infini (nouveau bloc chargé), sélecteur de colonnes, export Excel (fichier téléchargé cohérent avec les filtres), persistance après refresh, sauvegarde + rappel d'une vue (compte abonné).

- [ ] **Step 4: Lancer la suite complète**

Run: `uv run pytest`
Expected: PASS (aucune régression sur les autres pages, qui utilisent encore la `DataTable`).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files tests/test_tableau_ag_grid.py
git add tests/test_tableau_ag_grid.py
git commit -m "test(tableau): intégration AG Grid end-to-end (#41)"
```

---

## Verification (récapitulatif)

- `uv run pytest tests/test_query_ast.py tests/test_grid.py -q` — moteur de requête + datasource.
- `uv run pytest tests/test_tableau_ag_grid.py -q` — intégration grille.
- `uv run pytest` — non-régression globale (dernière tâche uniquement).
- Drive manuel de `/tableau` (compétence `run`/`verify`) pour l'UX scroll infini, filtres, tri, colonnes, export, persistance, vues sauvegardées.

## Notes de mise en œuvre

- **Colonnes masquées par défaut** : `get_default_hidden_columns("tableau")` lit l'env `DISPLAYED_COLUMNS` ; conserver ce comportement.
- **`track_search`** : on logue désormais le `filterModel` JSON (au lieu du DSL) ; format différent mais même intention.
- **Post-traitement HTML** : `postprocess_page` caste tout en `String` et injecte des `<a>` — parfait pour `cellRenderer: "markdown"` + `dangerously_allow_code=True`. L'export, lui, part des valeurs brutes DuckDB (pas de post-traitement HTML).
- **Ne pas** supprimer `filter_query_to_sql`, `clean_filters`, la classe `DataTable` : encore utilisés par les pages non migrées (Lots 2/3).
