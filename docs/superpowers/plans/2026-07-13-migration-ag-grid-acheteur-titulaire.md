# Migration AG Grid — `acheteur.py` + `titulaire.py` (Lot 2a) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer les `dash_table.DataTable` des pages `/acheteurs/<id>` et `/titulaires/<id>` par des grilles `dash-ag-grid`, en factorisant la logique commune dans un module partagé et en réutilisant au maximum l'infrastructure AG Grid du Lot 1 (`tableau.py`).

**Architecture:** Un nouveau module `src/utils/entity_grid.py` porte toute la logique de grille scopée à une entité (fonctions pures testables + une fabrique de callbacks appelée une fois par page). Chaque grille a un `id` **pattern-matching** (`{"type": "<org>-grid", "entity_id": ..., "year": ...}`) pour scoper la persistance du `filterModel` par fiche ; la disposition des colonnes (`columnState`) est persistée globalement dans un `dcc.Store` partagé. Le datasource, le reset, l'export filtré et le compteur passent par le moteur AST → SQL DuckDB du Lot 1 (`fetch_grid_page`, `export_dataframe`, `grid_column_defs`, `apply_persisted_layout`).

**Tech Stack:** Dash 4.4, dash-ag-grid 35.2.0, DuckDB, Polars, pytest + DashComposite/Selenium.

**Spec de référence:** `docs/superpowers/specs/2026-07-13-migration-ag-grid-acheteur-titulaire-design.md`

## Global Constraints

- Périmètre = **`acheteur.py` + `titulaire.py` uniquement**. Ne pas toucher `observatoire.py` (Lot 2b), `recherche.py`, `admin/liste.py`, `figures.make_table` (Lot 3), ni `tableau.py` (déjà migré — ses appels doivent rester fonctionnellement inchangés).
- **Dash 4.4** : `Input`/`State` en `MATCH` avec `Output` à id fixe est autorisé (relaxation Dash 4.2+). Un `Output` en `MATCH` exige toujours un `Input`/`State` en `MATCH` sur la même clé ; pour piloter la grille depuis un bouton à id fixe, utiliser `ALL` en `Output`/`State` (une seule grille présente à la fois).
- Imports internes toujours préfixés `src.` (ex. `src.utils.entity_grid`).
- **Thème "brique" du Lot 1 réutilisé** via `ag_grid()` (pas d'apparence de base non-thémée, pas de nouveau CSS).
- **Extensions rétro-compatibles du Lot 1** : `ag_grid()` et `export_dataframe()` gagnent des paramètres optionnels ; les appels existants de `tableau.py` doivent continuer à marcher **sans modification** (valeurs par défaut = comportement actuel).
- Sécurité : identifiants de colonnes validés contre `schema.names()` (déjà fait par `ast_to_sql`/`grid_column_defs`), valeurs **toujours** liées via `?` (jamais concaténées). Le scope entité (`entity_id`, année) passe **toujours** en paramètre lié, jamais concaténé dans le SQL.
- Lancer `pre-commit run --files <fichiers>` avant chaque `git add`/commit (hook prettier/ruff peut reformater — re-`git add` puis committer).
- Tests par fichier pendant le lot ; `uv run pytest` complet **uniquement** à la dernière tâche (cf. mémoire projet « full suite only at end »).
- Ne pas supprimer `filter_table_data`/`sort_table_data`/`prepare_table_data`/`clean_filters`/`filter_query_to_sql` : encore utilisés par `observatoire.py` et les Lots suivants. On les **débranche** seulement d'acheteur/titulaire.
- **Hors périmètre, à ne PAS migrer** : le sélecteur de colonnes (`make_column_picker`, composant `{page}_column_list`) reste un `dash_table.DataTable` — il est partagé avec `tableau.py` (lui aussi non migré sur ce point) ; le migrer toucherait `tableau.py` et sort du lot.

**Fonctions/objets réutilisables (ne pas réécrire) :**

- `src/db.py` : `schema` (pl.Schema), `query_marches(where_sql, params, columns, order_by, limit, offset)`, `count_marches(where_sql, params)`, `count_unique_marches(where_sql, params)`, `aggregate_marches(select_sql, where_sql, params, ...)`.
- `src/utils/grid.py` : `fetch_grid_page(filter_model, sort_model, start_row, end_row, base_where_sql="TRUE", base_params=()) -> (rows, total, total_unique)`, `grid_column_defs(hidden_columns=None)`, `apply_persisted_layout(defs, column_state)`, `export_dataframe(...)` (étendu en Task 1).
- `src/utils/table.py` : `postprocess_page(dff)`, `setup_table_columns(dff, hideable=True, exclude=None) -> (columns, tooltip)`, `add_links(dff)`, `get_default_hidden_columns(page)`, `write_styled_excel(df, buffer, worksheet="DECP")`, `COLUMNS` (= `schema.names()`).
- `src/figures.py` : `ag_grid(grid_id, column_defs, ...)` (paramétré en Task 2), `AG_GRID_LOCALE_FR`, `make_column_picker(page)`, `make_card(title, subtitle=None, fig=None, paragraphs=None, lg=6, xl=4)`, `DATA_SCHEMA`.
- `src/utils/frontend.py` : `get_button_properties(count) -> (disabled, children, title)` (état du bouton de téléchargement selon le seuil de 65 000 lignes), `DROPDOWN_LABELS_FR`.
- `src/utils/tracking.py` : `track_search(query, source)`.

---

## File Structure

- **Modify** `src/utils/grid.py` — étendre `export_dataframe()` avec `base_where_sql`/`base_params`.
- **Modify** `src/figures.py` — paramétrer `ag_grid()` (id dict + `persisted_props`) ; ajouter `get_top_org_ag_grid()`.
- **Create** `src/utils/entity_grid.py` — fonctions pures de grille scopée + `register_entity_grid_callbacks(org_type)`.
- **Create** `tests/test_entity_grid.py` — tests unitaires des fonctions pures.
- **Modify** `src/pages/acheteur.py` — `layout` → fonction, grille AG Grid via `entity_grid`, top 10 en AG Grid, suppression des callbacks DataTable.
- **Modify** `src/pages/titulaire.py` — idem acheteur.
- **Modify** `tests/test_main.py` — sélecteurs AG Grid (`test_002_filter_persistence`) ; vérifier `test_003_tableau_download`.

---

## Task 1: Étendre `export_dataframe()` avec le scope de base

**Files:**

- Modify: `src/utils/grid.py:71-85`
- Test: `tests/test_grid.py`

**Interfaces:**

- Produces: `export_dataframe(filter_model, sort_model, hidden_columns, base_where_sql="TRUE", base_params=()) -> pl.DataFrame`

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter dans `tests/test_grid.py` :

```python
def test_export_dataframe_applies_base_scope():
    """base_where_sql restreint l'export à un sous-ensemble (ex. un acheteur),
    en plus du filterModel — utilisé par acheteur.py/titulaire.py (#41)."""
    # Récupère un acheteur_id présent dans le jeu de test.
    unscoped = export_dataframe(None, None, hidden_columns=[])
    assert unscoped.height > 0
    an_acheteur = unscoped["acheteur_id"][0]

    scoped = export_dataframe(
        None,
        None,
        hidden_columns=[],
        base_where_sql="acheteur_id = ?",
        base_params=(an_acheteur,),
    )
    assert scoped.height > 0
    assert scoped.height <= unscoped.height
    assert set(scoped["acheteur_id"].to_list()) == {an_acheteur}
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_grid.py::test_export_dataframe_applies_base_scope -v`
Expected: FAIL — `TypeError: export_dataframe() got an unexpected keyword argument 'base_where_sql'`.

- [ ] **Step 3: Implémenter l'extension**

Remplacer `export_dataframe` dans `src/utils/grid.py` par :

```python
def export_dataframe(
    filter_model,
    sort_model,
    hidden_columns,
    base_where_sql: str = "TRUE",
    base_params: tuple = (),
) -> pl.DataFrame:
    """Renvoie les lignes filtrées/triées pour l'export Excel.

    Colonnes masquées exclues, valeurs brutes (non post-traitées HTML).
    `base_where_sql`/`base_params` scopent l'export à un sous-ensemble (ex. un
    acheteur/titulaire) — combinés en `(base) AND (filtre)`, comme
    `fetch_grid_page`. Par défaut `TRUE` → comportement inchangé pour tableau.py.
    """
    ast = filtermodel_to_ast(filter_model, schema)
    filter_sql, filter_params = ast_to_sql(ast, schema)
    where_sql = f"({base_where_sql}) AND ({filter_sql})"
    params = [*base_params, *filter_params]
    order_by = sort_model_to_sql(sort_model, schema) or None
    visible = [c for c in schema.names() if c not in set(hidden_columns or [])]
    return query_marches(
        where_sql=where_sql,
        params=params,
        columns=visible,
        order_by=order_by,
    )
```

- [ ] **Step 4: Lancer les tests du fichier, vérifier le succès + non-régression**

Run: `uv run pytest tests/test_grid.py -v`
Expected: PASS pour tous (dont `test_export_dataframe_excludes_hidden_columns` et `test_export_dataframe_applies_filter`, qui appellent sans les nouveaux args → défaut `TRUE`).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/utils/grid.py tests/test_grid.py
git add src/utils/grid.py tests/test_grid.py
git commit -m "feat(grid): export_dataframe scopable par base_where_sql/base_params (#41)"
```

---

## Task 2: Paramétrer `ag_grid()` (id dict + persisted_props)

**Files:**

- Modify: `src/figures.py:1101-1162`
- Test: `tests/test_figures.py`

**Interfaces:**

- Produces: `ag_grid(grid_id: str | dict, column_defs: list[dict], persisted_props=("filterModel", "columnState"), persistence=True) -> dag.AgGrid`

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `tests/test_figures.py` :

```python
def test_ag_grid_accepts_dict_id_and_custom_persisted_props():
    """Grille entité : id pattern-matching + persistance limitée au filterModel
    (columnState géré via un store partagé, pas la persistance native)."""
    from src.figures import ag_grid

    gid = {"type": "acheteur-grid", "entity_id": "123", "year": "Toutes les années"}
    grid = ag_grid(gid, [], persisted_props=["filterModel"])

    assert grid.id == gid
    assert list(grid.persisted_props) == ["filterModel"]
    assert grid.persistence is True


def test_ag_grid_defaults_unchanged_for_tableau():
    """Sans args de persistance, comportement identique au Lot 1 (tableau.py)."""
    from src.figures import ag_grid

    grid = ag_grid("tableau_grid", [])

    assert grid.id == "tableau_grid"
    assert list(grid.persisted_props) == ["filterModel", "columnState"]
    assert grid.persistence is True
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/test_figures.py::test_ag_grid_accepts_dict_id_and_custom_persisted_props -v`
Expected: FAIL — `TypeError: ag_grid() got an unexpected keyword argument 'persisted_props'`.

- [ ] **Step 3: Implémenter la paramétrisation**

Dans `src/figures.py`, modifier la signature et les deux lignes de persistance de `ag_grid()` :

```python
def ag_grid(
    grid_id: "str | dict",
    column_defs: list[dict],
    persisted_props=("filterModel", "columnState"),
    persistence: bool = True,
) -> "dag.AgGrid":
```

Et, dans le `return dag.AgGrid(...)`, remplacer les lignes finales :

```python
        persistence=persistence,
        persistence_type="local",
        persisted_props=list(persisted_props),
    )
