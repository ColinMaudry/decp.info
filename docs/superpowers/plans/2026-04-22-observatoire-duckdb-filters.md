# Observatoire — filtrage natif DuckDB — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le filtrage Polars sur LazyFrame dans `prepare_dashboard_data` par un requêtage natif DuckDB, pour ne matérialiser que le sous-ensemble utile au lieu de l'intégralité de la table `decp` (~1,5 M lignes).

**Architecture:** Nouveau helper pur `dashboard_filters_to_sql(**filter_params) -> (where_sql, params)` dans `src/utils/table_sql.py` (modèle de `filter_query_to_sql`). `prepare_dashboard_data` devient une fonction fine qui appelle `query_marches(where_sql, params)` et retourne une `pl.DataFrame`. Les 3 appelants dans `src/pages/observatoire.py` sont adaptés à la nouvelle signature.

**Tech Stack:** Python 3.12, Polars, DuckDB, Dash, pytest.

**Spec:** `docs/superpowers/specs/2026-04-22-observatoire-duckdb-filters-design.md`.

---

## File Structure

**À créer :**

- `tests/test_dashboard_filters_to_sql.py` — tests unitaires du nouveau helper SQL (cas vide + cas par filtre).
- `tests/test_prepare_dashboard_data.py` — test d'intégration léger (appel DuckDB réel sur `tests/test.parquet`).

**À modifier :**

- `src/utils/table_sql.py` — ajouter `dashboard_filters_to_sql` + import `datetime`/`timedelta`.
- `src/utils/data.py` — réécrire `prepare_dashboard_data` (signature et implémentation), ajouter `query_marches` aux imports `from src.db`.
- `src/pages/observatoire.py` — adapter 3 sites d'appel (lignes ~668, ~791, ~882) ; retirer `query_marches` de l'import `from src.db` (plus utilisé).
- `tests/test_main.py` — supprimer `test_010_observatoire_montant_filter` (migré en test unitaire du helper).

---

## Task 1: Tests unitaires — cas par défaut + filtre année

**Files:**

- Create: `tests/test_dashboard_filters_to_sql.py`
- Modify: `src/utils/table_sql.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dashboard_filters_to_sql.py`:

```python
from datetime import datetime, timedelta

from src.utils.table_sql import dashboard_filters_to_sql


def test_no_filters_uses_default_365_day_window():
    where_sql, params = dashboard_filters_to_sql()
    assert where_sql == '"dateNotification" > ?'
    assert len(params) == 1
    assert isinstance(params[0], datetime)
    expected = datetime.now() - timedelta(days=365)
    assert abs((params[0] - expected).total_seconds()) < 2


def test_year_filter_overrides_default_window():
    where_sql, params = dashboard_filters_to_sql(dashboard_year="2025")
    assert where_sql == 'YEAR("dateNotification") = ?'
    assert params == [2025]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: FAIL with `ImportError: cannot import name 'dashboard_filters_to_sql'`.

- [ ] **Step 3: Implement the helper**

Add to the top of `src/utils/table_sql.py` (below existing imports):

```python
from datetime import datetime, timedelta
```

Append this function at the end of `src/utils/table_sql.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git add tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git commit -m "feat(observatoire): squelette de dashboard_filters_to_sql (#72)"
```

---

## Task 2: Filtres d'égalité simples (catégorie, type, innovant, sous-traitance)

**Files:**

- Modify: `tests/test_dashboard_filters_to_sql.py`
- Modify: `src/utils/table_sql.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_dashboard_filters_to_sql.py`:

```python
def test_marche_type_equality():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_type="Marché",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "type" = ?'
    assert params == [2025, "Marché"]


def test_innovant_value_all_is_skipped():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_innovant="all",
    )
    assert where_sql == 'YEAR("dateNotification") = ?'
    assert params == [2025]


def test_innovant_value_oui_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_innovant="oui",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "marcheInnovant" = ?'
    assert params == [2025, "oui"]


