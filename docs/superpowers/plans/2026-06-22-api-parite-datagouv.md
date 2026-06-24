# Parité API decp.info / tabular-api — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atteindre la parité de l'API `/api/v1/data` de decp.info avec `tabular-api` (data.gouv.fr) sur les opérateurs manquants, et documenter chaque mot-clé dans le Swagger UI.

**Architecture:** Le parsing des filtres reste dans `src/api/filters.py` (`build_where`). On y ajoute l'opérateur `differs` et une nouvelle fonction `parse_aggregators` qui détecte les drapeaux d'agrégation et produit des fragments SQL. `src/db.py` gagne `aggregate_marches`. `src/api/routes.py` oriente vers le chemin agrégation ou le chemin normal, renomme le param réservé `count`→`count_results`, et documente les opérateurs.

**Tech Stack:** Flask + flask-smorest, DuckDB, Polars, pytest.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `src.api.filters`).
- Valeurs de filtre liées par paramètres `?` (jamais interpolées). Noms de colonnes validés contre `schema` avant interpolation.
- Spec de référence : `docs/superpowers/specs/2026-06-22-api-parite-datagouv-design.md`.
- Périmètre : `count_results`, `differs`, agrégation (`groupby`/`count`/`sum`/`avg`/`min`/`max`), doc. **Hors périmètre : `or`.**
- Lancer les tests via `rtk pytest` ; l'environnement de test définit `DEVELOPMENT=true` et `DATA_FILE_PARQUET_PATH=tests/test.parquet`.
- `tests/test.parquet` contient notamment les colonnes : `uid`, `montant` (Int64), `acheteur_departement_code`, `objet`, `dateNotification` (Date).

---

### Task 1 : Renommer le param réservé `count` → `count_results`

**Files:**

- Modify: `src/api/filters.py` (constante `RESERVED_PARAMS`)
- Modify: `src/api/routes.py` (lecture du param + doc swagger)
- Test: `tests/api/test_filters.py`, `tests/api/test_endpoints_data.py`

**Interfaces:**