```

(Le reste du corps — `dashGridOptions`, thème, `style`, etc. — est inchangé. `id=grid_id` accepte déjà str ou dict.)

- [ ] **Step 4: Lancer les tests, vérifier le succès + non-régression**

Run: `uv run pytest tests/test_figures.py -v`
Expected: PASS pour tous (dont les tests existants `test_ag_grid_locale_text_*`, `test_ag_grid_keeps_base_appearance`, `test_ag_grid_always_shows_horizontal_scroll`).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/figures.py tests/test_figures.py
git add src/figures.py tests/test_figures.py
git commit -m "feat(figures): ag_grid() paramétrable (id dict + persisted_props) (#41)"
```

---

## Task 3: `get_top_org_ag_grid()` — tableau « top 10 » en AG Grid

**Files:**

- Modify: `src/figures.py` (ajouter la fonction près de `get_top_org_table`, ~ligne 1062)
- Test: `tests/test_figures.py`

**Interfaces:**

- Consumes: `setup_table_columns`, `add_links` (src.utils.table) ; `ag_grid` (Task 2).
- Produces: `get_top_org_ag_grid(data, org_type, extra_columns, filters=True) -> dag.AgGrid | html.Div` — même rôle que `get_top_org_table`, mais rend une AG Grid client-side (row model par défaut, `rowData` fournie). Renvoie `html.Div()` si vide/erreur.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `tests/test_figures.py` :

