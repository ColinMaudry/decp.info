# Tableau prepare_table_data Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make page navigation, sort changes, and repeated filter visits in the `/tableau` page near-instant by memoizing the expensive filter+sort+post-process pipeline inside `prepare_table_data`.

**Architecture:** Extract a memoized inner function `_load_filter_sort_postprocess(filter_query, sort_by_key)` that performs the heavy work (load full data, filter, sort, collect, cast-to-string, fill-null, add HTML links, format values) and returns a fully post-processed Polars DataFrame. The outer `prepare_table_data` becomes a thin wrapper that handles non-deterministic side effects (`track_search`, `uuid.uuid4()` for cleanup trigger, `data_timestamp + 1`) and pagination. The memoized helper only runs when no `data` argument is passed (i.e., the Tableau path). Other callers (`acheteur`, `titulaire`, `observatoire`) keep the current uncached path because they pass an externally-provided LazyFrame that is not safely hashable for cache keys.

**Tech Stack:** Polars (LazyFrame, DataFrame), Flask-Caching (`@cache.memoize()` on `FileSystemCache` already configured in `src/app.py:38`), pytest for unit tests.

**Git**: the issue id is #72, add the reference in commit messages.

---

## Background and constraints

Read these before starting; they explain why the design takes the shape it does.

1. **Cache infrastructure is already wired.** `src/cache.py` defines `cache = Cache()`. `src/app.py:38-48` initializes it with `FileSystemCache`, default 24h timeout, `CACHE_THRESHOLD=300`. The cache directory is wiped on every restart (`rmtree` at `src/app.py:36`), so cache always starts empty.

2. **Existing pattern to mirror.** `src/pages/observatoire.py:650-660` already uses `@cache.memoize()` plus a `_normalize_filter_params` helper that converts a dict of filters into a hashable tuple. This plan applies the same idiom to `sort_by` (which is a `list[dict]` from Dash DataTable).

3. **Non-deterministic outputs that MUST stay outside the memoized function:**

   - `data_timestamp + 1` (increments each call; would freeze if cached)
   - `trigger_cleanup = str(uuid.uuid4())` (intentionally unique per call to fire the clientside filter-cleanup callback)
   - `track_search(filter_query, source_table)` — Matomo HTTP POST, currently called inside `filter_table_data` at `src/utils/table.py:214`. Must fire on every user action including cache hits.

4. **Tracking call site move.** `track_search` must move OUT of `filter_table_data` and into each caller, otherwise cache hits would silently skip Matomo tracking. Current callers of `filter_table_data` to update:

   - `src/utils/table.py:402` (inside `prepare_table_data`)
   - `src/pages/tableau.py:325` (`download_data` callback)
   - `src/pages/acheteur.py:427` (`download_data_acheteur` callback)
   - `src/pages/titulaire.py:443` (`download_data_titulaire` callback)

5. **Why Tableau-only caching.** `prepare_table_data` is also called from `acheteur.py`, `titulaire.py`, `observatoire.py`. Those callers pass a pre-filtered LazyFrame or list-of-dicts as `data`. Hashing arbitrary LazyFrames or large lists for memoization is impractical. The fix gates on `data is None` (the Tableau path) and leaves the other paths byte-for-byte identical.

6. **Cache key composition.** The memoized function takes only `(filter_query, sort_by_key)`. `page_current` and `page_size` are intentionally NOT in the key — pagination happens in the outer wrapper after retrieving the cached, fully post-processed frame. This means every page click and page-size change is a cache hit (the whole point of the change).

7. **Pickling.** Flask-Caching pickles arguments to form keys and pickles return values to disk. Polars `DataFrame` pickles cleanly. `LazyFrame` does not — so the memoized function must `.collect()` before returning.

8. **File path expectations.** All paths below are relative to repo root `/home/colin/git/decp.info`. Run all commands from there.

---

## File Structure

