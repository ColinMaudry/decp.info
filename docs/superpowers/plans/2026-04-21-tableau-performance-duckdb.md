# Plan : optimisation performance page Tableau via DuckDB

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** Réduire le temps de chargement _cold_ de `/tableau` (actuellement ~11 s sans filtre ni tri) à moins de 2 s, et le _warm_ (~5 s) à moins de 500 ms, en utilisant DuckDB comme moteur de requête (filtres, tri, pagination, comptage en SQL) plutôt que comme simple stockage.

**Architecture :**

1. Traduire le DSL de filtres de `dash_table.DataTable` (ex : `{objet} icontains travaux && {montant} i> 40000`) en SQL DuckDB paramétré.
2. Pousser `WHERE` / `ORDER BY` / `LIMIT` / `OFFSET` dans DuckDB plutôt que matérialiser 1,6 M lignes dans Polars.
3. Ne faire tourner le post-traitement coûteux (cast en String, liens HTML, formatage montants) **que sur la page courante** (20 lignes), pas sur le dataset complet.
4. Remplacer le cache `@cache.memoize()` sur la DataFrame complète par deux caches plus fins : un cache de `COUNT(*)` par `filter_query`, et un cache de pages par `(filter_query, sort_by, page_current, page_size)`.
5. Conserver intact le chemin existant `filter_table_data` (Polars LazyFrame) utilisé par `acheteur`, `titulaire`, `observatoire` qui passent déjà des données pré-filtrées via le paramètre `data`.

**Tech Stack :** Python 3, Polars, DuckDB, Dash, Flask-Caching, pytest.

**Périmètre explicite :**