```python
def test_get_top_org_ag_grid_returns_grid_with_rowdata():
    """Le top 10 devient une AG Grid client-side (rowData directe, pas de
    getRowsRequest server-side)."""
    import dash_ag_grid as dag

    from src.db import query_marches
    from src.figures import get_top_org_ag_grid

    lff = query_marches("TRUE", (), columns=None).lazy()
    grid = get_top_org_ag_grid(lff, "titulaire", ["titulaire_distance"])

    assert isinstance(grid, dag.AgGrid)
    assert grid.rowData is not None and len(grid.rowData) > 0
    # Colonne d'agrégat présente ; colonnes définies.
    assert any(c.get("field") == "Attributions" for c in grid.columnDefs)
    # Pas de persistance (petit tableau statique, régénéré à chaque fiche).
    assert grid.persistence in (False, None)


def test_get_top_org_ag_grid_empty_returns_div():
    """Données vides → html.Div() (parité get_top_org_table)."""
    import polars as pl
    from dash import html

    from src.figures import get_top_org_ag_grid

    empty = pl.DataFrame(
        {"uid": [], "titulaire_id": [], "titulaire_nom": [], "titulaire_distance": []}
    ).lazy()
    out = get_top_org_ag_grid(empty, "titulaire", ["titulaire_distance"])
    assert isinstance(out, html.Div)
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/test_figures.py::test_get_top_org_ag_grid_returns_grid_with_rowdata -v`
Expected: FAIL — `ImportError: cannot import name 'get_top_org_ag_grid'`.

- [ ] **Step 3: Implémenter la fonction**

Dans `src/figures.py`, ajouter (juste après `get_top_org_table`). Elle reprend le pré-traitement de `get_top_org_table` (group-by → `Attributions`, `add_links`) puis produit des `columnDefs` AG Grid depuis les colonnes calculées, avec `cellRenderer:"markdown"` sur les colonnes-liens (nom) :

```python
def get_top_org_ag_grid(data, org_type: str, extra_columns: list, filters: bool = True):
    """Top N acheteurs/titulaires en AG Grid client-side (rowData directe).

    Remplace get_top_org_table (dash_table) : même agrégation, mais rendu AG
    Grid (thème brique, liens markdown). Renvoie html.Div() si vide/erreur.
    """
    if isinstance(data, pl.LazyFrame):
        lff = data
    else:
        lff = pl.LazyFrame(data, strict=False, infer_schema_length=5000)

    extra = list(extra_columns)
    if org_type == "titulaire":
        extra.append("titulaire_typeIdentifiant")
    columns = ["uid", f"{org_type}_id", f"{org_type}_nom"] + extra

    lff = lff.select(columns)
    lff = lff.group_by([f"{org_type}_id", f"{org_type}_nom"] + extra).agg(
        pl.len().alias("Attributions")
    )
    lff = lff.sort(by="Attributions", descending=True, nulls_last=True)
    lff = lff.cast(pl.String)
    lff = lff.fill_null("")

    try:
        dff: pl.DataFrame = lff.collect(engine="streaming")
    except ColumnNotFoundError:
        logger.warning(f"get_top_org_ag_grid: column not found. {lff.collect_schema()}")
        return html.Div()

    if dff.height == 0:
        return html.Div()

    dff = add_links(dff)

    # columnDefs : on masque l'id (lien porté par le nom), on rend le nom en
    # markdown (HTML <a>), on cache les colonnes techniques *_tooltip.
    id_col = f"{org_type}_id"
    nom_col = f"{org_type}_nom"
    link_cols = {nom_col}
    column_defs = []
    for col in dff.columns:
        if col == id_col or col.endswith("_tooltip"):
            continue
        col_def = {
            "field": col,
            "headerName": DATA_SCHEMA.get(col, {}).get("title", col),
            "sortable": True,
            "filter": "agTextColumnFilter" if filters else False,
        }
        if col in link_cols:
            col_def["cellRenderer"] = "markdown"
            col_def["flex"] = 1
        column_defs.append(col_def)

    # ag_grid() du Lot 1 est server-side (rowModelType="infinite", pas de
    # rowData) : inadapté au top 10, qui est client-side. On construit donc une
    # AG Grid client-side directe, en réutilisant le thème + localeText.
    return dag.AgGrid(
        id=f"top10_{org_type}",
        columnDefs=column_defs,
        rowData=dff.to_dicts(),
        dangerously_allow_code=True,  # rend le HTML <a> des cellules liens
        columnSize="responsiveSizeToFit",
        dashGridOptions={
            "domLayout": "autoHeight",  # OK ici : row model client-side
            "pagination": True,
            "paginationPageSize": 10,
            "suppressCellFocus": True,
            "localeText": AG_GRID_LOCALE_FR,
            "theme": {
                "function": (
                    "themeQuartz.withParams({"
                    "accentColor: 'rgb(179, 56, 33)',"
                    "headerTextColor: 'white',"
                    "headerBackgroundColor: 'rgb(179, 56, 33)',"
                    "oddRowBackgroundColor: 'rgba(255, 240, 240, 0.4)',"
                    "borderColor: '#ccc',"
                    "fontFamily: 'Inter, sans-serif',"
                    "fontSize: 16"
                    "})"
                )
            },
        },
        style={"width": "100%"},
        persistence=False,
    )
```