- **Modify** `src/utils/table.py` — extract memoized helper, refactor `prepare_table_data`, remove `track_search` call from `filter_table_data`.
- **Modify** `src/pages/tableau.py` — add explicit `track_search` call in `download_data`.
- **Modify** `src/pages/acheteur.py` — add explicit `track_search` call in `download_data_acheteur`.
- **Modify** `src/pages/titulaire.py` — add explicit `track_search` call in `download_data_titulaire`.
- **Create** `tests/test_table.py` — unit tests for new helpers and refactored `prepare_table_data`.

---

## Task 1: Set up unit tests for table.py

**Files:**

- Create: `tests/test_table.py`

This task scaffolds a non-Selenium pytest module so subsequent tasks can do TDD without booting a Dash server. The conftest already writes a small `tests/test.parquet` fixture (see `tests/conftest.py:10`); reuse it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_table.py` with:

```python
import os

import polars as pl
import pytest


@pytest.fixture
def sample_lff():
    """Small LazyFrame with the columns needed by add_links / format_values."""
    return pl.LazyFrame(
        [
            {
                "uid": "u1",
                "id": "u1",
                "acheteur_id": "12345678900011",
                "acheteur_nom": "Mairie de Test",
                "titulaire_id": "98765432100022",
                "titulaire_nom": "Entreprise Test",
                "titulaire_typeIdentifiant": "SIRET",
                "objet": "Travaux divers",
                "montant": 12500.0,
                "dateNotification": "2025-03-15",
                "codeCPV": "45000000",
                "dureeRestanteMois": 6,
                "titulaire_distance": 42.0,
            }
        ]
    )


def test_table_module_imports():
    from src.utils import table

    assert hasattr(table, "prepare_table_data")
```

- [ ] **Step 2: Run test to verify it passes (sanity check)**

Run: `uv run pytest tests/test_table.py -v`
Expected: PASS for `test_table_module_imports`. (Selenium is not invoked because no `dash_duo` fixture is used.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_table.py
git commit -m "test: scaffold unit tests for table utilities"
```

---

## Task 2: Move track_search out of filter_table_data

**Files:**

- Modify: `src/utils/table.py:210-274` (remove `track_search` import usage at line 214)
- Modify: `src/pages/tableau.py:317-334` (`download_data` callback)
- Modify: `src/pages/acheteur.py:425-430` area (`download_data_acheteur` callback)
- Modify: `src/pages/titulaire.py:441-446` area (`download_data_titulaire` callback)
- Modify: `tests/test_table.py` (add a test that confirms `filter_table_data` no longer calls Matomo)

`track_search` must move out so that the soon-to-be-memoized helper does not swallow tracking on cache hits. We do this BEFORE introducing caching so that the diff is small and verifiable on its own.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_table.py`:

```python
def test_filter_table_data_does_not_call_track_search(monkeypatch, sample_lff):
    from src.utils import table

    calls = []
    monkeypatch.setattr(table, "track_search", lambda *a, **kw: calls.append(a))

    result = table.filter_table_data(
        sample_lff, "{objet} icontains travaux", "tableau"
    ).collect()

    assert calls == []
    assert result.height == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_table.py::test_filter_table_data_does_not_call_track_search -v`
Expected: FAIL (`assert calls == []` fails because `filter_table_data` currently calls `track_search` at line 214).

- [ ] **Step 3: Remove the track_search call from filter_table_data**

Edit `src/utils/table.py` — find this block:

```python
def filter_table_data(
    lff: pl.LazyFrame, filter_query: str, filter_source: str
) -> pl.LazyFrame:
    _schema = lff.collect_schema()
    track_search(filter_query, filter_source)
    filtering_expressions = filter_query.split(" && ")
```

Remove the `track_search(filter_query, filter_source)` line. Result:

```python
def filter_table_data(
    lff: pl.LazyFrame, filter_query: str, filter_source: str
) -> pl.LazyFrame:
    _schema = lff.collect_schema()
    filtering_expressions = filter_query.split(" && ")