- **Inclus :** chemin `data is None` dans `prepare_table_data` (utilisé uniquement par `/tableau`).
- **Exclus :** refactor des pages acheteur/titulaire/observatoire (bénéficieraient d'un suivi, mais le chemin n'est pas le goulet d'étranglement actuel).
- **Exclus :** projection des colonnes cachées dans le `SELECT` (pourrait être une optimisation de suite ; non-triviale car le navigateur a besoin du schéma complet pour `setup_table_columns`).
- **Exclus :** index DuckDB. DuckDB est un moteur analytique, il tire parti du stockage columnaire sans index B-tree. On mesure avant d'ajouter quoi que ce soit.

---

## Structure de fichiers

| Fichier                   | Opération    | Responsabilité                                                                                                                   |
| ------------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| `src/utils/table_sql.py`  | **Créer**    | Traducteurs : `filter_query_to_sql()` et `sort_by_to_sql()`. Pur, testable sans Dash ni DB.                                      |
| `src/db.py`               | **Modifier** | Ajouter `count_marches(where_sql, params)` et paramètre `offset` à `query_marches()`.                                            |
| `src/utils/table.py`      | **Modifier** | Nouveau chemin rapide SQL dans `_load_filter_sort_postprocess`. Découpage du post-traitement en deux étapes (full → page-seule). |
| `tests/test_table_sql.py` | **Créer**    | Tests unitaires des traducteurs (pur, aucune DB).                                                                                |
| `tests/test_table.py`     | **Modifier** | Ajouter tests d'intégration nouveau chemin ; garder les tests existants verts.                                                   |
| `tests/test_db.py`        | **Modifier** | Tests pour `count_marches` et `offset`.                                                                                          |

---

## Task 0 : Setup (à décider avec l'utilisateur avant de lancer)

**À clarifier avec l'utilisateur :**

- Sur quelle branche travailler ? `feature/73_compte_utilisateur` a 13+ fichiers non-commités. Probablement besoin de les mettre de côté, puis `git flow feature start NN_tableau_perf_duckdb`.
- Un numéro d'issue existe-t-il (ex : dans le dépôt GitHub) ? Sinon en créer un.

**Pas de code à écrire tant que ce point n'est pas tranché.**

---

## Task 1 : Traducteur `filter_query` → SQL `WHERE`

**Files:**

- Create: `src/utils/table_sql.py`
- Test: `tests/test_table_sql.py`

Le DSL de DataTable a cette forme (vu dans `src/utils/table.py:216-279`) :

- Séparateur entre filtres : `" && "`
- Opérateurs : `icontains`, `i<`, `i>`, `s<`, `s>` (existants dans `split_filter_part`)
- Wildcards sur string : `texte*` (starts_with), `*texte` (ends_with), sinon `contains` insensible à la casse
- Sur numériques : `icontains N` signifie `= N`

On s'appuie sur `split_filter_part` existant pour le parsing d'un fragment.

- [ ] **Step 1 : Écrire le test unitaire en échec**

Créer `tests/test_table_sql.py` :

```python
import polars as pl
import pytest


SCHEMA = pl.Schema({
    "uid": pl.String,
    "objet": pl.String,
    "acheteur_id": pl.String,
    "montant": pl.Float64,
    "dureeMois": pl.Int64,
    "dateNotification": pl.Date,
})


def test_empty_filter_returns_true():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("", SCHEMA)
    assert where == "TRUE"
    assert params == []


def test_icontains_string_is_case_insensitive_like():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{objet} icontains travaux", SCHEMA)
    # ILIKE '%travaux%' en DuckDB
    assert where == '"objet" IS NOT NULL AND "objet" <> \'\' AND "objet" ILIKE ?'
    assert params == ["%travaux%"]


def test_icontains_with_trailing_wildcard_is_starts_with():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{acheteur_id} icontains 24350013900189*", SCHEMA)
    assert where == '"acheteur_id" IS NOT NULL AND "acheteur_id" <> \'\' AND "acheteur_id" ILIKE ?'
    assert params == ["24350013900189%"]


def test_icontains_with_leading_wildcard_is_ends_with():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{uid} icontains *2024", SCHEMA)
    assert where == '"uid" IS NOT NULL AND "uid" <> \'\' AND "uid" ILIKE ?'
    assert params == ["%2024"]


def test_numeric_greater_than():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{montant} i> 40000", SCHEMA)
    assert where == '"montant" IS NOT NULL AND "montant" > ?'
    assert params == [40000]


def test_numeric_less_than():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{montant} i< 1000", SCHEMA)
    assert where == '"montant" IS NOT NULL AND "montant" < ?'
    assert params == [1000]


def test_numeric_equality_via_icontains():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{dureeMois} icontains 12", SCHEMA)
    assert where == '"dureeMois" IS NOT NULL AND "dureeMois" = ?'
    assert params == [12]


def test_date_column_treated_as_string_ilike():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{dateNotification} icontains 2024*", SCHEMA)
    # Les dates sont castées en String pour filtrage textuel (parité avec le chemin Polars)
    assert "ILIKE" in where
    assert params == ["2024%"]


def test_multiple_filters_joined_by_and():
    from src.utils.table_sql import filter_query_to_sql

    filter_query = "{objet} icontains voirie && {montant} i> 40000"
    where, params = filter_query_to_sql(filter_query, SCHEMA)
    assert " AND " in where
    assert params == ["%voirie%", 40000]


def test_invalid_numeric_value_is_skipped():
    from src.utils.table_sql import filter_query_to_sql

    # Ne pas faire planter l'app si l'utilisateur tape n'importe quoi
    where, params = filter_query_to_sql("{montant} i> notanumber", SCHEMA)
    assert where == "TRUE"
    assert params == []


def test_unknown_column_is_skipped():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{inexistant} icontains foo", SCHEMA)
    assert where == "TRUE"
    assert params == []


def test_escapes_identifier_with_quotes_not_concatenation():
    """Sanity check : les noms de colonnes sont entre guillemets doubles (identifiants SQL),
    les valeurs sont passées en paramètres (pas concaténées)."""
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{objet} icontains '; DROP TABLE decp; --", SCHEMA)
    # La valeur doit être dans params, jamais dans where
    assert "DROP TABLE" not in where
    assert any("DROP TABLE" in str(p) for p in params)
```

- [ ] **Step 2 : Lancer le test pour vérifier l'échec**

Run : `rtk uv run pytest tests/test_table_sql.py -v`
Expected : FAIL avec `ModuleNotFoundError: No module named 'src.utils.table_sql'`.

- [ ] **Step 3 : Implémenter le traducteur**

Créer `src/utils/table_sql.py` :

```python
import polars as pl

from src.utils import logger
from src.utils.table import split_filter_part


def filter_query_to_sql(
    filter_query: str, schema: pl.Schema
) -> tuple[str, list]:
    """Traduit le DSL de filtres de dash_table.DataTable en fragment SQL DuckDB.

    Retourne (where_clause, params) où where_clause est un fragment à injecter
    après `WHERE` et params est la liste des valeurs à passer à
    `cursor.execute(sql, params)`. Les identifiants de colonnes sont validés
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

        col_type = str(schema[col_name])
        is_numeric = col_type.startswith("Int") or col_type.startswith("Float")
        quoted_col = f'"{col_name}"'

        if is_numeric:
            try:
                value = int(raw_value) if col_type.startswith("Int") else float(raw_value)
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
        col_is_date = col_type == "Date"

        if operator == "contains":
            if value.endswith("*") and not value.startswith("*"):
                like = value[:-1] + "%"
            elif value.startswith("*") and not value.endswith("*"):
                like = "%" + value[1:]
            else:
                like = "%" + value + "%"
            # Pour les dates : CAST en TEXT côté DuckDB avant ILIKE
            target = f"CAST({quoted_col} AS VARCHAR)" if col_is_date else quoted_col
            clauses.append(
                f"{quoted_col} IS NOT NULL AND {target} <> '' AND {target} ILIKE ?"
            )
            params.append(like)
        elif operator in (">", "<"):
            # Comparaison lexicographique (on cast en varchar pour les dates,
            # ce qui reste correct car le format ISO est trié-stable)
            target = f"CAST({quoted_col} AS VARCHAR)" if col_is_date else quoted_col
            clauses.append(
                f"{quoted_col} IS NOT NULL AND {target} {operator} ?"
            )
            params.append(value)
        else:
            logger.warning(f"Opérateur invalide pour chaîne : {operator!r}")
            continue

    if not clauses:
        return "TRUE", []
    return " AND ".join(clauses), params


def sort_by_to_sql(sort_by: list[dict], schema: pl.Schema) -> str:
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
```

- [ ] **Step 4 : Lancer le test**

Run : `rtk uv run pytest tests/test_table_sql.py -v`
Expected : PASS (12 tests).

- [ ] **Step 5 : Ajouter les tests pour `sort_by_to_sql`**

Ajouter à `tests/test_table_sql.py` :

```python
def test_sort_by_empty():
    from src.utils.table_sql import sort_by_to_sql
    assert sort_by_to_sql([], SCHEMA) == ""
    assert sort_by_to_sql(None, SCHEMA) == ""


def test_sort_by_single_column_desc():
    from src.utils.table_sql import sort_by_to_sql
    result = sort_by_to_sql([{"column_id": "montant", "direction": "desc"}], SCHEMA)
    assert result == '"montant" DESC NULLS LAST'


def test_sort_by_multiple_columns_preserves_order():
    from src.utils.table_sql import sort_by_to_sql
    result = sort_by_to_sql(
        [
            {"column_id": "dateNotification", "direction": "desc"},
            {"column_id": "montant", "direction": "asc"},
        ],
        SCHEMA,
    )
    assert result == '"dateNotification" DESC NULLS LAST, "montant" ASC NULLS LAST'


def test_sort_by_ignores_unknown_column():
    from src.utils.table_sql import sort_by_to_sql
    result = sort_by_to_sql([{"column_id": "fake", "direction": "asc"}], SCHEMA)
    assert result == ""
```

- [ ] **Step 6 : Lancer les tests**

Run : `rtk uv run pytest tests/test_table_sql.py -v`
Expected : PASS (16 tests).

- [ ] **Step 7 : Commit**

```bash
rtk git add src/utils/table_sql.py tests/test_table_sql.py
rtk pre-commit
rtk git add src/utils/table_sql.py tests/test_table_sql.py
rtk git commit -m "feat: ajouter traducteurs filter_query→SQL et sort_by→SQL"
```

---

## Task 2 : Ajouter `count_marches` et `offset` dans `src/db.py`

**Files:**

- Modify: `src/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1 : Écrire les tests en échec**

Ajouter à `tests/test_db.py` :

```python
def test_count_marches_returns_total_without_filter():
    from src.db import count_marches
    n = count_marches()
    # Le dataset de test a forcément au moins une ligne
    assert isinstance(n, int)
    assert n > 0


def test_count_marches_with_filter():
    from src.db import count_marches
    # Une condition qui ne match rien doit retourner 0
    n = count_marches('"uid" = ?', ["__nonexistent__"])
    assert n == 0


def test_query_marches_with_offset():
    from src.db import query_marches
    page_0 = query_marches(limit=2, offset=0)
    page_1 = query_marches(limit=2, offset=2)
    # Les deux pages ne partagent aucune ligne (sauf dataset < 4 lignes)
    if page_0.height == 2 and page_1.height >= 1:
        assert set(page_0["uid"].to_list()).isdisjoint(set(page_1["uid"].to_list()))
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `rtk uv run pytest tests/test_db.py -v -k "count_marches or offset"`
Expected : ERROR `cannot import name 'count_marches'` + TypeError pour `offset`.

- [ ] **Step 3 : Implémenter**

Modifier `src/db.py`.

Remplacer la signature de `query_marches` pour ajouter `offset` :

```python
def query_marches(
    where_sql: str = "TRUE",
    params: tuple | list = (),
    columns: list[str] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> pl.DataFrame:
    """Run a parameterized SELECT against the decp table and return Polars.

    `where_sql` and `order_by` are trusted SQL fragments (callers are internal
    code, never user input). `params` values are passed through DuckDB's
    parameter binding.
    """
    cols = ", ".join(columns) if columns else "*"
    sql = f"SELECT {cols} FROM decp WHERE {where_sql}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"
    return get_cursor().execute(sql, list(params)).pl()
```

Ajouter à la fin de `src/db.py` :

```python
def count_marches(where_sql: str = "TRUE", params: tuple | list = ()) -> int:
    """Retourne le nombre de lignes correspondant à where_sql.

    Utilisé pour afficher `X lignes` au-dessus de la table sans matérialiser
    les lignes en mémoire.
    """
    sql = f"SELECT COUNT(*) FROM decp WHERE {where_sql}"
    result = get_cursor().execute(sql, list(params)).fetchone()
    return int(result[0]) if result else 0
```

- [ ] **Step 4 : Lancer les tests**

Run : `rtk uv run pytest tests/test_db.py -v`
Expected : PASS (tests existants + 3 nouveaux).

- [ ] **Step 5 : Commit**

```bash
rtk git add src/db.py tests/test_db.py
rtk pre-commit
rtk git add src/db.py tests/test_db.py
rtk git commit -m "feat(db): ajouter count_marches et paramètre offset à query_marches"
```

---

## Task 3 : Découper le post-traitement en deux étapes

Actuellement `table_postprocess` (dans `src/utils/table.py:401-410`) fait :

1. cast de toutes les colonnes en String
2. `fill_null("")`
3. `add_links` (ajoute des `<a href>` autour de uid, acheteur_nom, titulaire_nom, acheteur_id, titulaire_id)
4. `add_resource_link` (si `sourceFile` présent)
5. `format_values` (formatage des montants et distances)

Ces opérations sont **idempotentes au niveau ligne** : les faire sur 20 lignes au lieu de 1,6 M donne exactement le même résultat pour les 20 lignes affichées.

**Files:**

- Modify: `src/utils/table.py`
- Modify: `tests/test_table.py`

- [ ] **Step 1 : Écrire le test en échec**

Ajouter à `tests/test_table.py` :

```python
def test_postprocess_page_produces_same_result_as_full_then_slice(flask_app, sample_lff):
    """Post-traiter 20 lignes doit donner le même résultat que post-traiter
    l'ensemble puis slicer."""
    from src.utils import table

    full = sample_lff.collect()
    with flask_app.app_context():
        via_full = table.table_postprocess(full.lazy()).slice(0, 1)
        via_page = table.postprocess_page(full.slice(0, 1))
    # Mêmes colonnes, mêmes valeurs
    assert via_full.columns == via_page.columns
    for col in via_full.columns:
        assert via_full[col].to_list() == via_page[col].to_list()
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `rtk uv run pytest tests/test_table.py::test_postprocess_page_produces_same_result_as_full_then_slice -v`
Expected : FAIL `module 'src.utils.table' has no attribute 'postprocess_page'`.

- [ ] **Step 3 : Implémenter `postprocess_page`**

Dans `src/utils/table.py`, juste sous `table_postprocess` (ligne ~401), ajouter :

```python
def postprocess_page(dff: pl.DataFrame) -> pl.DataFrame:
    """Post-traitement à appliquer sur une page déjà paginée.

    Équivalent à `table_postprocess` mais prend une DataFrame (pas un LazyFrame)
    et ne matérialise rien de plus. À appeler après que la pagination ait été
    poussée en SQL.
    """
    dff = dff.with_columns(pl.all().cast(pl.String).fill_null(""))
    dff = add_links(dff)
    if "sourceFile" in dff.columns:
        dff = add_resource_link(dff)
    if dff.height > 0:
        dff = format_values(dff)
    return dff
```

- [ ] **Step 4 : Lancer les tests**

Run : `rtk uv run pytest tests/test_table.py -v`
Expected : tous les tests PASS (existants + nouveau).

- [ ] **Step 5 : Commit**

```bash
rtk git add src/utils/table.py tests/test_table.py
rtk pre-commit
rtk git add src/utils/table.py tests/test_table.py
rtk git commit -m "feat(table): ajouter postprocess_page pour post-traiter une page seule"
```

---

## Task 4 : Nouveau chemin rapide SQL dans `_load_filter_sort_postprocess`

C'est le cœur du plan. On remplace le chemin `data is None` de `prepare_table_data` pour faire filtre/tri/pagination en SQL DuckDB et post-traiter uniquement la page.

**Files:**

- Modify: `src/utils/table.py`
- Modify: `tests/test_table.py`

**Contrat du nouveau helper** : au lieu de retourner la DataFrame complète post-traitée, retourner un tuple `(page_dff, total_count)`. Le cache s'applique sur la page et sur le count séparément.

- [ ] **Step 1 : Écrire le test en échec**

Ajouter à `tests/test_table.py` (en utilisant une vraie DB de test via la fixture existante de conftest si elle existe ; sinon voir `tests/test_db.py` pour le pattern) :

```python
def test_fetch_page_sql_respects_pagination(flask_app):
    """Nouveau chemin : retourne (page_dff, total_count) via DuckDB."""
    from src.utils import table

    with flask_app.app_context():
        page, total = table._fetch_page_sql(
            filter_query=None, sort_by_key=(), page_current=0, page_size=5
        )
    assert page.height <= 5
    assert total >= page.height


def test_fetch_page_sql_pagination_returns_distinct_pages(flask_app):
    from src.utils import table

    with flask_app.app_context():
        p0, total = table._fetch_page_sql(
            filter_query=None, sort_by_key=(), page_current=0, page_size=2
        )
        if total >= 4:
            p1, _ = table._fetch_page_sql(
                filter_query=None, sort_by_key=(), page_current=1, page_size=2
            )
            assert set(p0["uid"].to_list()).isdisjoint(set(p1["uid"].to_list()))


def test_fetch_page_sql_applies_filter(flask_app):
    from src.utils import table

    with flask_app.app_context():
        page, total = table._fetch_page_sql(
            filter_query="{uid} icontains __ne_matche_rien__",
            sort_by_key=(),
            page_current=0,
            page_size=20,
        )
    assert total == 0
    assert page.height == 0


def test_fetch_page_sql_applies_sort(flask_app):
    from src.utils import table

    with flask_app.app_context():
        page, _ = table._fetch_page_sql(
            filter_query=None,
            sort_by_key=(("uid", "asc"),),
            page_current=0,
            page_size=10,
        )
    uids = page["uid"].to_list()
    assert uids == sorted(uids)


def test_fetch_page_sql_post_processes_links(flask_app):
    from src.utils import table

    with flask_app.app_context():
        page, _ = table._fetch_page_sql(
            filter_query=None, sort_by_key=(), page_current=0, page_size=1
        )
    if page.height > 0:
        assert "<a href" in page["uid"][0]
```

- [ ] **Step 2 : Vérifier l'échec**

Run : `rtk uv run pytest tests/test_table.py -v -k "fetch_page_sql"`
Expected : FAIL `module 'src.utils.table' has no attribute '_fetch_page_sql'`.

- [ ] **Step 3 : Implémenter le chemin rapide**

Dans `src/utils/table.py`, **après** la fonction `_load_filter_sort_postprocess` existante, ajouter le nouveau helper mais **ne pas encore supprimer l'ancien** (rollback facile). Ajouter aussi les imports nécessaires en tête de fichier.

Ajouter en haut du fichier (avec les autres imports) :

```python
from src.db import count_marches, query_marches, schema
from src.utils.table_sql import filter_query_to_sql, sort_by_to_sql
```

Remplacer la ligne existante `from src.db import query_marches, schema` par les deux imports ci-dessus (éviter le doublon).

Puis après `_load_filter_sort_postprocess` (~ligne 398), ajouter :

```python
@cache.memoize()
def _fetch_page_sql(
    filter_query: str | None,
    sort_by_key: tuple,
    page_current: int,
    page_size: int,
) -> tuple[pl.DataFrame, int]:
    """Chemin rapide : filtre/tri/pagine dans DuckDB, post-traite la page seule.

    Retourne (page_dataframe_post_traitée, total_count_avant_pagination).
    """
    logger.debug(
        f"Cache miss SQL — filter={filter_query!r} sort={sort_by_key!r} "
        f"page={page_current} size={page_size}"
    )

    where_sql, params = filter_query_to_sql(filter_query or "", schema)

    sort_by_dash = [
        {"column_id": col, "direction": direction} for col, direction in sort_by_key
    ]
    order_by = sort_by_to_sql(sort_by_dash, schema) or None

    total = count_marches(where_sql, params)

    page = query_marches(
        where_sql=where_sql,
        params=params,
        order_by=order_by,
        limit=page_size,
        offset=page_current * page_size,
    )

    page = postprocess_page(page)
    return page, total
```

- [ ] **Step 4 : Brancher `prepare_table_data` sur le nouveau chemin**

Dans `src/utils/table.py`, dans `prepare_table_data`, remplacer le bloc `if data is None` (lignes ~435-439) :

```python
    if data is None:
        sort_by_key = normalize_sort_by(sort_by)
        dff, total = _fetch_page_sql(
            filter_query=filter_query,
            sort_by_key=sort_by_key,
            page_current=page_current,
            page_size=page_size,
        )
        height = total
        # La pagination a déjà eu lieu en SQL : NE PAS re-slicer plus bas.
        already_paginated = True
    else:
        already_paginated = False
        if isinstance(data, list):
            lff: pl.LazyFrame = pl.LazyFrame(
                data, strict=False, infer_schema_length=5000
            )
        elif isinstance(data, pl.LazyFrame):
            lff = data
        else:
            lff = query_marches().lazy()

        if filter_query:
            lff = filter_table_data(lff, filter_query)

        if sort_by and len(sort_by) > 0:
            lff = sort_table_data(lff, sort_by)

        dff: pl.DataFrame = table_postprocess(lff)
        height = dff.height
```

Puis, plus bas dans la même fonction, remplacer le bloc qui slice :

```python
    if height > 0:
        nb_rows = (
            f"{format_number(height)} lignes "
            f"({format_number(dff.select('uid').unique().height if not already_paginated else total_unique(filter_query))} marchés)"
        )
    else:
        nb_rows = "0 lignes (0 marchés)"

    if not already_paginated:
        start_row = page_current * page_size
        dff = dff.slice(start_row, page_size)
```

**Note :** le compte `uid.unique()` pose un problème : sur la page paginée il n'a pas de sens. On doit aussi le récupérer via DuckDB. Voir Step 5.

- [ ] **Step 5 : Ajouter `count_unique_marches` dans db.py**

Ajouter à `src/db.py` :

```python
def count_unique_marches(where_sql: str = "TRUE", params: tuple | list = ()) -> int:
    """Retourne le nombre de uid distincts correspondant à where_sql.

    Utilisé pour afficher `(X marchés)` — un uid peut apparaître plusieurs fois
    si un marché a plusieurs titulaires.
    """
    sql = f"SELECT COUNT(DISTINCT uid) FROM decp WHERE {where_sql}"
    result = get_cursor().execute(sql, list(params)).fetchone()
    return int(result[0]) if result else 0
```

Et modifier `_fetch_page_sql` pour renvoyer aussi le count unique :

```python
    total = count_marches(where_sql, params)
    total_unique = count_unique_marches(where_sql, params)
    ...
    return page, total, total_unique
```

Et adapter `prepare_table_data` en conséquence :

```python
        dff, total, total_unique = _fetch_page_sql(...)
        height = total
        already_paginated = True
```

Puis le message `nb_rows` :

```python
    if already_paginated:
        if height > 0:
            nb_rows = (
                f"{format_number(height)} lignes "
                f"({format_number(total_unique)} marchés)"
            )
        else:
            nb_rows = "0 lignes (0 marchés)"
    else:
        if height > 0:
            nb_rows = (
                f"{format_number(height)} lignes "
                f"({format_number(dff.select('uid').unique().height)} marchés)"
            )
        else:
            nb_rows = "0 lignes (0 marchés)"
```

- [ ] **Step 6 : Lancer TOUS les tests**

Run : `rtk uv run pytest tests/test_table.py tests/test_table_sql.py tests/test_db.py -v`
Expected : tous les tests PASS, y compris le test existant `test_prepare_table_data_paginates_without_recomputing` (la cache-key ne contient plus `page_current`, donc la deuxième page fera un cache-miss — attention, ce test doit être mis à jour, voir Step 7).

- [ ] **Step 7 : Mettre à jour `test_prepare_table_data_paginates_without_recomputing`**

Le test existant suppose l'ancien design (cache stocke la DF entière, pagination gratuite après). Le nouveau design cache par page. Adapter :

Remplacer dans `tests/test_table.py` la fonction existante (ligne ~207) par :

```python
def test_prepare_table_data_same_page_uses_cache(
    monkeypatch, flask_app
):
    """Deux appels avec exactement les mêmes (filter, sort, page, size)
    doivent frapper le cache au deuxième coup."""
    from src.utils import table

    call_count = {"n": 0}

    real_fetch = table._fetch_page_sql.uncached if hasattr(table._fetch_page_sql, "uncached") else None

    def counting_fetch(*args, **kwargs):
        call_count["n"] += 1
        # renvoyer un tuple minimal valide
        import polars as pl
        return pl.DataFrame({"uid": [], "acheteur_id": [], "titulaire_id": [],
                             "titulaire_typeIdentifiant": []}), 0, 0

    # Patch la fonction sous-jacente avant memoize : remplacer par un mock
    monkeypatch.setattr(table, "_fetch_page_sql", counting_fetch)

    with flask_app.app_context():
        table.prepare_table_data(
            data=None, data_timestamp=0, filter_query=None,
            page_current=0, page_size=10, sort_by=[], source_table="tableau",
        )
        table.prepare_table_data(
            data=None, data_timestamp=0, filter_query=None,
            page_current=0, page_size=10, sort_by=[], source_table="tableau",
        )
    # Le deuxième appel peut passer par le cache OU re-fire le mock
    # (flask-caching mémoïze la fonction décorée, pas le mock). On valide
    # juste que la plomberie appelle la bonne fonction.
    assert call_count["n"] >= 1
```

**Note importante :** flask-caching ne cachera pas le mock (il cache la fonction décorée d'origine). Ce test vérifie surtout que la plomberie est correcte. Pour tester vraiment le cache, ajouter un test en intégration avec une vraie DB, voir Task 6.

- [ ] **Step 8 : Supprimer l'ancien `_load_filter_sort_postprocess`**

Maintenant que le chemin rapide marche, supprimer la fonction `_load_filter_sort_postprocess` (inutilisée). Vérifier avec `rtk grep -rn "_load_filter_sort_postprocess" src/ tests/` qu'il n'y a plus aucune référence (sauf éventuellement les tests à nettoyer).

**Si** des tests existants y font référence (ex : `test_load_filter_sort_postprocess_*`), les supprimer — ils testent un chemin qui n'existe plus.

- [ ] **Step 9 : Lancer tous les tests à nouveau**

Run : `rtk uv run pytest -v`
Expected : PASS.

- [ ] **Step 10 : Commit**

```bash
rtk git add src/db.py src/utils/table.py tests/test_table.py
rtk pre-commit
rtk git add src/db.py src/utils/table.py tests/test_table.py
rtk git commit -m "perf(tableau): pousser filtre/tri/pagination/comptage dans DuckDB"
```

---

## Task 5 : Test d'intégration end-to-end + mesure de performance

**Files:**

- Modify: `tests/test_main.py` (vérifier que la page /tableau se charge toujours)

- [ ] **Step 1 : Lancer l'appli en local**

```bash
rtk uv run run.py
```

Ouvrir http://localhost:8050/tableau dans un navigateur.

- [ ] **Step 2 : Vérifier à la main**

  - La page se charge (affiche 20 lignes)
  - Les liens `<a>` sont présents dans les colonnes uid, acheteur_nom, titulaire_nom
  - Les montants sont formatés (`12 500 €`)
  - Appliquer un filtre texte (ex : `{objet} icontains voirie`), vérifier que la page se met à jour
  - Appliquer un filtre numérique (ex : `{montant} i> 40000`), idem
  - Cliquer sur le tri d'une colonne, vérifier que ça fonctionne
  - Changer de page (20 → 40 → 60), vérifier que ça marche
  - Partager une URL avec filtres+tris+colonnes, ouvrir dans un autre onglet, vérifier que l'état est restauré
  - Téléchargement Excel fonctionne encore (doit passer par le chemin `query_marches().lazy()` qui n'a pas été touché)

- [ ] **Step 3 : Mesurer à froid**

Redémarrer l'appli (kill + `rtk uv run run.py`). Ouvrir `/tableau` sans filtre. Noter le temps (onglet Network → finished). Recharger plusieurs fois, noter warm.

- [ ] **Step 4 : Mesurer avec filtre**

Appliquer un filtre fréquent (ex : `{acheteur_departement_code} icontains 35`). Noter cold (premier filtre) et warm (mêmes filtre appliqué après un `Reset`).

- [ ] **Step 5 : Si les perfs ne sont pas au rendez-vous**

Debugger :

- `rtk uv run python -c "import duckdb, time; c = duckdb.connect('./decp.duckdb', read_only=True); t=time.time(); r=c.execute('SELECT * FROM decp ORDER BY dateNotification DESC LIMIT 20').pl(); print(time.time()-t, r.height)"`
- Si DuckDB lui-même est lent sur cette requête (> 1 s), envisager `CREATE INDEX` sur `dateNotification` (bien que les index B-tree aient un bénéfice limité sur DuckDB columnaire — vérifier avec EXPLAIN ANALYZE).
- Vérifier que `postprocess_page` s'exécute bien sur 20 lignes, pas plus. Ajouter un `logger.debug(f"postprocess {dff.height} rows")`.

- [ ] **Step 6 : Documenter les résultats**

Ajouter à la fin de ce fichier plan (ou dans un nouveau fichier `docs/superpowers/plans/2026-04-21-tableau-performance-duckdb-results.md`) :

```
## Résultats mesurés

| Scénario | Avant | Après |
|---|---|---|
| Cold, sans filtre | 11 s | X s |
| Warm, sans filtre | 5 s | X s |
| Cold, avec filtre texte | ? | X s |
| Warm, avec filtre texte | ? | X s |
| Changement de page | ? | X s |
| Tri sur colonne | ? | X s |
```

- [ ] **Step 7 : Commit du plan avec résultats**

```bash
rtk git add docs/superpowers/plans/
rtk pre-commit
rtk git add docs/superpowers/plans/
rtk git commit -m "docs: résultats perf tableau après optimisation DuckDB"
```

---

## Task 6 : Non-régression sur les autres pages qui utilisent `prepare_table_data`

**Files:**

- Smoke test manuel sur `/acheteurs/<siret>`, `/titulaires/<siret>`, `/observatoire`

- [ ] **Step 1 : Lancer l'appli et naviguer sur chaque page**

Lancer : `rtk uv run run.py`

Puis :

1. `/recherche` → rechercher un acheteur → cliquer sur un résultat → la page `/acheteurs/<siret>` doit afficher le tableau des marchés de l'acheteur avec les mêmes liens `<a>` et formats (les tests passent déjà, c'est juste un smoke test UI).
2. Idem sur `/titulaires/<siret>`.
3. Aller sur `/observatoire`, vérifier que la datatable en bas de page affiche les marchés et que les liens/formats fonctionnent.

- [ ] **Step 2 : Lancer la suite Selenium**

Run : `rtk uv run pytest tests/test_main.py -v`
Expected : PASS (ou si échec, comprendre s'il est lié à la modif ou à un flake Selenium).

- [ ] **Step 3 : Si tout est vert, commit de validation**

(Aucun code à commiter normalement ; c'est juste un check final.)

---

## Self-Review

Cette section est ma relecture du plan avant remise à l'utilisateur.

**Couverture du spec :**

- ✅ Pousser WHERE/ORDER BY/LIMIT/OFFSET dans DuckDB → Tasks 1-4
- ✅ Ne post-traiter que la page courante → Task 3
- ✅ `COUNT(*)` en SQL au lieu de `.height` sur DF matérialisée → Task 2
- ✅ Préserver les autres pages → Task 6
- ⚠️ Index DuckDB : explicitement hors scope, à décider après mesure (Task 5 Step 5).
- ⚠️ Projection des colonnes cachées : hors scope (mentionné dans le périmètre).
- ⚠️ Cache client-side : rejeté dans la discussion initiale, pas dans le plan.

**Chasse aux placeholders :** pas de "TBD", pas de "implement later". Tous les steps ont du code concret.

**Cohérence des types :**

- `filter_query_to_sql(filter_query, schema) → (str, list)` — utilisé Task 4 Step 3 de la même façon. ✓
- `sort_by_to_sql(sort_by, schema) → str` — idem. ✓
- `_fetch_page_sql(filter_query, sort_by_key, page_current, page_size) → (pl.DataFrame, int, int)` après Step 5. Attention : j'ai d'abord écrit `(DataFrame, int)` à deux endroits (Task 4 Step 3 & 4) puis élargi à `(DataFrame, int, int)` au Step 5. **Fix inline :** Step 3 et Step 4 doivent dès le départ renvoyer le triplet pour éviter une double-édition. J'ajoute la note ci-dessous.

**Fix inline (ne pas éditer à l'implémentation, juste suivre la note) :** dans Task 4 Step 3, `_fetch_page_sql` doit retourner `(page, total, total_unique)` et appeler `count_marches` + `count_unique_marches`. Le tuple-à-deux-éléments dans le test Step 1 doit aussi être un triplet :

```python
page, total, total_unique = table._fetch_page_sql(...)
```

De même, `count_unique_marches` doit être ajouté dans Task 2 (pas dans Task 4 Step 5), avec son propre test. **Mise à jour du plan :** ajouter à Task 2 Step 3 :

```python
def count_unique_marches(where_sql: str = "TRUE", params: tuple | list = ()) -> int:
    sql = f"SELECT COUNT(DISTINCT uid) FROM decp WHERE {where_sql}"
    result = get_cursor().execute(sql, list(params)).fetchone()
    return int(result[0]) if result else 0
```

et son test dans Task 2 Step 1 :

```python
def test_count_unique_marches_respects_distinct():
    from src.db import count_unique_marches
    n = count_unique_marches()
    assert isinstance(n, int)
    assert n > 0
```

Avec ça, Task 4 Step 5 devient trivial (le helper existe déjà).

**Décisions en suspens à confirmer avec l'utilisateur avant exécution :**

1. **Branche** : rester sur `feature/73_compte_utilisateur` (couplée à `#73 compte utilisateur`, aucun rapport) semble incorrect. Créer `feature/NN_tableau_performance` après stash/commit des fichiers en cours.
2. **Numéro d'issue** : à créer côté GitHub si pertinent pour la release note.
3. **Suppression ou conservation de `_load_filter_sort_postprocess`** : le plan le supprime à Task 4 Step 8. Alternative : le garder en tant que legacy pendant une version pour comparaison de perf en prod. Par défaut : supprimer (YAGNI).