def test_sous_traitance_value_non_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_sous_traitance_declaree="non",
    )
    assert (
        where_sql
        == 'YEAR("dateNotification") = ? AND "sousTraitanceDeclaree" = ?'
    )
    assert params == [2025, "non"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: 4 new tests FAIL (missing clauses).

- [ ] **Step 3: Extend the helper**

Insert the following block in `dashboard_filters_to_sql`, **after** the `if dashboard_year / else` block and **before** `return " AND ".join(clauses), params`:

```python
    if dashboard_marche_type:
        clauses.append('"type" = ?')
        params.append(dashboard_marche_type)

    if dashboard_marche_innovant and dashboard_marche_innovant != "all":
        clauses.append('"marcheInnovant" = ?')
        params.append(dashboard_marche_innovant)

    if (
        dashboard_marche_sous_traitance_declaree
        and dashboard_marche_sous_traitance_declaree != "all"
    ):
        clauses.append('"sousTraitanceDeclaree" = ?')
        params.append(dashboard_marche_sous_traitance_declaree)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: PASS (6 tests total).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git add tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git commit -m "feat(observatoire): filtres d'égalité simples dans dashboard_filters_to_sql (#72)"
```

---

## Task 3: Filtres LIKE/ILIKE (ids, objet, cpv)

**Files:**

- Modify: `tests/test_dashboard_filters_to_sql.py`
- Modify: `src/utils/table_sql.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_dashboard_filters_to_sql.py`:

```python
def test_acheteur_id_uses_like_wildcards():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_id="12345678900010",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_id" LIKE ?'
    assert params == [2025, "%12345678900010%"]


def test_titulaire_id_uses_like_wildcards():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_titulaire_id="999",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "titulaire_id" LIKE ?'
    assert params == [2025, "%999%"]


def test_marche_objet_uses_case_insensitive_ilike():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_objet="travaux",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "objet" ILIKE ?'
    assert params == [2025, "%travaux%"]


def test_code_cpv_uses_prefix_like():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_code_cpv="4521",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "codeCPV" LIKE ?'
    assert params == [2025, "4521%"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: 4 new tests FAIL.

- [ ] **Step 3: Extend the helper**

Insert the following block, **just after** the year/default block and **before** the `if dashboard_marche_type` block:

```python
    if dashboard_acheteur_id:
        clauses.append('"acheteur_id" LIKE ?')
        params.append(f"%{dashboard_acheteur_id}%")

    if dashboard_titulaire_id:
        clauses.append('"titulaire_id" LIKE ?')
        params.append(f"%{dashboard_titulaire_id}%")
```

Insert in the "marché" block, **after** `dashboard_marche_type` and **before** `dashboard_marche_innovant`:

```python
    if dashboard_marche_objet:
        clauses.append('"objet" ILIKE ?')
        params.append(f"%{dashboard_marche_objet}%")

    if dashboard_marche_code_cpv:
        clauses.append('"codeCPV" LIKE ?')
        params.append(f"{dashboard_marche_code_cpv}%")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: PASS (10 tests total).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git add tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git commit -m "feat(observatoire): filtres LIKE/ILIKE dans dashboard_filters_to_sql (#72)"
```

---

## Task 4: Filtre IN (départements) + skip conditionnel par ID

**Files:**

- Modify: `tests/test_dashboard_filters_to_sql.py`
- Modify: `src/utils/table_sql.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_dashboard_filters_to_sql.py`:

```python
def test_acheteur_departement_multiple_uses_in_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_departement_code=["75", "92", "93"],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        'AND "acheteur_departement_code" IN (?, ?, ?)'
    )
    assert params == [2025, "75", "92", "93"]


def test_acheteur_categorie_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_categorie="Commune",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_categorie" = ?'
    assert params == [2025, "Commune"]