```

The `filter_source` parameter remains in the signature (avoids changing all callers in this task). It becomes unused; that is acceptable since callers will pass it again later if needed. Do NOT remove the `from src.utils.tracking import track_search` import yet — `prepare_table_data` will use it in Task 5.

- [ ] **Step 4: Add explicit track_search calls in download callbacks**

In `src/pages/tableau.py`, find:

```python
def download_data(n_clicks, filter_query, sort_by, hidden_columns: list = None):
    lff: pl.LazyFrame = query_marches().lazy()

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        lff = filter_table_data(lff, filter_query, "tab download")
```

Insert a `track_search` call so behavior is preserved. First add the import at the top of `src/pages/tableau.py` next to other `src.utils` imports:

```python
from src.utils.tracking import track_search
```

Then change the body:

```python
def download_data(n_clicks, filter_query, sort_by, hidden_columns: list = None):
    lff: pl.LazyFrame = query_marches().lazy()

    # Les colonnes masquées sont supprimées
    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        track_search(filter_query, "tab download")
        lff = filter_table_data(lff, filter_query, "tab download")
```

Repeat the same pattern in `src/pages/acheteur.py` (search for `filter_table_data(lff, filter_query, "ach download")`):

Add import:

```python
from src.utils.tracking import track_search
```

Wrap the call:

```python
    if filter_query:
        track_search(filter_query, "ach download")
        lff = filter_table_data(lff, filter_query, "ach download")
```

Repeat in `src/pages/titulaire.py` (search for `filter_table_data(lff, filter_query, "titu download")`):

Add import:

```python
from src.utils.tracking import track_search
```

Wrap the call:

```python
    if filter_query:
        track_search(filter_query, "titu download")
        lff = filter_table_data(lff, filter_query, "titu download")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_table.py::test_filter_table_data_does_not_call_track_search -v`
Expected: PASS.

- [ ] **Step 6: Run full unit test file to verify no regressions**

Run: `uv run pytest tests/test_table.py -v`
Expected: All tests in `test_table.py` PASS.

- [ ] **Step 7: Commit**

```bash
git add src/utils/table.py src/pages/tableau.py src/pages/acheteur.py src/pages/titulaire.py tests/test_table.py
git commit -m "refactor: move track_search out of filter_table_data into callers"
```

---

## Task 3: Add normalize_sort_by helper

**Files:**

- Modify: `src/utils/table.py` (add helper near other utility functions, e.g. after `dates_to_strings`)
- Modify: `tests/test_table.py` (add tests)

A cache key must be hashable. Dash DataTable's `sort_by` is a `list[dict]` like `[{"column_id": "montant", "direction": "asc"}, ...]`, which is not hashable. We mirror the `_normalize_filter_params` idiom from `src/pages/observatoire.py:650-657`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_table.py`:

```python
def test_normalize_sort_by_handles_empty():
    from src.utils.table import normalize_sort_by

    assert normalize_sort_by(None) == ()
    assert normalize_sort_by([]) == ()


def test_normalize_sort_by_returns_hashable_tuple():
    from src.utils.table import normalize_sort_by

    sort_by = [
        {"column_id": "montant", "direction": "desc"},
        {"column_id": "dateNotification", "direction": "asc"},
    ]
    key = normalize_sort_by(sort_by)

    assert key == (("montant", "desc"), ("dateNotification", "asc"))
    # Must be hashable so that flask-caching can build a cache key from it
    hash(key)


def test_normalize_sort_by_preserves_order():
    """Order matters for sort: [A, B] != [B, A]."""
    from src.utils.table import normalize_sort_by

    a_then_b = normalize_sort_by(
        [{"column_id": "a", "direction": "asc"}, {"column_id": "b", "direction": "asc"}]
    )
    b_then_a = normalize_sort_by(
        [{"column_id": "b", "direction": "asc"}, {"column_id": "a", "direction": "asc"}]
    )
    assert a_then_b != b_then_a
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_table.py -v -k normalize_sort_by`
Expected: FAIL with `ImportError` for `normalize_sort_by`.

- [ ] **Step 3: Implement normalize_sort_by**

Edit `src/utils/table.py`. Add this function immediately after the `dates_to_strings` function (around line 148):