(Vérifier que `import dash_ag_grid as dag` est déjà présent en tête de `src/figures.py` — c'est le cas. `add_links`, `setup_table_columns`, `ColumnNotFoundError`, `DATA_SCHEMA`, `logger`, `AG_GRID_LOCALE_FR` sont déjà importés/définis dans `src/figures.py` puisque `get_top_org_table` les utilise.)

> Note : `setup_table_columns` n'est pas strictement nécessaire ici (les columnDefs sont dérivés directement de `dff.columns`), mais l'agrégation reprend fidèlement celle de `get_top_org_table`. Garder `get_top_org_table` en place ce lot (encore utilisé par `observatoire.py`) ; ne le supprimer qu'au Lot 2b/3.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/test_figures.py::test_get_top_org_ag_grid_returns_grid_with_rowdata tests/test_figures.py::test_get_top_org_ag_grid_empty_returns_div -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/figures.py tests/test_figures.py
git add src/figures.py tests/test_figures.py
git commit -m "feat(figures): get_top_org_ag_grid (top 10 en AG Grid client-side) (#41)"
```

---

## Task 4: `entity_grid.py` — fonctions pures de grille scopée

**Files:**

- Create: `src/utils/entity_grid.py`
- Test: `tests/test_entity_grid.py`

**Interfaces:**

- Consumes: `fetch_grid_page`, `export_dataframe` (Task 1), `grid_column_defs`, `apply_persisted_layout` (grid.py) ; `ag_grid` (Task 2) ; `schema` (src.db).
- Produces (consommées en Task 5/6/7) :

  - `entity_scope(org_type: str, entity_id: str, year) -> tuple[str, list]`
  - `entity_grid_column_defs(hidden_columns, column_state) -> list[dict]`
  - `fetch_entity_page(org_type, entity_id, year, request: dict) -> tuple[dict, int, int]` — renvoie `({"rowData": ..., "rowCount": total}, total, total_unique)`
  - `export_entity_dataframe(org_type, entity_id, year, filter_model, column_state) -> pl.DataFrame`
  - `clear_sort(column_state) -> list[dict]`
  - `build_entity_grid(org_type, entity_id, year, hidden_columns, column_state) -> dag.AgGrid`
  - `GRID_TYPE = "{org_type}-grid"` construit via `grid_type(org_type)`

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_entity_grid.py` :

```python
import dash_ag_grid as dag
import pytest

import src.app  # noqa: F401  # instancie l'app → schema chargé
from src.db import query_marches
from src.utils.entity_grid import (
    build_entity_grid,
    clear_sort,
    entity_grid_column_defs,
    entity_scope,
    export_entity_dataframe,
    fetch_entity_page,
    grid_type,
)


def _an_acheteur_id():
    return query_marches("TRUE", (), columns=["acheteur_id"])["acheteur_id"][0]


def test_entity_scope_acheteur():
    where, params = entity_scope("acheteur", "S123", None)
    assert where == "acheteur_id = ?"
    assert params == ["S123"]


def test_entity_scope_titulaire_requires_siret():
    where, params = entity_scope("titulaire", "S123", None)
    assert "titulaire_id = ?" in where
    assert "titulaire_typeIdentifiant = 'SIRET'" in where
    assert params == ["S123"]


def test_entity_scope_with_year_adds_bound_param():
    where, params = entity_scope("acheteur", "S123", "2025")
    assert 'YEAR("dateNotification") = ?' in where
    assert params == ["S123", 2025]


def test_entity_scope_toutes_les_annees_no_year_filter():
    where, params = entity_scope("acheteur", "S123", "Toutes les années")
    assert "YEAR" not in where
    assert params == ["S123"]


def test_fetch_entity_page_is_scoped():
    ach = _an_acheteur_id()
    request = {"startRow": 0, "endRow": 50, "filterModel": None, "sortModel": None}
    response, total, total_unique = fetch_entity_page("acheteur", ach, None, request)
    assert total > 0
    assert total_unique > 0
    assert response["rowCount"] == total
    assert len(response["rowData"]) <= 50
    # Toutes les lignes appartiennent à l'acheteur scopé.
    assert all(str(r["acheteur_id"]).find(str(ach)) != -1 for r in response["rowData"])


def test_fetch_entity_page_none_request():
    from dash import no_update

    out = fetch_entity_page("acheteur", "S123", None, None)
    assert out == (no_update, no_update, no_update)


def test_export_entity_dataframe_scoped():
    ach = _an_acheteur_id()
    df = export_entity_dataframe("acheteur", ach, None, None, None)
    assert df.height > 0
    assert set(df["acheteur_id"].to_list()) == {ach}


def test_clear_sort_preserves_width_and_order():
    column_state = [
        {"colId": "objet", "width": 400, "sort": "asc", "sortIndex": 0},
        {"colId": "montant", "width": 150, "sort": "desc", "sortIndex": 1},
    ]
    cleared = clear_sort(column_state)
    assert all(c["sort"] is None and c["sortIndex"] is None for c in cleared)
    assert cleared[0]["width"] == 400 and cleared[0]["colId"] == "objet"
    assert cleared[1]["width"] == 150


def test_clear_sort_empty():
    assert clear_sort(None) == []


def test_entity_grid_column_defs_applies_persisted_layout():
    defs = entity_grid_column_defs(hidden_columns=[], column_state=[{"colId": "montant", "width": 999}])
    by_field = {d["field"]: d for d in defs}
    assert by_field["montant"]["width"] == 999


def test_build_entity_grid_has_pattern_matching_id_and_filter_only_persistence():
    grid = build_entity_grid("acheteur", "S123", "Toutes les années", [], None)
    assert isinstance(grid, dag.AgGrid)
    assert grid.id == {"type": "acheteur-grid", "entity_id": "S123", "year": "Toutes les années"}
    assert list(grid.persisted_props) == ["filterModel"]


def test_grid_type():
    assert grid_type("acheteur") == "acheteur-grid"
    assert grid_type("titulaire") == "titulaire-grid"
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/test_entity_grid.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.utils.entity_grid'`.

- [ ] **Step 3: Implémenter le module**

Créer `src/utils/entity_grid.py` :

```python
"""Logique de grille AG Grid scopée à une entité (acheteur/titulaire).

Factorise ce qui est commun aux pages acheteur.py et titulaire.py :
- scope SQL (WHERE acheteur_id/titulaire_id + année),
- datasource server-side (réutilise fetch_grid_page du Lot 1),
- export Excel filtré (réutilise export_dataframe),
- columnDefs + réapplication de la disposition persistée,
- fabrique de grille à id pattern-matching (persistance filterModel par fiche).

Les callbacks Dash sont enregistrés par register_entity_grid_callbacks()
(cf. module séparé de wiring) ; ici, seules des fonctions pures testables.
"""

import dash_ag_grid as dag
from dash import no_update

from src.figures import (
    AG_GRID_LOCALE_FR,  # noqa: F401  (réexport pratique)
    ag_grid,
)
from src.utils.grid import (
    apply_persisted_layout,
    export_dataframe,
    fetch_grid_page,
    grid_column_defs,
)

_TOUTES = "Toutes les années"


def grid_type(org_type: str) -> str:
    """Valeur de la clé `type` de l'id pattern-matching de la grille."""
    return f"{org_type}-grid"


def entity_scope(org_type: str, entity_id: str, year) -> tuple[str, list]:
    """WHERE SQL + params liés scopant les requêtes à cette entité (+ année).

    Reproduit _acheteur_scope/_titulaire_scope des pages, unifié par org_type.
    """
    if org_type == "titulaire":
        where_sql = "titulaire_id = ? AND titulaire_typeIdentifiant = 'SIRET'"
    else:
        where_sql = "acheteur_id = ?"
    params: list = [entity_id]
    if year and year != _TOUTES:
        where_sql += ' AND YEAR("dateNotification") = ?'
        params.append(int(year))
    return where_sql, params


def _sort_model_from_column_state(column_state) -> list:
    """Extrait le sortModel AG Grid d'un columnState (comme tableau.download_data)."""
    return [
        {"colId": c["colId"], "sort": c["sort"]}
        for c in (column_state or [])
        if c.get("sort")
    ]


def entity_grid_column_defs(hidden_columns, column_state) -> list[dict]:
    """columnDefs du schéma DECP + disposition (largeur/ordre) persistée."""
    defs = grid_column_defs(hidden_columns)
    return apply_persisted_layout(defs, column_state)


def fetch_entity_page(org_type, entity_id, year, request) -> tuple:
    """Datasource server-side scopé pour la grille entité.

    Renvoie ({"rowData": ..., "rowCount": total}, total, total_unique).
    """
    if request is None:
        return no_update, no_update, no_update
    base_where_sql, base_params = entity_scope(org_type, entity_id, year)
    rows, total, total_unique = fetch_grid_page(
        request.get("filterModel") or None,
        request.get("sortModel") or None,
        request.get("startRow", 0),
        request.get("endRow", 100),
        base_where_sql=base_where_sql,
        base_params=tuple(base_params),
    )
    return {"rowData": rows, "rowCount": total}, total, total_unique


def export_entity_dataframe(org_type, entity_id, year, filter_model, column_state):
    """DataFrame filtré/trié (état courant de la grille) pour l'export Excel."""
    base_where_sql, base_params = entity_scope(org_type, entity_id, year)
    sort_model = _sort_model_from_column_state(column_state)
    hidden_columns = [c["colId"] for c in (column_state or []) if c.get("hide")]
    return export_dataframe(
        filter_model,
        sort_model,
        hidden_columns,
        base_where_sql=base_where_sql,
        base_params=tuple(base_params),
    )


def clear_sort(column_state) -> list[dict]:
    """columnState avec le tri effacé (sort/sortIndex à None), largeur/ordre/
    épinglage préservés. Approche #47-safe de tableau.reset_view."""
    return [{**col, "sort": None, "sortIndex": None} for col in (column_state or [])]


def build_entity_grid(org_type, entity_id, year, hidden_columns, column_state):
    """Grille AG Grid à id pattern-matching, scopée à (entité, année).

    L'id inclut entity_id + year → une entrée localStorage de filterModel par
    fiche/année (persistance native scopée). columnState n'est PAS persisté
    nativement (géré par un store global partagé) : persisted_props=["filterModel"].
    """
    grid_id = {"type": grid_type(org_type), "entity_id": entity_id, "year": year or _TOUTES}
    defs = entity_grid_column_defs(hidden_columns, column_state)
    return ag_grid(grid_id, defs, persisted_props=["filterModel"])
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/test_entity_grid.py -v`
Expected: PASS pour les 12 tests.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/utils/entity_grid.py tests/test_entity_grid.py
git add src/utils/entity_grid.py tests/test_entity_grid.py
git commit -m "feat(entity_grid): fonctions pures de grille scopée acheteur/titulaire (#41)"
```

---

## Task 5: `register_entity_grid_callbacks()` — wiring des callbacks partagés

**Files:**

- Modify: `src/utils/entity_grid.py` (ajouter la fonction de registration)
- Test: `tests/test_entity_grid.py` (test de fumée : la registration ne lève pas)

**Interfaces:**

- Consumes: fonctions pures de Task 4.
- Produces: `register_entity_grid_callbacks(org_type: str) -> None` — enregistre, pour la page `org_type`, les callbacks : datasource (grille MATCH → stores totaux fixes), rebuild de grille (nav/année/colonnes masquées), persistance columnState (grille → store partagé), reset (bouton → grille ALL), export filtré (bouton → Download), meta (totaux → nb_rows + état bouton export filtré).
- **Ids conventionnels attendus par page** (créés en Task 6/7) : `f"{org_type}_url"` (dcc.Location), `f"{org_type}_year"` (dropdown), `f"{org_type}-grid-container"` (html.Div hôte), `f"{org_type}-total"`, `f"{org_type}-total-unique"` (dcc.Store), `f"{org_type}-hidden-columns"` (dcc.Store), `"entity-grid-columns-state"` (dcc.Store partagé), `f"{org_type}_nb_rows"` (Span), `f"btn-{org_type}-reset"`, `f"btn-download-filtered-data-{org_type}"`, `f"{org_type}-download-filtered-data"` (dcc.Download).

- [ ] **Step 1: Écrire le test de fumée qui échoue**

Ajouter dans `tests/test_entity_grid.py` :

```python
def test_register_entity_grid_callbacks_smoke():
    """La registration ne lève pas (les ids/patterns sont valides pour Dash)."""
    import src.app  # noqa: F401
    from src.utils.entity_grid import register_entity_grid_callbacks

    # Ne doit pas lever ; idempotence non requise (appelée une fois par page).
    register_entity_grid_callbacks("acheteur")
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/test_entity_grid.py::test_register_entity_grid_callbacks_smoke -v`
Expected: FAIL — `ImportError: cannot import name 'register_entity_grid_callbacks'`.

- [ ] **Step 3: Implémenter la registration**

Ajouter en tête de `src/utils/entity_grid.py` les imports Dash nécessaires :

```python
from dash import ALL, MATCH, Input, Output, State, callback, ctx, dcc
```

Puis ajouter à la fin du module :

```python
def register_entity_grid_callbacks(org_type: str) -> None:
    """Enregistre les callbacks de grille pour la page org_type (acheteur/titulaire).

    Appelée une fois par page. Utilise des closures sur org_type ; toute la
    logique délègue aux fonctions pures ci-dessus (testées en Task 4).
    """
    gtype = grid_type(org_type)

    # 1) Datasource server-side. Input MATCH (grille) → Output MATCH
    #    (getRowsResponse) + Outputs fixes (stores totaux). Autorisé en Dash 4.4.
    @callback(
        Output({"type": gtype, "entity_id": MATCH, "year": MATCH}, "getRowsResponse"),
        Output(f"{org_type}-total", "data"),
        Output(f"{org_type}-total-unique", "data"),
        Input({"type": gtype, "entity_id": MATCH, "year": MATCH}, "getRowsRequest"),
        prevent_initial_call=True,
    )
    def _get_rows(request):
        gid = ctx.triggered_id  # {"type", "entity_id", "year"}
        if request is None or gid is None:
            return no_update, no_update, no_update
        if request.get("filterModel") and request.get("startRow", 0) == 0:
            import json

            from src.utils.tracking import track_search

            track_search(json.dumps(request["filterModel"]), org_type)
        return fetch_entity_page(org_type, gid["entity_id"], gid["year"], request)

    # 2) (Re)construit la grille au changement de fiche (URL), d'année, ou de
    #    colonnes masquées. Le remontage réinitialise le filterModel (accepté
    #    au changement de fiche/année) ; pour les colonnes masquées voir §3bis.
    @callback(
        Output(f"{org_type}-grid-container", "children"),
        Input(f"{org_type}_url", "pathname"),
        Input(f"{org_type}_year", "value"),
        State(f"{org_type}-hidden-columns", "data"),
        State("entity-grid-columns-state", "data"),
    )
    def _build_grid(pathname, year, hidden_columns, column_state):
        from src.utils.table import get_default_hidden_columns

        entity_id = (pathname or "").split("/")[-1]
        if hidden_columns is None:
            hidden_columns = get_default_hidden_columns(org_type)
        return build_entity_grid(org_type, entity_id, year, hidden_columns, column_state)

    # 3) Persiste columnState (largeur/ordre/tri/visibilité) dans le store global
    #    partagé. Input MATCH (grille) → Output fixe (store). Autorisé Dash 4.4.
    @callback(
        Output("entity-grid-columns-state", "data"),
        Input({"type": gtype, "entity_id": MATCH, "year": MATCH}, "columnState"),
        prevent_initial_call=True,
    )
    def _persist_column_state(column_state):
        return column_state or no_update

    # 3bis) Colonnes masquées → columnDefs in-place (préserve le filtre courant,
    #       contrairement au remontage). Input fixe → Output ALL (grille unique).
    @callback(
        Output({"type": gtype, "entity_id": ALL, "year": ALL}, "columnDefs"),
        Input(f"{org_type}-hidden-columns", "data"),
        State({"type": gtype, "entity_id": ALL, "year": ALL}, "columnState"),
        prevent_initial_call=True,
    )
    def _apply_hidden_columns(hidden_columns, column_states):
        from src.utils.table import get_default_hidden_columns

        if hidden_columns is None:
            hidden_columns = get_default_hidden_columns(org_type)
        # ALL → listes (une entrée par grille présente, ici 0 ou 1).
        return [
            entity_grid_column_defs(hidden_columns, cs) for cs in (column_states or [])
        ]

    # 4) Reset : efface filtres ET tris (columnState avec sort=None). Bouton fixe
    #    → grille ALL.
    @callback(
        Output({"type": gtype, "entity_id": ALL, "year": ALL}, "filterModel"),
        Output({"type": gtype, "entity_id": ALL, "year": ALL}, "columnState"),
        Input(f"btn-{org_type}-reset", "n_clicks"),
        State({"type": gtype, "entity_id": ALL, "year": ALL}, "columnState"),
        prevent_initial_call=True,
    )
    def _reset(_n, column_states):
        cleared = [clear_sort(cs) for cs in (column_states or [])]
        return [{} for _ in cleared], cleared

    # 5) Export filtré (état courant de la grille). Bouton fixe → Download fixe,
    #    lit filterModel/columnState de la grille via ALL (state).
    @callback(
        Output(f"{org_type}-download-filtered-data", "data"),
        Input(f"btn-download-filtered-data-{org_type}", "n_clicks"),
        State(f"{org_type}_url", "pathname"),
        State(f"{org_type}_year", "value"),
        State(f"{org_type}_nom", "children"),
        State({"type": gtype, "entity_id": ALL, "year": ALL}, "filterModel"),
        State({"type": gtype, "entity_id": ALL, "year": ALL}, "columnState"),
        prevent_initial_call=True,
    )
    def _download_filtered(_n, pathname, year, nom, filter_models, column_states):
        import datetime as _dt

        from src.utils.table import write_styled_excel

        entity_id = (pathname or "").split("/")[-1]
        filter_model = (filter_models or [None])[0]
        column_state = (column_states or [None])[0]
        if filter_model:
            import json

            from src.utils.tracking import track_search

            track_search(json.dumps(filter_model), f"{org_type} download")
        df = export_entity_dataframe(org_type, entity_id, year, filter_model, column_state)

        def to_bytes(buffer):
            write_styled_excel(df, buffer)

        date = _dt.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        label = nom if isinstance(nom, str) else org_type
        return dcc.send_bytes(to_bytes, filename=f"decp_filtrées_{label}_{date}.xlsx")

    # 6) Meta : "X marchés (Y lignes)" + état du bouton d'export filtré (seuil 65k).
    @callback(
        Output(f"{org_type}_nb_rows", "children"),
        Output(f"btn-download-filtered-data-{org_type}", "disabled"),
        Output(f"btn-download-filtered-data-{org_type}", "children"),
        Output(f"btn-download-filtered-data-{org_type}", "title"),
        Input(f"{org_type}-total", "data"),
        Input(f"{org_type}-total-unique", "data"),
    )
    def _meta(total, total_unique):
        from src.utils.frontend import get_button_properties
        from src.utils.table import format_number

        total = total or 0
        total_unique = total_unique or 0
        nb_rows = (
            f"{format_number(total_unique) or 0} marchés "
            f"({format_number(total) or 0} lignes)"
        )
        disabled, children, title = get_button_properties(total)
        return nb_rows, disabled, children, title
```

> **Note :** `format_number` est dans `src/utils/table.py` (importé en local pour éviter les cycles). Vérifier lors de l'implémentation que `get_button_properties(count)` renvoie bien `(disabled, children, title)` (cf. `acheteur.update_download_button_acheteur`). Si sa signature/retour diffère, adapter l'appel dans `_meta` en conséquence.

- [ ] **Step 4: Lancer le test de fumée, vérifier le succès**

Run: `uv run pytest tests/test_entity_grid.py::test_register_entity_grid_callbacks_smoke -v`
Expected: PASS (aucune exception de validation Dash sur les patterns d'ids).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/utils/entity_grid.py tests/test_entity_grid.py
git add src/utils/entity_grid.py tests/test_entity_grid.py
git commit -m "feat(entity_grid): register_entity_grid_callbacks (datasource/reset/export/meta) (#41)"
```

---

## Task 6: Migrer `acheteur.py` vers AG Grid

**Files:**

- Modify: `src/pages/acheteur.py`
- Test: manuel (Selenium couvert en Task 8) ; vérifier l'import de la page.

**Interfaces:**

- Consumes: `entity_grid.register_entity_grid_callbacks`, `entity_grid.build_entity_grid` (indirect via le container), `figures.get_top_org_ag_grid`, helpers existants.

- [ ] **Step 1: Remplacer le composant table et les stores dans le layout**

Dans `src/pages/acheteur.py` :

1. **Imports** : retirer `DataTable` de l'import `src.figures` ; ajouter `get_top_org_ag_grid`. Retirer les imports devenus inutiles (`filter_table_data`, `sort_table_data`, `prepare_table_data`, `COLUMNS`, `get_default_hidden_columns` si plus utilisés localement — garder ceux encore référencés). Ajouter :

```python
from src.utils.entity_grid import register_entity_grid_callbacks
```

2. **Supprimer** le bloc `DATATABLE = html.Div(className="marches_table", children=DataTable(dtid="acheteur_datatable", ...))` (lignes ~71-85).

3. **Convertir `layout` en fonction** `def layout(acheteur_id=None, **kwargs):` qui retourne l'actuelle liste, avec ces changements dans le corps :
   - Conserver `dcc.Location(id="acheteur_url", ...)`, tous les composants d'infos/carte/stats/histogramme **inchangés**.
   - Ajouter, à côté de `dcc.Store(id="acheteur-hidden-columns", storage_type="local")` :

```python
    dcc.Store(id="acheteur-total"),
    dcc.Store(id="acheteur-total-unique"),
    dcc.Store(id="entity-grid-columns-state", storage_type="local"),
```

- Remplacer le `DATATABLE` (dernier enfant, ligne ~256) par le container hôte de la grille :

```python
    html.Div(id="acheteur-grid-container", className="marches_table"),
```

> `entity-grid-columns-state` est **partagé** avec titulaire.py. Il est déclaré dans les deux `layout()` : Dash tolère un même id de Store présent sur des pages différentes (une seule page montée à la fois). Ne PAS le déclarer dans un layout global.

- [ ] **Step 2: Supprimer les callbacks DataTable, enregistrer les callbacks de grille**

Dans `src/pages/acheteur.py`, **supprimer** les callbacks devenus obsolètes :

- `get_last_marches_data` (Output `acheteur_datatable.*`).
- `download_filtered_acheteur_data` (remplacé par le callback export de `register_entity_grid_callbacks`).
- le `clientside_callback` `clean_filters` + le `dcc.Store(id="filter-cleanup-trigger-acheteur")`.
- `store_hidden_columns` (Output `acheteur_datatable.hidden_columns`).
- `reset_view` (Output `acheteur_datatable.filter_query/sort_by`) — remplacé par le reset de la grille.

**Conserver inchangés** : `update_acheteur_infos`, `update_acheteur_map`, `update_acheteur_stats`, `update_download_button_acheteur`, `download_acheteur_data` (bouton « toutes les données »), `update_hidden_columns_from_checkboxes`, `toggle_acheteur_columns`, `update_acheteur_distance_histogram`.

**Corriger** `update_checkboxes_from_hidden_columns` : son `Input` pointe aujourd'hui vers `acheteur_datatable.hidden_columns` (prop qui disparaît avec la DataTable). Le rebrancher sur le **store** :

```python
@callback(
    Output("acheteur_column_list", "selected_rows"),
    Input("acheteur-hidden-columns", "data"),
    State("acheteur_column_list", "selected_rows"),  # pour éviter la boucle infinie
)
def update_checkboxes_from_hidden_columns(hidden_cols, current_checkboxes):
    hidden_cols = hidden_cols or get_default_hidden_columns("acheteur")
    visible_cols = [COLUMNS.index(col) for col in COLUMNS if col not in hidden_cols]
    return visible_cols
```

(Garder donc les imports `COLUMNS` et `get_default_hidden_columns` dans `acheteur.py`.)

**Migrer le top 10** : dans `get_top_titulaires`, remplacer `get_top_org_table(...)` par `get_top_org_ag_grid(...)` :

```python
@callback(
    Output(component_id="top10_titulaires", component_property="children"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def get_top_titulaires(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    table = get_top_org_ag_grid(
        query_marches(where_sql, params).lazy(), "titulaire", ["titulaire_distance"]
    )
    return make_card(fig=table, title="Top titulaires", lg=12, xl=12)
```

**Enregistrer les callbacks de grille** (une fois, au niveau module, après les définitions de callbacks) :

```python
register_entity_grid_callbacks("acheteur")
```

> `_acheteur_scope` reste utilisé par les callbacks conservés (carte, stats, download « toutes les données », top 10) — **ne pas le supprimer**. La logique de scope de la grille vit en double conceptuel dans `entity_grid.entity_scope`, mais les deux doivent rester cohérentes (même WHERE). C'est acceptable (le lot 3 pourra unifier).

- [ ] **Step 3: Vérifier que la page s'importe sans erreur**

Run: `uv run python -c "import src.app; import src.pages.acheteur; print('acheteur OK')"`
Expected: `acheteur OK` (aucune exception de validation Dash : ids en double, patterns invalides, Output dupliqués sans `allow_duplicate`).

> Si Dash signale un Output dupliqué (ex. `entity-grid-columns-state.data` ou un `columnDefs` piloté par deux callbacks), ajouter `allow_duplicate=True` au besoin et `prevent_initial_call=True`.

- [ ] **Step 4: Vérifier le rendu réel de la page (skill run)**

Lancer l'app et charger `/acheteurs/<un_id_présent_dans_test.parquet>`. Vérifier : la grille s'affiche, filtre multi-conditions (ET/OU + Contient) fonctionne, tri fonctionne, le compteur affiche « X marchés (Y lignes) », le bouton Réinitialiser vide filtres+tris, l'export filtré télécharge un fichier cohérent, le sélecteur de colonnes masque/affiche, le top 10 s'affiche en AG Grid.

> Utiliser le skill `run` (ou `uv run run.py`) ; ne pas cocher cette étape tant que la grille n'est pas vérifiée visuellement fonctionnelle.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/acheteur.py
git add src/pages/acheteur.py
git commit -m "feat(acheteur): migration du tableau des marchés vers AG Grid (#41)"
```

---

## Task 7: Migrer `titulaire.py` vers AG Grid

**Files:**

- Modify: `src/pages/titulaire.py`

**Interfaces:** identiques à Task 6, substitutions `acheteur`→`titulaire`. Différences spécifiques titulaire détaillées ci-dessous.

- [ ] **Step 1: Layout — stores + container**

Dans `src/pages/titulaire.py` :

- Imports : retirer `DataTable`, ajouter `get_top_org_ag_grid` et `from src.utils.entity_grid import register_entity_grid_callbacks`.
- Supprimer le bloc `DATATABLE = html.Div(..., DataTable(dtid="titulaire_datatable", ...))` (lignes ~70-84).
- `layout` → `def layout(titulaire_id=None, **kwargs):`.
- Ajouter près de `dcc.Store(id="titulaire-hidden-columns", ...)` :

```python
    dcc.Store(id="titulaire-total"),
    dcc.Store(id="titulaire-total-unique"),
    dcc.Store(id="entity-grid-columns-state", storage_type="local"),
```

- Remplacer le `DATATABLE` final (ligne ~271) par :

```python
    html.Div(id="titulaire-grid-container", className="marches_table"),
```

- [ ] **Step 2: Callbacks — suppression + registration + top 10**

- Supprimer : `get_last_marches_data` (Output `titulaire_datatable.*`), `download_filtered_titulaire_data`, le `clientside_callback` `clean_filters` + `dcc.Store(id="filter-cleanup-trigger-titulaire")`, `store_hidden_columns` (Output `titulaire_datatable.hidden_columns`), `reset_view` (Output `titulaire_datatable.*`).
- Conserver inchangés : `update_titulaire_infos`, `update_titulaire_map`, `update_titulaire_stats`, `update_download_button_titulaire`, `download_titulaire_data`, `update_hidden_columns_from_checkboxes`, `toggle_titulaire_columns`, `update_titulaire_distance_histogram`.
- **Corriger** `update_checkboxes_from_hidden_columns` (comme pour acheteur) : rebrancher son `Input("titulaire_datatable", "hidden_columns")` sur `Input("titulaire-hidden-columns", "data")` (le store), corps inchangé sinon (utilise `COLUMNS`/`get_default_hidden_columns("titulaire")`). Garder ces imports.
- **Top 10 (spécifique titulaire)** : `get_top_acheteurs` n'utilise PAS `make_card` — il retourne la table directement dans `html.Div(id="top10_acheteurs")` (qui a déjà son `<H3>Top acheteurs` dans le layout, lignes ~189-194). Migrer ainsi :

```python
@callback(
    Output(component_id="top10_acheteurs", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def get_top_acheteurs(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    return get_top_org_ag_grid(
        query_marches(where_sql, params).lazy(), "acheteur", ["titulaire_distance"]
    )
```

- Enregistrer les callbacks de grille (niveau module) :

```python
register_entity_grid_callbacks("titulaire")
```

> `_titulaire_scope` (qui ajoute `titulaire_typeIdentifiant = 'SIRET'`) reste utilisé par les callbacks conservés — ne pas le supprimer. Cohérent avec `entity_scope("titulaire", ...)`.

- [ ] **Step 3: Vérifier l'import de la page**

Run: `uv run python -c "import src.app; import src.pages.titulaire; print('titulaire OK')"`
Expected: `titulaire OK`.

- [ ] **Step 4: Vérifier le rendu réel (skill run)**

Charger `/titulaires/<un_id_SIRET_présent_dans_test.parquet>`. Mêmes vérifications qu'en Task 6 Step 4, plus : le scope SIRET s'applique (pas de lignes non-SIRET). Vérifier aussi qu'après avoir redimensionné/réordonné une colonne sur `/acheteurs/...` puis navigué vers `/titulaires/...`, la disposition des colonnes est **conservée** (store partagé), mais que le **filtre** n'est PAS repris d'une fiche à l'autre.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/titulaire.py
git add src/pages/titulaire.py
git commit -m "feat(titulaire): migration du tableau des marchés vers AG Grid (#41)"
```

---

## Task 8: Mettre à jour les tests d'intégration + suite complète

**Files:**

- Modify: `tests/test_main.py:63-95` (`test_002_filter_persistence`), `tests/test_main.py:98-121` (`test_003_tableau_download`)

> Note : la correction « Dash 3.4 → Dash 4.4 » dans `CLAUDE.md` a déjà été faite par l'utilisateur — ne pas la refaire.

- [ ] **Step 1: Adapter `test_002_filter_persistence` aux sélecteurs AG Grid**

Ce test pilote `/acheteurs/123` et `/titulaires/345` et cherche l'input de filtre de colonne DataTable (`.marches_table th[data-dash-column="dateNotification"] input[type="text"]`). Avec AG Grid, le filtre flottant d'une colonne est un `input` dans `.ag-floating-filter-input` de la colonne correspondante. Lire d'abord le test actuel :

Run: `uv run pytest tests/test_main.py::test_002_filter_persistence -v`
Expected (avant correction) : FAIL/erreur (sélecteur DataTable absent sur la grille AG Grid).

Adapter le corps pour cibler le filtre flottant AG Grid. Remplacer la recherche du champ de filtre par (adapter aux noms de variables du test existant) :

```python
    # AG Grid : le filtre flottant de la colonne dateNotification est un input
    # dans la cellule d'en-tête flottante correspondante. On l'atteint via le
    # col-id AG Grid (= nom du champ).
    filter_input = dash_duo.wait_for_element(
        'div[col-id="dateNotification"] .ag-floating-filter-input input',
        timeout=10,
    )
    filter_input.send_keys("2024")
```

> Le `col-id` AG Grid vaut le `field` de la columnDef (= nom de colonne DECP). Vérifier le sélecteur exact au moment de l'implémentation en inspectant le DOM rendu (le skill `run` peut servir à confirmer la structure `.ag-floating-filter-input`). Conserver l'intention du test (persistance du filtre après rechargement) : après saisie, recharger la page et vérifier que la valeur du filtre persiste — mais **attention** : la persistance filterModel est désormais scopée par `(entity_id, year)` ; le test doit recharger la **même** fiche pour observer la persistance.

- [ ] **Step 2: Vérifier `test_003_tableau_download`**

Ce test appelle directement `download_data(1, None, None)` (tableau), `download_acheteur_data(1, "/acheteurs/123", "2025", "ACHETEUR 1")`, `download_titulaire_data(1, "/titulaires/345", "2025", "TITULAIRE 1")`. Ces trois callbacks (« toutes les données ») ne changent PAS de signature dans ce lot. Vérifier qu'ils s'importent et s'appellent toujours :

Run: `uv run pytest tests/test_main.py::test_003_tableau_download -v`
Expected: PASS sans modification. Si un `ImportError` survient (ex. un helper supprimé était importé en tête du test), corriger l'import ; ne pas changer la logique du test.

- [ ] **Step 3: Lancer les tests ciblés**

Run: `uv run pytest tests/test_main.py::test_002_filter_persistence tests/test_main.py::test_003_tableau_download tests/test_entity_grid.py tests/test_grid.py tests/test_figures.py -v`
Expected: PASS.

- [ ] **Step 4: Lancer la suite complète (fin de lot)**

Run: `uv run pytest`
Expected: PASS (hors flakes Selenium préexistants éventuels — les identifier en relançant le test isolé et en confirmant qu'il échoue aussi sur `dev` sans ce lot ; cf. mémoire projet). Aucun échec **nouveau** attribuable à ce lot.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files tests/test_main.py
git add tests/test_main.py
git commit -m "test(acheteur/titulaire): sélecteurs AG Grid pour la grille des marchés (#41)"
```

---

## Notes de fin de lot

- **`entity-grid-columns-state`** est un store `storage_type="local"` partagé acheteur+titulaire ; sa déclaration apparaît dans les deux `layout()`. Si Dash se plaint d'un id dupliqué au chargement simultané (ne devrait pas : une page montée à la fois), déplacer sa déclaration dans un layout applicatif global unique (`src/app.py`) et retirer des pages.
- **Persistance filterModel scopée** : repose sur le fait que dash-ag-grid sérialise l'id dict comme clé localStorage. Le vérifier en Task 6 Step 4 (deux acheteurs distincts → filtres indépendants). Si la persistance ne discrimine pas par id, repli documenté dans la spec (« reset systématique au changement de fiche » — le remontage de grille le fait déjà, seul le rappel du filtre par fiche serait perdu).
- **Doublon de scope** (`_acheteur_scope`/`_titulaire_scope` dans les pages vs `entity_scope` dans le module) : toléré ce lot, à unifier au Lot 3.
- **Hors périmètre confirmé** : sélecteur de colonnes (`make_column_picker` reste DataTable, partagé avec tableau.py), `observatoire.py` (Lot 2b).