def test_titulaire_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_titulaire_categorie="PME",
        dashboard_titulaire_departement_code=["35"],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        'AND "titulaire_categorie" = ? '
        'AND "titulaire_departement_code" IN (?)'
    )
    assert params == [2025, "PME", "35"]


def test_acheteur_id_present_skips_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_id="123",
        dashboard_acheteur_categorie="Commune",
        dashboard_acheteur_departement_code=["75"],
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_id" LIKE ?'
    assert params == [2025, "%123%"]


def test_titulaire_id_present_skips_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_titulaire_id="999",
        dashboard_titulaire_categorie="PME",
        dashboard_titulaire_departement_code=["35"],
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "titulaire_id" LIKE ?'
    assert params == [2025, "%999%"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: 5 new tests FAIL.

- [ ] **Step 3: Refactor the helper with conditional skip**

Replace the two simple `if dashboard_acheteur_id` / `if dashboard_titulaire_id` blocks added in Task 3 with the nested form:

```python
    if dashboard_acheteur_id:
        clauses.append('"acheteur_id" LIKE ?')
        params.append(f"%{dashboard_acheteur_id}%")
    else:
        if dashboard_acheteur_categorie:
            clauses.append('"acheteur_categorie" = ?')
            params.append(dashboard_acheteur_categorie)
        if dashboard_acheteur_departement_code:
            placeholders = ", ".join(["?"] * len(dashboard_acheteur_departement_code))
            clauses.append(f'"acheteur_departement_code" IN ({placeholders})')
            params.extend(dashboard_acheteur_departement_code)

    if dashboard_titulaire_id:
        clauses.append('"titulaire_id" LIKE ?')
        params.append(f"%{dashboard_titulaire_id}%")
    else:
        if dashboard_titulaire_categorie:
            clauses.append('"titulaire_categorie" = ?')
            params.append(dashboard_titulaire_categorie)
        if dashboard_titulaire_departement_code:
            placeholders = ", ".join(
                ["?"] * len(dashboard_titulaire_departement_code)
            )
            clauses.append(f'"titulaire_departement_code" IN ({placeholders})')
            params.extend(dashboard_titulaire_departement_code)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: PASS (15 tests total).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git add tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git commit -m "feat(observatoire): IN départements et skip conditionnel par ID (#72)"
```

---

## Task 5: Filtre liste (techniques, considérations sociales/environnementales)

**Files:**

- Modify: `tests/test_dashboard_filters_to_sql.py`
- Modify: `src/utils/table_sql.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_dashboard_filters_to_sql.py`:

```python
def test_marche_techniques_uses_list_has_any():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_techniques=["Enchère", "Accord-cadre"],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_any(string_split(\"techniques\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Enchère", "Accord-cadre"]]


def test_considerations_sociales_uses_list_has_any():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_considerations_sociales=["Clause sociale"],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_any(string_split(\"considerationsSociales\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Clause sociale"]]


def test_considerations_environnementales_uses_list_has_any():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_considerations_environnementales=["Clause env."],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_any(string_split(\"considerationsEnvironnementales\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Clause env."]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: 3 new tests FAIL.

- [ ] **Step 3: Extend the helper**

Insert the following block in `dashboard_filters_to_sql`, **after** the `dashboard_marche_sous_traitance_declaree` block and **before** `return " AND ".join(clauses), params`:

```python
    if dashboard_marche_techniques:
        clauses.append(
            "list_has_any(string_split(\"techniques\", ', '), ?::VARCHAR[])"
        )
        params.append(list(dashboard_marche_techniques))

    if dashboard_marche_considerations_sociales:
        clauses.append(
            "list_has_any(string_split(\"considerationsSociales\", ', '), ?::VARCHAR[])"
        )
        params.append(list(dashboard_marche_considerations_sociales))

    if dashboard_marche_considerations_environnementales:
        clauses.append(
            "list_has_any(string_split(\"considerationsEnvironnementales\", ', '), ?::VARCHAR[])"
        )
        params.append(list(dashboard_marche_considerations_environnementales))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: PASS (18 tests total).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git add tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git commit -m "feat(observatoire): filtres liste via list_has_any (#72)"
```

---

## Task 6: Filtres montant min/max (incluant 0)

**Files:**

- Modify: `tests/test_dashboard_filters_to_sql.py`
- Modify: `src/utils/table_sql.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_dashboard_filters_to_sql.py`:

```python
def test_montant_min_only():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_min=1000,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant" >= ?'
    assert params == [2025, 1000]


def test_montant_max_only():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_max=500,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant" <= ?'
    assert params == [2025, 500]


def test_montant_zero_is_a_valid_lower_bound():
    # 0 est falsy mais reste un filtre valide (distinct de None)
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_min=0,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant" >= ?'
    assert params == [2025, 0]


def test_montant_min_and_max_combined():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_min=100,
        dashboard_montant_max=1000,
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? AND "montant" >= ? AND "montant" <= ?'
    )
    assert params == [2025, 100, 1000]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: 4 new tests FAIL.