```python
def normalize_sort_by(sort_by) -> tuple:
    """Convert Dash DataTable sort_by (list[dict]) into a hashable tuple
    suitable for use as a cache key. Order is preserved because it determines
    sort precedence."""
    if not sort_by:
        return ()
    return tuple((entry["column_id"], entry["direction"]) for entry in sort_by)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_table.py -v -k normalize_sort_by`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/table.py tests/test_table.py
git commit -m "feat: add normalize_sort_by hashable cache-key helper"
```

---

## Task 4: Extract memoized post-process helper

**Files:**

- Modify: `src/utils/table.py` (add `_load_filter_sort_postprocess`, decorate with `@cache.memoize()`, import `cache`)
- Modify: `tests/test_table.py` (add tests)

Introduce the function whose result will live in the FileSystemCache. Inputs: `(filter_query, sort_by_key)`. Output: a fully post-processed, unpaginated Polars DataFrame ready to slice and convert to dicts.

This task does NOT yet wire the helper into `prepare_table_data` — that happens in Task 5. Splitting these tasks keeps each diff small and testable.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_table.py`:

```python
@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure the flask-caching backend is empty between tests so that
    cache-hit assertions are meaningful. Falls back to no-op when no
    Flask app context is active (NullCache)."""
    from utils.cache import cache

    try:
        cache.clear()
    except RuntimeError:
        # No app context — cache is NullCache, nothing to clear
        pass
    yield


def test_load_filter_sort_postprocess_returns_dataframe(monkeypatch, sample_lff):
    from src.utils import table

    monkeypatch.setattr(
        table, "query_marches", lambda: sample_lff.collect()
    )

    df = table._load_filter_sort_postprocess(filter_query=None, sort_by_key=())

    assert isinstance(df, pl.DataFrame)
    assert df.height == 1
    # All values must be strings after post-processing
    for col in df.columns:
        assert df.schema[col] == pl.String


def test_load_filter_sort_postprocess_applies_filter(monkeypatch, sample_lff):
    from src.utils import table

    monkeypatch.setattr(
        table, "query_marches", lambda: sample_lff.collect()
    )

    df = table._load_filter_sort_postprocess(
        filter_query="{objet} icontains travaux", sort_by_key=()
    )
    assert df.height == 1

    df_empty = table._load_filter_sort_postprocess(
        filter_query="{objet} icontains nonexistent", sort_by_key=()
    )
    assert df_empty.height == 0


def test_load_filter_sort_postprocess_adds_links(monkeypatch, sample_lff):
    from src.utils import table

    monkeypatch.setattr(
        table, "query_marches", lambda: sample_lff.collect()
    )

    df = table._load_filter_sort_postprocess(filter_query=None, sort_by_key=())
    # add_links injects an <a href> wrapper around uid, acheteur_nom, titulaire_nom
    assert "<a href" in df["uid"][0]
    assert "<a href" in df["acheteur_nom"][0]
    assert "<a href" in df["titulaire_nom"][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_table.py -v -k load_filter_sort_postprocess`
Expected: FAIL with `AttributeError: module 'src.utils.table' has no attribute '_load_filter_sort_postprocess'`.

- [ ] **Step 3: Implement the helper**

Edit `src/utils/table.py`. Add this import near the top, with the other `src.` imports:

```python
from utils.cache import cache
```

Then add the helper function. Place it ABOVE `prepare_table_data` (around line 370, just before `def prepare_table_data`):

```python
@cache.memoize()
def _load_filter_sort_postprocess(filter_query, sort_by_key):
    """Memoized core of the Tableau page pipeline.

    Loads the full marchés dataset, applies filter and sort, materializes,
    then runs the per-row post-processing (cast to string, fill nulls, add
    HTML links, format values). Returns an unpaginated Polars DataFrame.

    Inputs MUST be hashable: filter_query is str|None, sort_by_key is the
    tuple produced by normalize_sort_by(). Pagination intentionally lives
    in the outer wrapper so that page changes are cache hits.
    """
    logger.debug(f"Cache miss — recomputing for filter={filter_query!r} sort={sort_by_key!r}")

    lff: pl.LazyFrame = query_marches().lazy()

    if filter_query:
        lff = filter_table_data(lff, filter_query, "tableau")

    if sort_by_key:
        sort_by = [
            {"column_id": col, "direction": direction}
            for col, direction in sort_by_key
        ]
        lff = sort_table_data(lff, sort_by)


    # The remaining steps are cheap per-row operations that we run ONCE here
    # so that pagination in the outer function is a pure slice + to_dicts.
    lff = lff.cast(pl.String)
    lff = lff.fill_null("")

    dff: pl.DataFrame = lff.collect()

    dff = add_links(dff)
    if "sourceFile" in dff.columns:
        dff = add_resource_link(dff)
    if dff.height > 0:
        dff = format_values(dff)

    return dff
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_table.py -v -k load_filter_sort_postprocess`
Expected: 3 PASS.