- Consumes: rien.
- Produces: le param réservé s'appelle désormais `count_results` ; `count` n'est plus réservé (libéré pour l'agrégation en Task 3).

- [ ] **Step 1 : Mettre à jour les tests existants**

Dans `tests/api/test_filters.py`, remplacer `("count", "false")` par `("count_results", "false")` dans `test_reserved_params_are_ignored` :

```python
def test_reserved_params_are_ignored():
    where, params, order = build_where(
        [
            ("page", "2"),
            ("page_size", "100"),
            ("columns", "uid"),
            ("count_results", "false"),
            ("uid__exact", "z"),
        ],
        SCHEMA,
    )
    assert where == '"uid" = ?'
    assert params == ["z"]
```

Dans `tests/api/test_endpoints_data.py`, renommer le test et l'URL :

```python
def test_data_count_results_false_omits_total(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?count_results=false", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "total" not in body["meta"]
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `rtk pytest tests/api/test_endpoints_data.py::test_data_count_results_false_omits_total tests/api/test_filters.py::test_reserved_params_are_ignored -v`
Expected: FAIL (`count_results` encore traité comme filtre inconnu → 400 / `FilterError`).

- [ ] **Step 3 : Modifier `RESERVED_PARAMS`**

Dans `src/api/filters.py` :

```python
RESERVED_PARAMS = {"page", "page_size", "columns", "count_results"}
```

- [ ] **Step 4 : Modifier la lecture dans la route**

Dans `src/api/routes.py`, fonction `data()`, remplacer :

```python
    count = request.args.get("count", "true").lower() != "false"
```

par :

```python
    count_results = request.args.get("count_results", "true").lower() != "false"
```

et plus bas remplacer `if count else None` par `if count_results else None`.

- [ ] **Step 5 : Mettre à jour la doc swagger du param**

Dans `src/api/routes.py`, dans `@bp.doc(parameters=[...])`, remplacer le bloc du paramètre `count` par :

```python
        {
            "name": "count_results",
            "in": "query",
            "schema": {"type": "string", "enum": ["true", "false"], "default": "true"},
            "description": "Inclure le total (`COUNT(*)`) dans `meta`. Mettre `false` pour accélérer la requête. Ignoré en mode agrégation.",
        },
```

Et dans le docstring de `data()`, remplacer la mention `count (true|false ...)` par `count_results (true|false ; mettre false pour économiser le COUNT(*))`.

- [ ] **Step 6 : Lancer les tests, vérifier le succès**

Run: `rtk pytest tests/api/test_endpoints_data.py tests/api/test_filters.py -v`
Expected: PASS (tous).

- [ ] **Step 7 : Commit**

```bash
git add src/api/filters.py src/api/routes.py tests/api/test_filters.py tests/api/test_endpoints_data.py
git commit -m "feat(api): renomme le param réservé count en count_results (#78)"
```

---

### Task 2 : Opérateur de filtre `differs`

**Files:**

- Modify: `src/api/filters.py` (`OPERATORS`, `build_where`)
- Test: `tests/api/test_filters.py`, `tests/api/test_endpoints_data.py`

**Interfaces:**

- Consumes: `build_where(args, schema) -> (where_sql, params, order_sql)` (existant).
- Produces: `col__differs=val` → fragment SQL `"col" IS DISTINCT FROM ?`.

- [ ] **Step 1 : Écrire les tests unitaires (échec attendu)**

Dans `tests/api/test_filters.py` :

```python
def test_differs_filter():
    where, params, _ = build_where([("uid__differs", "abc")], SCHEMA)
    assert where == '"uid" IS DISTINCT FROM ?'
    assert params == ["abc"]


def test_differs_filter_on_int():
    where, params, _ = build_where([("annee__differs", "2020")], SCHEMA)
    assert where == '"annee" IS DISTINCT FROM ?'
    assert params == [2020]
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `rtk pytest tests/api/test_filters.py::test_differs_filter tests/api/test_filters.py::test_differs_filter_on_int -v`
Expected: FAIL (`FilterError: Opérateur inconnu : __differs`).

- [ ] **Step 3 : Ajouter `differs` à `OPERATORS`**

Dans `src/api/filters.py`, ajouter `"differs",` dans le set `OPERATORS` (après `"notcontains",`).

- [ ] **Step 4 : Ajouter la branche dans `build_where`**

Dans `src/api/filters.py`, dans `build_where`, après le bloc `elif op == "notcontains":` (lignes ~132-134), ajouter :

```python
        elif op == "differs":
            where_parts.append(f'"{col}" IS DISTINCT FROM ?')
            params.append(v)
```

- [ ] **Step 5 : Lancer les tests unitaires, vérifier le succès**

Run: `rtk pytest tests/api/test_filters.py -k differs -v`
Expected: PASS.

- [ ] **Step 6 : Ajouter un test d'endpoint**

Dans `tests/api/test_endpoints_data.py` :

```python
def test_data_differs_excludes_value(api_client, valid_token_header):
    client, _ = api_client
    base = client.get("/api/v1/data?page_size=1", headers=valid_token_header).get_json()
    uid = base["data"][0]["uid"]
    resp = client.get(f"/api/v1/data?uid__differs={uid}", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert all(row["uid"] != uid for row in body["data"])
```

- [ ] **Step 7 : Lancer, vérifier le succès**

Run: `rtk pytest tests/api/test_endpoints_data.py::test_data_differs_excludes_value -v`
Expected: PASS.

- [ ] **Step 8 : Commit**

```bash
git add src/api/filters.py tests/api/test_filters.py tests/api/test_endpoints_data.py
git commit -m "feat(api): ajoute l'opérateur de filtre differs (IS DISTINCT FROM) (#78)"
```

---

### Task 3 : Parsing des agrégateurs (`parse_aggregators`)

**Files:**

- Modify: `src/api/filters.py` (constantes `AGGREGATORS`/`AGG_SQL`, dataclass `AggregationSpec`, fonction `parse_aggregators`, skip dans `build_where`)
- Test: `tests/api/test_filters.py`

**Interfaces:**

- Consumes: `_split_key`, `FilterError` (existants).
- Produces:

  - `AGGREGATORS: set[str]` = `{"groupby","count","sum","avg","min","max"}`.
  - `@dataclass class AggregationSpec: select_sql: str; group_by_sql: str | None`.
  - `parse_aggregators(args: list[tuple[str,str]], schema: pl.Schema) -> AggregationSpec | None` — `None` si aucun agrégateur.
  - `build_where` ignore désormais les clés dont l'opérateur ∈ `AGGREGATORS`.

- [ ] **Step 1 : Écrire les tests unitaires (échec attendu)**

Dans `tests/api/test_filters.py`, ajouter l'import et les tests :

```python
from src.api.filters import AggregationSpec, parse_aggregators


def test_parse_aggregators_none_when_absent():
    assert parse_aggregators([("uid__exact", "a")], SCHEMA) is None


def test_parse_aggregators_groupby_and_count():
    spec = parse_aggregators(
        [("annee__groupby", ""), ("uid__count", "")], SCHEMA
    )
    assert isinstance(spec, AggregationSpec)
    assert spec.select_sql == '"annee", COUNT("uid") AS "uid__count"'
    assert spec.group_by_sql == '"annee"'


def test_parse_aggregators_multiple_aggregates():
    spec = parse_aggregators(
        [
            ("annee__groupby", ""),
            ("montant__sum", ""),
            ("montant__avg", ""),
            ("montant__min", ""),
            ("montant__max", ""),
        ],
        SCHEMA,
    )
    assert spec.select_sql == (
        '"annee", SUM("montant") AS "montant__sum", '
        'AVG("montant") AS "montant__avg", '
        'MIN("montant") AS "montant__min", '
        'MAX("montant") AS "montant__max"'
    )
    assert spec.group_by_sql == '"annee"'


def test_parse_aggregators_global_without_groupby():
    spec = parse_aggregators([("uid__count", "")], SCHEMA)
    assert spec.select_sql == 'COUNT("uid") AS "uid__count"'
    assert spec.group_by_sql is None


def test_parse_aggregators_unknown_column_raises():
    with pytest.raises(FilterError):
        parse_aggregators([("nope__count", "")], SCHEMA)


def test_build_where_ignores_aggregator_flags():
    where, params, _ = build_where(
        [("annee__groupby", ""), ("uid__count", ""), ("montant__greater", "100")],
        SCHEMA,
    )
    assert where == '"montant" >= ?'
    assert params == [100.0]
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `rtk pytest tests/api/test_filters.py -k aggregator -v`
Expected: FAIL (`ImportError: cannot import name 'parse_aggregators'`).

- [ ] **Step 3 : Ajouter constantes + dataclass + fonction**

Dans `src/api/filters.py`, ajouter en haut l'import `from dataclasses import dataclass` (après les imports existants), puis après `RESERVED_PARAMS` :

```python
AGGREGATORS = {"groupby", "count", "sum", "avg", "min", "max"}
AGG_SQL = {"count": "COUNT", "sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX"}


@dataclass
class AggregationSpec:
    select_sql: str
    group_by_sql: str | None


def parse_aggregators(
    args: list[tuple[str, str]], schema: pl.Schema
) -> AggregationSpec | None:
    """Détecte les drapeaux d'agrégation (`col__groupby`, `col__count`, ...).

    Retourne None si aucun agrégateur. Sinon, construit les fragments SQL
    `select_sql` et `group_by_sql` (noms de colonnes validés contre le schéma).
    """
    group_cols: list[str] = []
    aggregates: list[tuple[str, str]] = []  # (operator, column)
    has_agg = False

    for key, _ in args:
        parsed = _split_key(key)
        if not parsed:
            continue
        col, op = parsed
        if op not in AGGREGATORS:
            continue
        has_agg = True
        if col not in schema:
            raise FilterError(f"Colonne inconnue : {col!r}", field=key)
        if op == "groupby":
            group_cols.append(col)
        else:
            aggregates.append((op, col))

    if not has_agg:
        return None

    select_parts = [f'"{c}"' for c in group_cols]
    for op, col in aggregates:
        select_parts.append(f'{AGG_SQL[op]}("{col}") AS "{col}__{op}"')

    group_by_sql = ", ".join(f'"{c}"' for c in group_cols) if group_cols else None
    return AggregationSpec(select_sql=", ".join(select_parts), group_by_sql=group_by_sql)
```

- [ ] **Step 4 : Faire ignorer les drapeaux d'agrégation par `build_where`**

Dans `src/api/filters.py`, dans `build_where`, juste après `col, op = parsed` (et avant `if op not in OPERATORS:`), ajouter :

```python
        if op in AGGREGATORS:
            continue
```

- [ ] **Step 5 : Lancer les tests, vérifier le succès**

Run: `rtk pytest tests/api/test_filters.py -v`
Expected: PASS (tous, anciens et nouveaux).

- [ ] **Step 6 : Commit**

```bash
git add src/api/filters.py tests/api/test_filters.py
git commit -m "feat(api): parsing des opérateurs d'agrégation (groupby/count/sum/avg/min/max) (#78)"
```

---

### Task 4 : `aggregate_marches` dans la couche DB

**Files:**

- Modify: `src/db.py` (nouvelle fonction `aggregate_marches`)
- Test: `tests/api/test_db_aggregate.py` (créer)

**Interfaces:**

- Consumes: `get_cursor()`, `logger` (existants dans `src/db.py`).
- Produces: `aggregate_marches(select_sql: str, where_sql: str = "TRUE", params: tuple | list = (), group_by: str | None = None, limit: int | None = None, offset: int | None = None) -> pl.DataFrame`.

- [ ] **Step 1 : Écrire le test (échec attendu)**

Créer `tests/api/test_db_aggregate.py` :

```python
import polars as pl

from src.db import aggregate_marches


def test_aggregate_groupby_count_returns_named_columns():
    df = aggregate_marches(
        select_sql='"acheteur_departement_code", COUNT("uid") AS "uid__count"',
        group_by='"acheteur_departement_code"',
    )
    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["acheteur_departement_code", "uid__count"]
    assert df["uid__count"].sum() > 0


def test_aggregate_global_without_groupby_returns_one_row():
    df = aggregate_marches(select_sql='COUNT("uid") AS "uid__count"')
    assert df.height == 1
    assert df["uid__count"][0] > 0
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `rtk pytest tests/api/test_db_aggregate.py -v`
Expected: FAIL (`ImportError: cannot import name 'aggregate_marches'`).

- [ ] **Step 3 : Implémenter `aggregate_marches`**

Dans `src/db.py`, après `count_marches` (vers la ligne 186), ajouter :

```python
def aggregate_marches(
    select_sql: str,
    where_sql: str = "TRUE",
    params: tuple | list = (),
    group_by: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> pl.DataFrame:
    """SELECT agrégé paramétré contre la table decp.

    `select_sql` et `group_by` sont des fragments SQL construits depuis des
    noms de colonnes validés (jamais de valeur utilisateur libre). Les
    valeurs de filtre passent par le binding `?` via `params`.
    """
    sql = f"SELECT {select_sql} FROM decp WHERE {where_sql}"
    if group_by:
        sql += f" GROUP BY {group_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"

    logger.debug("aggregate_marches: " + sql.replace("?", "{}").format(*params))

    return get_cursor().execute(sql, list(params)).pl()
```

- [ ] **Step 4 : Lancer, vérifier le succès**

Run: `rtk pytest tests/api/test_db_aggregate.py -v`
Expected: PASS.

- [ ] **Step 5 : Commit**

```bash
git add src/db.py tests/api/test_db_aggregate.py
git commit -m "feat(db): aggregate_marches pour les requêtes GROUP BY (#78)"
```

---

### Task 5 : Orchestration du mode agrégation dans la route

**Files:**

- Modify: `src/api/routes.py` (fonction `data()`)
- Test: `tests/api/test_endpoints_data.py`

**Interfaces:**

- Consumes: `parse_aggregators` (Task 3), `aggregate_marches` (Task 4), `build_where` (existant), `AggregationSpec`.
- Produces: l'endpoint `/api/v1/data` renvoie des lignes agrégées quand un opérateur d'agrégation est présent ; `meta` sans `total` ; `columns` + agrégation → 400.

- [ ] **Step 1 : Écrire les tests d'endpoint (échec attendu)**

Dans `tests/api/test_endpoints_data.py` :

```python
def test_data_aggregation_groupby_count(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?acheteur_departement_code__groupby&uid__count",
        headers=valid_token_header,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["data"], "agrégation vide ?"
    for row in body["data"]:
        assert set(row.keys()) == {"acheteur_departement_code", "uid__count"}
    assert "total" not in body["meta"]


def test_data_aggregation_global_count(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?uid__count", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["data"]) == 1
    assert "uid__count" in body["data"][0]


def test_data_aggregation_with_filter(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?acheteur_departement_code__groupby&uid__count&montant__greater=0",
        headers=valid_token_header,
    )
    assert resp.status_code == 200


def test_data_aggregation_with_columns_returns_400(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?uid__count&columns=uid",
        headers=valid_token_header,
    )
    assert resp.status_code == 400
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `rtk pytest tests/api/test_endpoints_data.py -k aggregation -v`
Expected: FAIL (les drapeaux d'agrégation sont ignorés → réponse non agrégée, clés inattendues / pas de 400).

- [ ] **Step 3 : Mettre à jour les imports de la route**

Dans `src/api/routes.py`, remplacer la ligne d'import des filtres :

```python
from src.api.filters import FilterError, build_where
```

par :

```python
from src.api.filters import FilterError, build_where, parse_aggregators
from src.db import aggregate_marches
```

(et conserver l'import existant `from src.db import count_marches, query_marches`).

- [ ] **Step 4 : Brancher le chemin agrégation dans `data()`**

Dans `src/api/routes.py`, fonction `data()`, remplacer le bloc qui va de `try:` (parsing `build_where`) jusqu'au `return {...}` final par :

```python
    args = list(request.args.items(multi=True))
    try:
        agg = parse_aggregators(args, duckdb_schema)
        where_sql, params, order_sql = build_where(args, duckdb_schema)
    except FilterError as e:
        abort(400, message=str(e), errors={"field": e.field})

    if agg is not None:
        if columns:
            abort(
                400,
                message="`columns` ne peut pas être combiné avec une agrégation",
            )
        df = aggregate_marches(
            select_sql=agg.select_sql,
            where_sql=where_sql,
            params=params,
            group_by=agg.group_by_sql,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        df_ready = df.with_columns(cs.temporal().cast(pl.String))
        return {
            "data": df_ready.to_dicts(),
            "meta": {"page": page, "page_size": page_size},
            "links": _build_links(page, page_size, None),
        }

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

    total = count_marches(where_sql, params) if count_results else None
    meta = {"page": page, "page_size": page_size}
    if total is not None:
        meta["total"] = total

    return {
        "data": df_ready.to_dicts(),
        "meta": meta,
        "links": _build_links(page, page_size, total),
    }
```

(Note : `count_results` provient de la Task 1 ; `columns`, `page`, `page_size` sont déjà calculés plus haut dans la fonction.)

- [ ] **Step 5 : Lancer les tests d'endpoint, vérifier le succès**

Run: `rtk pytest tests/api/test_endpoints_data.py -v`
Expected: PASS (tous).

- [ ] **Step 6 : Commit**

```bash
git add src/api/routes.py tests/api/test_endpoints_data.py
git commit -m "feat(api): mode agrégation sur /data (groupby + agrégats) (#78)"
```

---

### Task 6 : Documentation Swagger des mots-clés

**Files:**

- Modify: `src/api/routes.py` (bloc `@bp.doc` du param dynamique + docstring de `data()`)
- Test: `tests/api/test_openapi_doc.py` (créer)

**Interfaces:**

- Consumes: l'OpenAPI généré, servi sur `/api/v1/openapi.json`.
- Produces: la description du paramètre `<colonne>__<opérateur>` liste tous les opérateurs (filtres + agrégation) avec une définition d'une ligne chacun, et décrit le mode agrégation.

- [ ] **Step 1 : Écrire le test (échec attendu)**

Créer `tests/api/test_openapi_doc.py` :

```python
def test_openapi_documents_new_keywords(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    raw = resp.get_data(as_text=True)
    for keyword in ["count_results", "differs", "groupby", "__sum", "__avg", "__min", "__max"]:
        assert keyword in raw, f"{keyword} absent de la doc OpenAPI"
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `rtk pytest tests/api/test_openapi_doc.py -v`
Expected: FAIL (`differs`, `groupby`, etc. absents de la description).

- [ ] **Step 3 : Étoffer la description du paramètre dynamique**

Dans `src/api/routes.py`, remplacer la `description` du paramètre `<colonne>__<opérateur>` par :

```python
            "description": (
                "Filtre ou agrégation dynamique : `<colonne>__<opérateur>` "
                "(voir les colonnes via `/schema`).\n\n"
                "**Filtres** (`<colonne>__<op>=<valeur>`) :\n"
                "- `exact` : égal à la valeur\n"
                "- `differs` : différent de la valeur (null-safe, `IS DISTINCT FROM`)\n"
                "- `contains` / `notcontains` : contient / ne contient pas (LIKE)\n"
                "- `in` / `notin` : dans / hors d'une liste séparée par des virgules\n"
                "- `less` / `greater` : ≤ / ≥\n"
                "- `strictly_less` / `strictly_greater` : < / >\n"
                "- `isnull` / `isnotnull` : valeur nulle / non nulle (sans valeur)\n"
                "- `sort` : tri, valeur `asc` ou `desc`\n\n"
                "**Agrégation** (drapeaux sans valeur, ex. `acheteur_departement_code__groupby&montant__sum`) :\n"
                "- `groupby` : regroupe sur la colonne\n"
                "- `count`, `sum`, `avg`, `min`, `max` : agrège la colonne ; "
                "la colonne de sortie est nommée `colonne__count`, `colonne__sum`, "
                "`colonne__avg`, `colonne__min`, `colonne__max`\n\n"
                "En mode agrégation, la réponse contient des lignes groupées, "
                "`columns` est interdit et `meta` ne contient pas `total`.\n\n"
                "Exemples : `acheteur_id__contains=VILLE`, `montant__greater=10000`, "
                "`acheteur_departement_code__groupby&montant__sum`."
            ),
```

- [ ] **Step 4 : Mettre à jour le docstring de `data()`**

Dans `src/api/routes.py`, remplacer le docstring de `data()` par :

```python
    """Récupère des marchés publics filtrés, triés ou agrégés.

    Filtres en query string : `<colonne>__<opérateur>=<valeur>`.
    Opérateurs de filtre : exact, differs, contains, notcontains, in, notin,
    less, greater, strictly_less, strictly_greater, isnull, isnotnull, sort.

    Agrégation (drapeaux sans valeur) : `<colonne>__groupby`,
    `<colonne>__count|sum|avg|min|max`. Les colonnes agrégées sont nommées
    `<colonne>__<opérateur>`. `columns` est interdit avec une agrégation et
    `meta` ne contient alors pas `total`.

    Paramètres réservés : page (défaut 1), page_size (défaut 50, max 1000),
    columns (csv), count_results (true|false ; mettre false pour économiser
    le COUNT(*)).

    Exemple d'agrégation :
    `?acheteur_departement_code__groupby&uid__count&montant__sum`
    """
```

- [ ] **Step 5 : Lancer, vérifier le succès**

Run: `rtk pytest tests/api/test_openapi_doc.py -v`
Expected: PASS.

- [ ] **Step 6 : Vérifier la non-régression complète de l'API**

Run: `rtk pytest tests/api/ -v`
Expected: PASS (tous).

- [ ] **Step 7 : Commit**

```bash
git add src/api/routes.py tests/api/test_openapi_doc.py
git commit -m "docs(api): documente les opérateurs (filtres + agrégation) dans Swagger (#78)"
```

---

## Notes de vérification de référence (manuel, hors tests automatisés)

Après implémentation, vérifier que quelques requêtes d'agrégation renvoient
des valeurs cohérentes avec data.gouv.fr sur la même ressource DECP
(`22847056-61df-452d-837d-8b8ceadbfc52`), aux différences de fraîcheur près :

```
GET /api/v1/data?acheteur_departement_code__groupby&uid__count&montant__sum
```

à comparer à :

```
https://tabular-api.data.gouv.fr/api/resources/22847056-61df-452d-837d-8b8ceadbfc52/data/?acheteur_departement_code__groupby&uid__count&montant__sum
```