- [ ] **Step 3: Extend the helper**

Insert at the very end of `dashboard_filters_to_sql`, **just before** `return " AND ".join(clauses), params`:

```python
    if dashboard_montant_min is not None:
        clauses.append('"montant" >= ?')
        params.append(dashboard_montant_min)

    if dashboard_montant_max is not None:
        clauses.append('"montant" <= ?')
        params.append(dashboard_montant_max)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`
Expected: PASS (22 tests total).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git add tests/test_dashboard_filters_to_sql.py src/utils/table_sql.py
rtk git commit -m "feat(observatoire): filtres montant min/max (#72)"
```

---

## Task 7: Réécriture de `prepare_dashboard_data`

**Files:**

- Modify: `src/utils/data.py`
- Modify: `tests/test_main.py` (supprimer `test_010_observatoire_montant_filter`)

- [ ] **Step 1: Remove the obsolete Polars-based test**

Delete the function `test_010_observatoire_montant_filter` from `tests/test_main.py` (lines ~218-256). La couverture du filtre montant est déjà assurée par les tests unitaires `test_montant_*` de la Task 6.

- [ ] **Step 2: Rewrite `prepare_dashboard_data`**

Replace the entire `prepare_dashboard_data` function in `src/utils/data.py` (lines ~86-194) with:

```python
def prepare_dashboard_data(**filter_params) -> pl.DataFrame:
    """Exécute la requête DuckDB filtrée pour le tableau de bord.

    Retourne une pl.DataFrame matérialisée uniquement pour le sous-ensemble
    correspondant aux filtres. Les appelants qui ont besoin d'une LazyFrame
    appellent `.lazy()` sur le résultat.
    """
    from src.utils.table_sql import dashboard_filters_to_sql

    where_sql, params = dashboard_filters_to_sql(**filter_params)
    return query_marches(where_sql=where_sql, params=params)
```

Update the import at the top of `src/utils/data.py`:

```python
from src.db import get_cursor, query_marches, schema
```

Remove the now-unused import in `src/utils/data.py`:

```python
from datetime import datetime, timedelta
```

(Si `datetime` n'est plus référencé dans `data.py` hors de `prepare_dashboard_data`, sinon garder.)

**Vérification rapide à effectuer avant de supprimer `datetime`/`timedelta`** :

```bash
rtk grep -n "datetime\|timedelta" src/utils/data.py
```

Si d'autres occurrences existent, conserver les imports.

- [ ] **Step 3: Run the full test suite**

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py tests/test_main.py -v -k "not selenium and not dash_duo"`

Ou, si filter n'est pas pratique :

Run: `rtk pytest tests/test_dashboard_filters_to_sql.py -v`

Expected: PASS (22 tests).

- [ ] **Step 4: Commit**