- [ ] **Step 5: Run the full test_table.py to catch regressions**

Run: `uv run pytest tests/test_table.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add src/utils/table.py tests/test_table.py
git commit -m "feat: add memoized _load_filter_sort_postprocess helper"
```

---

## Task 5: Wire the memoized helper into prepare_table_data

**Files:**

- Modify: `src/utils/table.py` — replace the body of `prepare_table_data` so the Tableau path uses the cache
- Modify: `tests/test_table.py` — add tests covering the new flow

The outer function keeps its signature unchanged so callers in `acheteur.py`, `titulaire.py`, `observatoire.py`, `tableau.py` need no updates. When `data is None` (the Tableau case), use the memoized helper; otherwise fall through to the original logic.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_table.py`:

```python
def test_prepare_table_data_returns_expected_tuple(monkeypatch, sample_lff):
    from src.utils import table

    monkeypatch.setattr(
        table, "query_marches", lambda: sample_lff.collect()
    )

    result = table.prepare_table_data(
        data=None,
        data_timestamp=5,
        filter_query=None,
        page_current=0,
        page_size=20,
        sort_by=[],
        source_table="tableau",
    )

    # Same arity as before: 9 outputs
    assert len(result) == 9
    dicts, columns, tooltip, ts, nb_rows, dl_disabled, dl_text, dl_title, cleanup = result
    assert isinstance(dicts, list)
    assert ts == 6  # data_timestamp + 1 must still increment
    assert "1 lignes" in nb_rows


def test_prepare_table_data_calls_track_search_on_filter(monkeypatch, sample_lff):
    from src.utils import table

    calls = []
    monkeypatch.setattr(
        table, "query_marches", lambda: sample_lff.collect()
    )
    monkeypatch.setattr(table, "track_search", lambda *a, **kw: calls.append(a))

    table.prepare_table_data(
        data=None,
        data_timestamp=0,
        filter_query="{objet} icontains travaux",
        page_current=0,
        page_size=20,
        sort_by=[],
        source_table="tableau",
    )

    assert calls == [("{objet} icontains travaux", "tableau")]


def test_prepare_table_data_paginates_without_recomputing(monkeypatch, sample_lff):
    """Two calls with same filter+sort but different pages must invoke
    the inner heavy work only once."""
    from src.utils import table

    call_count = {"n": 0}
    real_query = sample_lff.collect()

    def counting_query():
        call_count["n"] += 1
        return real_query

    monkeypatch.setattr(table, "query_marches", counting_query)

    # First call: cache miss
    table.prepare_table_data(
        data=None,
        data_timestamp=0,
        filter_query=None,
        page_current=0,
        page_size=10,
        sort_by=[],
        source_table="tableau",
    )
    first_count = call_count["n"]

    # Second call, different page: cache hit, query_marches must NOT fire again
    table.prepare_table_data(
        data=None,
        data_timestamp=0,
        filter_query=None,
        page_current=1,
        page_size=10,
        sort_by=[],
        source_table="tableau",
    )

    assert call_count["n"] == first_count, (
        "query_marches was called again — pagination triggered cache miss"
    )