```bash
rtk pre-commit run --files src/utils/data.py tests/test_main.py
rtk git add src/utils/data.py tests/test_main.py
rtk git commit -m "refactor(observatoire): prepare_dashboard_data utilise DuckDB (#72)"
```

---

## Task 8: Adaptation des 3 appelants dans `observatoire.py`

**Files:**

- Modify: `src/pages/observatoire.py`

- [ ] **Step 1: Update `_compute_dashboard_children`**

Remplacer dans `src/pages/observatoire.py` (autour des lignes 660-670) :

```python
@cache.memoize()
def _compute_dashboard_children(filter_params_normalized: tuple):
    logger.debug("Cache miss — computing dashboard")
    filter_params = {
        k: (list(v) if isinstance(v, tuple) else v) for k, v in filter_params_normalized
    }

    lff: pl.LazyFrame = query_marches().lazy()
    lff = prepare_dashboard_data(lff=lff, **filter_params)

    dff = lff.collect(engine="streaming")
```

Par :

```python
@cache.memoize()
def _compute_dashboard_children(filter_params_normalized: tuple):
    logger.debug("Cache miss — computing dashboard")
    filter_params = {
        k: (list(v) if isinstance(v, tuple) else v) for k, v in filter_params_normalized
    }

    dff = prepare_dashboard_data(**filter_params)
    lff = dff.lazy()
```

Le reste de la fonction (à partir de `df_per_uid = ...`) est inchangé.

- [ ] **Step 2: Update `download_observatoire`**

Remplacer dans `src/pages/observatoire.py` (autour des lignes 789-800) :

```python
def download_observatoire(_n_clicks, filter_params, hidden_columns):
    lff = prepare_dashboard_data(lff=query_marches().lazy(), **(filter_params or {}))

    if hidden_columns:
        lff = lff.drop(hidden_columns)

    def to_bytes(buffer):
        lff.collect(engine="streaming").write_excel(buffer, worksheet="DECP")

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_observatoire_{date}.xlsx")
```

Par :

```python
def download_observatoire(_n_clicks, filter_params, hidden_columns):
    dff = prepare_dashboard_data(**(filter_params or {}))

    if hidden_columns:
        dff = dff.drop(hidden_columns)

    def to_bytes(buffer):
        dff.write_excel(buffer, worksheet="DECP")

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_observatoire_{date}.xlsx")
```

- [ ] **Step 3: Update `populate_preview_table`**

Remplacer dans `src/pages/observatoire.py` (autour des lignes 879-892) :

```python
    if not is_open:
        return (no_update,) * 9

    lff = prepare_dashboard_data(lff=query_marches().lazy(), **(filter_params or {}))

    return prepare_table_data(
        lff,
        data_timestamp,
        filter_query,
        page_current,
        page_size,
        sort_by,
        "observatoire-preview",
    )
```

Par :

```python
    if not is_open:
        return (no_update,) * 9

    dff = prepare_dashboard_data(**(filter_params or {}))

    return prepare_table_data(
        dff.lazy(),
        data_timestamp,
        filter_query,
        page_current,
        page_size,
        sort_by,
        "observatoire-preview",
    )
```

- [ ] **Step 4: Remove unused `query_marches` import**

Dans `src/pages/observatoire.py`, ligne ~19 :

```python
from src.db import query_marches, schema
```

Devient :

```python
from src.db import schema
```

Vérifier avant de committer :

```bash
rtk grep -n "query_marches" src/pages/observatoire.py
```

Expected: aucun résultat (ou uniquement des commentaires).

- [ ] **Step 5: Smoke test**

Démarrer l'app et naviguer sur `/observatoire`, vérifier à la main que :

- Les cartes s'affichent.
- Un filtre année se propage.
- Un filtre acheteur par SIRET partiel fonctionne.
- Un filtre département (multi-valeur) fonctionne.
- Un filtre montant_min fonctionne.
- Le bouton « Télécharger au format Excel » génère un fichier non vide.
- Le bouton « Voir les données » ouvre l'offcanvas et peuple la table.