def test_prepare_table_data_cleanup_trigger_for_non_tableau(monkeypatch, sample_lff):
    """Non-tableau pages still get a fresh uuid trigger, not no_update."""
    from dash import no_update

    from src.utils import table

    monkeypatch.setattr(
        table, "query_marches", lambda: sample_lff.collect()
    )

    result = table.prepare_table_data(
        data=None,
        data_timestamp=0,
        filter_query="{objet} icontains travaux",
        page_current=0,
        page_size=20,
        sort_by=[],
        source_table="acheteur",
    )

    cleanup = result[8]
    assert cleanup is not no_update
    assert isinstance(cleanup, str)
    assert len(cleanup) >= 32  # uuid4 hex string


def test_prepare_table_data_with_external_data_does_not_use_cache(
    monkeypatch, sample_lff
):
    """When a caller passes data (acheteur/titulaire/observatoire path),
    bypass the memoized helper entirely."""
    from src.utils import table

    sentinel = {"called": False}

    def should_not_be_called(*a, **kw):
        sentinel["called"] = True
        raise AssertionError("Memoized helper must not be called when data is provided")

    monkeypatch.setattr(
        table, "_load_filter_sort_postprocess", should_not_be_called
    )

    table.prepare_table_data(
        data=sample_lff,  # external LazyFrame
        data_timestamp=0,
        filter_query=None,
        page_current=0,
        page_size=20,
        sort_by=[],
        source_table="acheteur",
    )

    assert sentinel["called"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_table.py -v -k prepare_table_data`
Expected: At least the cache-hit (`paginates_without_recomputing`) and `track_search`-routing tests FAIL because the current `prepare_table_data` re-runs the full pipeline on every call and routes tracking through `filter_table_data` (which Task 2 already neutralized — so tracking would be lost without the new explicit call).

- [ ] **Step 3: Refactor prepare_table_data**

Edit `src/utils/table.py`. Replace the entire `prepare_table_data` function body with:

```python
def prepare_table_data(
    data, data_timestamp, filter_query, page_current, page_size, sort_by, source_table
):
    """
    Préparation des données pour les datatables.

    Pour la page Tableau (data is None), le calcul lourd (chargement complet,
    filtre, tri, post-traitement) est mémorisé via _load_filter_sort_postprocess.
    Les changements de page deviennent ainsi des cache hits.

    Pour les autres pages (data fourni), le chemin original est conservé : la
    LazyFrame externe n'est pas hashable et le coût de filtre/tri y est déjà
    minime puisque les données sont pré-restreintes.
    """
    logger.debug(" + + + + + + + + + + + + + + + + + + ")

    # Side effect non-cacheable : le tracking doit firer sur chaque action
    # utilisateur, y compris sur cache hit.
    if filter_query:
        track_search(filter_query, source_table)

    # Trigger uuid pour les pages autres que tableau (clientside cleanup)
    trigger_cleanup = (
        no_update if source_table == "tableau" else str(uuid.uuid4())
    )

    if data is None:
        # Tableau path : utilise le cache
        sort_by_key = normalize_sort_by(sort_by)
        dff: pl.DataFrame = _load_filter_sort_postprocess(
            filter_query=filter_query, sort_by_key=sort_by_key
        )
    else:
        # acheteur / titulaire / observatoire path : code original, non caché
        if isinstance(data, list):
            lff: pl.LazyFrame = pl.LazyFrame(
                data, strict=False, infer_schema_length=5000
            )
        elif isinstance(data, pl.LazyFrame):
            lff = data
        else:
            lff = query_marches().lazy()

        if filter_query:
            lff = filter_table_data(lff, filter_query, source_table)

        if sort_by and len(sort_by) > 0:
            lff = sort_table_data(lff, sort_by)

        dff = lff.collect()
        dff = dff.cast(pl.String)
        dff = dff.fill_null("")
        dff = add_links(dff)
        if "sourceFile" in dff.columns:
            dff = add_resource_link(dff)
        if dff.height > 0:
            dff = format_values(dff)

    height = dff.height

    if height > 0:
        nb_rows = (
            f"{format_number(height)} lignes "
            f"({format_number(dff.select('uid').unique().height)} marchés)"
        )
    else:
        nb_rows = "0 lignes (0 marchés)"

    # Pagination — toujours hors cache pour rester sur des cache hits
    start_row = page_current * page_size
    dff = dff.slice(start_row, page_size)

    table_columns, tooltip = setup_table_columns(dff)

    dicts = dff.to_dicts()

    download_disabled, download_text, download_title = get_button_properties(height)

    return (
        dicts,
        table_columns,
        tooltip,
        data_timestamp + 1,
        nb_rows,
        download_disabled,
        download_text,
        download_title,
        trigger_cleanup,
    )
```

Notes on what changed vs the original at `src/utils/table.py:372-458`:

- `track_search` now called explicitly at the top, on every invocation (not via `filter_table_data`).
- `data is None` branch delegates the heavy work to the memoized helper.
- `data is not None` branch is functionally identical to the original (pagination still happens after collect+post-process).
- The post-processing (`cast`, `fill_null`, `add_links`, `add_resource_link`, `format_values`) is now done in BOTH branches before `nb_rows` calculation. In the cached branch this was already done inside `_load_filter_sort_postprocess`; in the uncached branch we keep doing it inline. This means `nb_rows` and `dff.select('uid').unique().height` operate on the post-processed frame in both branches, matching the original semantics.

- [ ] **Step 4: Run all unit tests**

Run: `uv run pytest tests/test_table.py -v`
Expected: All PASS, including `test_prepare_table_data_paginates_without_recomputing`.

- [ ] **Step 5: Run the full repo test suite to catch regressions**

Run: `uv run pytest -v`
Expected: All PASS. Selenium tests (`tests/test_main.py`) require Chrome/Chromium; if the executor lacks a browser, those tests will error/skip — note the failures and rerun in an environment with Chrome before declaring done.

- [ ] **Step 6: Commit**

```bash
git add src/utils/table.py tests/test_table.py
git commit -m "perf(tableau): memoize filter+sort+postprocess pipeline"
```

---

## Task 6: Manual smoke test in the browser

**Files:** none modified.

Type checks and unit tests cannot validate that page navigation actually feels faster. This task is explicitly a hands-on verification.

- [ ] **Step 1: Start the dev server**

Run: `uv run run.py`
Wait for `Dash is running on http://...`.

- [ ] **Step 2: Open the Tableau page and warm the cache**

1. Open `http://localhost:8050/tableau` (or whatever port the dev server prints).
2. With no filter applied, wait for the first page to load fully. This is the cold-cache load (slow expected).
3. Open the browser devtools Network panel.

- [ ] **Step 3: Verify pagination is fast**

1. Click "page 2" / "page 3" / "page 4" in the table footer in quick succession.
2. Each navigation should return data in well under 1 second (in the original code each took several seconds).
3. In the dev server logs, look for the line `Cache miss — recomputing for filter=...` from `_load_filter_sort_postprocess`. It should appear ONCE for the initial load and NOT appear again as you change pages.

- [ ] **Step 4: Verify a new filter triggers exactly one cache miss**

1. In the table, type a filter into one of the columns (e.g. `paris` in `acheteur_commune_nom`) and press Enter.
2. The dev log should show ONE new `Cache miss — recomputing` line.
3. Change page within the filtered view — no new cache miss line should appear.

- [ ] **Step 5: Verify filter cleanup trigger still fires**

1. Open `http://localhost:8050/acheteur?id=<some_acheteur_id>` (use any valid id from the dataset).
2. Apply a filter on the embedded table.
3. The clientside callback for filter cleanup (`src/assets/dash_clientside.js` `clean_filters`) should still rewrite the filter operators (e.g. `contains` → `icontains`). If it doesn't fire, the `trigger_cleanup` uuid is broken — investigate.

- [ ] **Step 6: Verify download still works**

1. On the Tableau page, click "Télécharger au format Excel" (the button must be enabled — apply a filter that brings the row count under 65,000).
2. The downloaded XLSX must open and contain the filtered rows.

- [ ] **Step 7: Stop the dev server**

Ctrl-C.

- [ ] **Step 8: If all checks pass, this completes the implementation**

No commit — this task is verification only. Report results to the user.