Run: `python run.py`

Expected: app démarre sans erreur ; les filtres se comportent comme avant.

- [ ] **Step 6: Commit**

```bash
rtk pre-commit run --files src/pages/observatoire.py
rtk git add src/pages/observatoire.py
rtk git commit -m "refactor(observatoire): appelants utilisent la nouvelle signature (#72)"
```

---

## Task 9: Test d'intégration — `prepare_dashboard_data` sur `tests/test.parquet`

**Files:**

- Create: `tests/test_prepare_dashboard_data.py`

- [ ] **Step 1: Write the failing test**

Le but : vérifier que la fonction s'exécute réellement contre DuckDB, retourne une `pl.DataFrame`, et applique bien les filtres simples. `conftest.py` construit `tests/test.parquet` avec un jeu de données d'une ligne : acheteur_id `123`, acheteur_departement_code `75`, dateNotification `2025-01-01`, montant `10`.

Create `tests/test_prepare_dashboard_data.py`:

```python
import polars as pl


def test_returns_dataframe_with_year_filter():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(dashboard_year="2025")
    assert isinstance(dff, pl.DataFrame)
    assert dff.height == 1


def test_year_mismatch_returns_empty():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(dashboard_year="2024")
    assert isinstance(dff, pl.DataFrame)
    assert dff.height == 0


def test_acheteur_id_partial_match():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(
        dashboard_year="2025",
        dashboard_acheteur_id="12",
    )
    assert dff.height == 1


def test_departement_in_clause():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(
        dashboard_year="2025",
        dashboard_acheteur_departement_code=["75", "92"],
    )
    assert dff.height == 1


def test_montant_min_above_value_excludes_row():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(
        dashboard_year="2025",
        dashboard_montant_min=1000,
    )
    assert dff.height == 0
```

- [ ] **Step 2: Run the test**

Run: `rtk pytest tests/test_prepare_dashboard_data.py -v`
Expected: PASS (5 tests).

- [ ] **Step 3: Commit**

```bash
rtk pre-commit run --files tests/test_prepare_dashboard_data.py
rtk git add tests/test_prepare_dashboard_data.py
rtk git commit -m "test(observatoire): intégration DuckDB pour prepare_dashboard_data (#72)"
```

---

## Task 10: Vérification finale

**Files:** (aucune modification)

- [ ] **Step 1: Run the full test suite**

Run: `rtk pytest -v`
Expected: tous les tests unitaires passent. Les tests Selenium peuvent échouer si Chrome n'est pas disponible — ce n'est pas bloquant s'ils étaient déjà rouges avant.

- [ ] **Step 2: Check for leftover references**

Run: `rtk grep -rn "prepare_dashboard_data(lff" src/ tests/`
Expected: aucun résultat (plus d'appels avec l'ancienne signature).

Run: `rtk grep -rn "query_marches().lazy()" src/`
Expected: aucun résultat (ou uniquement dans `src/utils/table.py:prepare_table_data` pour le fallback).

- [ ] **Step 3: Confirm `datetime`/`timedelta` in data.py if needed**

Run: `rtk grep -n "datetime\|timedelta" src/utils/data.py`

Si aucune occurrence hors imports, vérifier que les imports inutiles ont bien été retirés dans Task 7.

- [ ] **Step 4: Manual timing sanity check (optionnel)**

Si possible, comparer informellement le temps de `_compute_dashboard_children` sur un filtre sélectif (ex. un département) avant/après. Pas de benchmark formel attendu.

- [ ] **Step 5: Push (manuel, à l'initiative de l'utilisateur)**

Conformément aux consignes projet, ne jamais `git push`. Laisser l'utilisateur pousser la branche `feature/72_observatoire_duckdb_filters` et ouvrir la PR.
