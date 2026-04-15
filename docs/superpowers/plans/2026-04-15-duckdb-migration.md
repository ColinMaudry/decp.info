# DuckDB Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the in-memory global Polars dataframes in `src/utils.py` (the full `df` plus five derived frames) with an on-disk DuckDB database, reducing steady-state RSS. Per-request SQL returns small Polars frames that existing downstream code continues to consume.

**Architecture:** A new module `src/db.py` owns the DuckDB lifecycle — startup build under a `fcntl.flock` lock, atomic `os.replace` swap, read-only runtime connection with per-call cursors, and a `query_marches()` helper that returns `pl.DataFrame`. Row-level transforms stay in Polars (via `connection.register("frame", pl_frame)`) so `booleans_to_strings` and the null-name replacement remain the single source of truth. `df_acheteurs` and `df_titulaires` stay as in-memory Polars frames populated from DuckDB at import time (they feed the autocomplete search).

**Tech Stack:** Python 3.10+, DuckDB (Python API), Polars, Dash, pytest (+ dash Selenium testing), pre-commit (prettier, ruff).

**Spec:** `docs/superpowers/specs/2026-04-15-duckdb-migration-design.md`

---

## File Structure

### Created files

| Path               | Responsibility                                                                                                         |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `src/db.py`        | DuckDB lifecycle: `should_rebuild`, `build_database`, module-level `conn`, `schema`, `get_cursor()`, `query_marches()` |
| `tests/test_db.py` | Unit tests for `should_rebuild`, `build_database`, `query_marches`, and concurrent-startup lock behavior               |

### Modified files

| Path                                   | What changes                                                                                                                                                                                           |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pyproject.toml`                       | Add `duckdb` dependency                                                                                                                                                                                |
| `.gitignore`                           | Ignore `**/decp.duckdb`, `**/decp.duckdb.tmp`, `**/decp.duckdb.lock`                                                                                                                                   |
| `src/utils.py`                         | Remove `df` global, replace `df_acheteurs` / `df_titulaires` population with DuckDB-backed queries, remove `df_*_marches` and `df_*_departement` globals, expose `schema` / `columns` from `src/db.py` |
| `src/pages/marche.py`                  | `df.lazy().filter(...)` → `query_marches("uid = ?", (uid,)).lazy()`                                                                                                                                    |
| `src/pages/acheteur.py`                | Same pattern + replace `df.collect_schema()` with module `schema`, `df.columns` with `schema.names()`                                                                                                  |
| `src/pages/titulaire.py`               | Same pattern as acheteur                                                                                                                                                                               |
| `src/pages/tableau.py`                 | `df.lazy()` → `query_marches().lazy()`, `df.columns` → `schema.names()`, `df.width` → `len(schema.names())`                                                                                            |
| `src/pages/observatoire.py`            | 3 call sites: `df.lazy()` → `query_marches().lazy()`, `df.columns` → `schema.names()`                                                                                                                  |
| `src/pages/arbre/departement.py`       | `df_acheteurs_departement` / `df_titulaires_departement` → `get_cursor().execute("SELECT ... FROM {table} WHERE ...", [...]).pl()`                                                                     |
| `src/pages/arbre/liste_marches_org.py` | `df_acheteurs_marches` / `df_titulaires_marches` → `get_cursor().execute(...).pl()`                                                                                                                    |
| `src/figures.py`                       | `df.columns` → `schema.names()` (via `src.db`)                                                                                                                                                         |
| `tests/conftest.py`                    | Ensure the DuckDB test file is rebuilt from the freshly-written `test.parquet` each session                                                                                                            |

---

## Task 1: Add DuckDB dependency and ignore patterns

**Files:**

- Modify: `pyproject.toml` (dependencies list at top)
- Modify: `.gitignore`

- [ ] **Step 1: Add `duckdb` to `pyproject.toml`**

Open `pyproject.toml`, find the `dependencies = [...]` block, and insert `"duckdb",` on a new line before `"flask-caching",`. Result:

```toml
dependencies = [
  "dash==3.4.0",
  "dash[compress]",
  "polars",
  "gunicorn",
  "dash-bootstrap-components",
  "python-dotenv",
  "xlsxwriter",
  "plotly[express]",
  "httpx",
  "pandas",
  "unidecode",
  "dash-leaflet",
  "dash-extensions",
  "duckdb",
  "flask-caching",
]
```

- [ ] **Step 2: Install the dependency**

Run: `uv pip install -e ".[dev]"`

Expected: installation completes, `python -c "import duckdb; print(duckdb.__version__)"` prints a version.

- [ ] **Step 3: Add DuckDB artifacts to `.gitignore`**

Append to `.gitignore`:

```
# DuckDB runtime artifacts (regenerated from decp_prod.parquet at startup)
**/decp.duckdb
**/decp.duckdb.tmp
**/decp.duckdb.lock
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .gitignore uv.lock
git commit -m "Ajout de la dépendance duckdb"
```

---

## Task 2: Write failing tests for `should_rebuild`

**Files:**

- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:

```python
import os
import time
from pathlib import Path

import pytest


@pytest.fixture
def parquet_and_db(tmp_path, monkeypatch):
    parquet = tmp_path / "source.parquet"
    db = tmp_path / "decp.duckdb"
    parquet.write_bytes(b"fake parquet content")
    monkeypatch.delenv("REBUILD_DUCKDB", raising=False)
    monkeypatch.delenv("DEVELOPMENT", raising=False)
    return parquet, db


def test_should_rebuild_when_db_missing(parquet_and_db, monkeypatch):
    from src.db import should_rebuild
    parquet, db = parquet_and_db
    monkeypatch.setenv("DEVELOPMENT", "true")
    assert should_rebuild(db, parquet) is True


def test_should_rebuild_prod_when_parquet_newer(parquet_and_db, monkeypatch):
    from src.db import should_rebuild
    parquet, db = parquet_and_db
    db.write_bytes(b"x")
    time.sleep(0.01)
    parquet.touch()
    monkeypatch.setenv("DEVELOPMENT", "false")
    assert should_rebuild(db, parquet) is True


def test_should_not_rebuild_prod_when_parquet_older(parquet_and_db, monkeypatch):
    from src.db import should_rebuild
    parquet, db = parquet_and_db
    parquet.touch()
    time.sleep(0.01)
    db.write_bytes(b"x")
    monkeypatch.setenv("DEVELOPMENT", "false")
    assert should_rebuild(db, parquet) is False


def test_should_not_rebuild_dev_even_when_parquet_newer(parquet_and_db, monkeypatch):
    from src.db import should_rebuild
    parquet, db = parquet_and_db
    db.write_bytes(b"x")
    time.sleep(0.01)
    parquet.touch()
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.delenv("REBUILD_DUCKDB", raising=False)
    assert should_rebuild(db, parquet) is False


def test_should_rebuild_dev_when_rebuild_forced(parquet_and_db, monkeypatch):
    from src.db import should_rebuild
    parquet, db = parquet_and_db
    db.write_bytes(b"x")
    time.sleep(0.01)
    parquet.touch()
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("REBUILD_DUCKDB", "true")
    assert should_rebuild(db, parquet) is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/test_db.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.db'` (or `ImportError`).

---

## Task 3: Implement `should_rebuild` in `src/db.py`

**Files:**

- Create: `src/db.py`

- [ ] **Step 1: Create minimal `src/db.py`**

```python
import logging
import os
from pathlib import Path

logger = logging.getLogger("decp.info")


def should_rebuild(db_path: Path, parquet_path: Path) -> bool:
    """Decide whether to rebuild the DuckDB database from the source Parquet.

    Rules:
      - Rebuild if the DuckDB file does not exist.
      - Otherwise, rebuild only if the source Parquet is newer than the DB,
        EXCEPT in development mode without REBUILD_DUCKDB=true (dev keeps
        a stable DB across reloads unless explicitly opted in).
    """
    db_path = Path(db_path)
    parquet_path = Path(parquet_path)

    if not db_path.exists():
        return True

    dev = os.getenv("DEVELOPMENT", "False").lower() == "true"
    force = os.getenv("REBUILD_DUCKDB", "False").lower() == "true"
    if dev and not force:
        return False

    return parquet_path.stat().st_mtime > db_path.stat().st_mtime
```

- [ ] **Step 2: Run tests and verify they pass**

Run: `uv run pytest tests/test_db.py -v`

Expected: 5 passed.

- [ ] **Step 3: Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "Ajout de src.db.should_rebuild et ses tests"
```

---

## Task 4: Write failing tests for `build_database` and `query_marches`

**Files:**

- Modify: `tests/test_db.py`

- [ ] **Step 1: Append build/query tests to `tests/test_db.py`**

```python
import datetime
import polars as pl


@pytest.fixture
def built_db(tmp_path, monkeypatch):
    """Build a DuckDB from a small Polars frame written as parquet."""
    parquet_path = tmp_path / "source.parquet"
    db_path = tmp_path / "decp.duckdb"

    data = pl.DataFrame(
        [
            {
                "uid": "1",
                "id": "1",
                "objet": "Travaux",
                "acheteur_id": "A1",
                "acheteur_nom": "Mairie",
                "acheteur_departement_code": "75",
                "titulaire_id": "T1",
                "titulaire_nom": "Entreprise",
                "titulaire_departement_code": "35",
                "titulaire_typeIdentifiant": "SIRET",
                "montant": 1000.0,
                "dateNotification": datetime.date(2025, 1, 1),
                "donneesActuelles": True,
                "marcheInnovant": True,
            },
            {
                "uid": "2",
                "id": "2",
                "objet": "Études",
                "acheteur_id": "A1",
                "acheteur_nom": "Mairie",
                "acheteur_departement_code": "75",
                "titulaire_id": "T2",
                "titulaire_nom": None,
                "titulaire_departement_code": "75",
                "titulaire_typeIdentifiant": "SIRET",
                "montant": 500.0,
                "dateNotification": datetime.date(2024, 6, 1),
                "donneesActuelles": True,
                "marcheInnovant": False,
            },
            {
                "uid": "3",
                "id": "3",
                "objet": "Ancien",
                "acheteur_id": "A2",
                "acheteur_nom": None,
                "acheteur_departement_code": "13",
                "titulaire_id": "T3",
                "titulaire_nom": "Autre",
                "titulaire_departement_code": "13",
                "titulaire_typeIdentifiant": "SIRET",
                "montant": 100.0,
                "dateNotification": datetime.date(2023, 1, 1),
                "donneesActuelles": False,  # must be filtered out
                "marcheInnovant": False,
            },
        ]
    )
    data.write_parquet(parquet_path)
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", str(parquet_path))

    from src.db import build_database
    build_database(db_path, parquet_path)
    return db_path


def test_build_filters_donnees_actuelles(built_db):
    import duckdb
    with duckdb.connect(str(built_db), read_only=True) as c:
        rows = c.execute("SELECT uid FROM decp ORDER BY uid").fetchall()
    assert [r[0] for r in rows] == ["1", "2"]


def test_build_converts_booleans_to_oui_non(built_db):
    import duckdb
    with duckdb.connect(str(built_db), read_only=True) as c:
        values = c.execute(
            "SELECT marcheInnovant FROM decp ORDER BY uid"
        ).fetchall()
    assert [v[0] for v in values] == ["oui", "non"]


def test_build_replaces_null_org_names(built_db):
    import duckdb
    with duckdb.connect(str(built_db), read_only=True) as c:
        titulaire_2 = c.execute(
            "SELECT titulaire_nom FROM decp WHERE uid = '2'"
        ).fetchone()
    assert titulaire_2[0] == "[Identifiant non reconnu dans la base INSEE]"


def test_build_creates_derived_tables(built_db):
    import duckdb
    with duckdb.connect(str(built_db), read_only=True) as c:
        tables = {r[0] for r in c.execute("SHOW TABLES").fetchall()}
    assert {"decp", "acheteurs_marches", "titulaires_marches",
            "acheteurs_departement", "titulaires_departement"} <= tables


def test_query_marches_returns_polars_frame(built_db, monkeypatch):
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", str(built_db.parent / "source.parquet"))
    # Force src.db to load pointing at this test DB.
    import importlib, src.db
    importlib.reload(src.db)
    from src.db import query_marches
    frame = query_marches("acheteur_id = ?", ("A1",))
    assert isinstance(frame, pl.DataFrame)
    assert frame.height == 2
    assert set(frame["uid"].to_list()) == {"1", "2"}
```

- [ ] **Step 2: Run new tests and verify they fail**

Run: `uv run pytest tests/test_db.py -v -k "build or query_marches"`

Expected: FAIL with `ImportError: cannot import name 'build_database' from 'src.db'` (or similar on `query_marches`).

---

## Task 5: Implement `build_database` in `src/db.py`

**Files:**

- Modify: `src/db.py`

- [ ] **Step 1: Add imports and `build_database`**

Replace the contents of `src/db.py` with:

```python
import fcntl
import logging
import os
from pathlib import Path

import duckdb
import polars as pl
import polars.selectors as cs
from polars.exceptions import ComputeError
from time import sleep

logger = logging.getLogger("decp.info")


def should_rebuild(db_path: Path, parquet_path: Path) -> bool:
    db_path = Path(db_path)
    parquet_path = Path(parquet_path)
    if not db_path.exists():
        return True
    dev = os.getenv("DEVELOPMENT", "False").lower() == "true"
    force = os.getenv("REBUILD_DUCKDB", "False").lower() == "true"
    if dev and not force:
        return False
    return parquet_path.stat().st_mtime > db_path.stat().st_mtime


def _load_source_frame(parquet_path: Path) -> pl.DataFrame:
    """Read the source parquet and apply the row-level transforms.

    Kept here (not in utils.py) so src.db has no dependency on utils.
    Mirrors the behavior previously in utils.get_decp_data().
    """
    try:
        lff: pl.LazyFrame = pl.scan_parquet(str(parquet_path))
    except ComputeError:
        logger.info("Lecture du parquet échouée, nouvelle tentative dans 10s...")
        sleep(10)
        lff = pl.scan_parquet(str(parquet_path))

    lff = lff.sort(by=["dateNotification", "uid"], descending=True, nulls_last=True)
    lff = lff.filter(pl.col("donneesActuelles")).drop("donneesActuelles")

    # booleans_to_strings: true → "oui", false → "non"
    lff = lff.with_columns(
        pl.col(cs.Boolean).cast(pl.String).str.replace("true", "oui").str.replace("false", "non")
    )

    for col in ["acheteur_nom", "titulaire_nom"]:
        lff = lff.with_columns(
            pl.when(pl.col(col).is_null())
            .then(pl.lit("[Identifiant non reconnu dans la base INSEE]"))
            .otherwise(pl.col(col))
            .name.keep()
        )

    return lff.collect()


def build_database(db_path: Path, parquet_path: Path) -> None:
    """Build the DuckDB database atomically under an exclusive lock.

    Caller MUST hold the fcntl.flock on the .lock file.
    """
    db_path = Path(db_path)
    parquet_path = Path(parquet_path)
    tmp_path = db_path.with_suffix(".duckdb.tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    logger.info(f"Construction de la base DuckDB à partir de {parquet_path}...")
    frame = _load_source_frame(parquet_path)

    with duckdb.connect(str(tmp_path)) as w:
        w.register("frame", frame)
        w.execute("CREATE TABLE decp AS SELECT * FROM frame")
        w.execute(
            "CREATE TABLE acheteurs_marches AS "
            "SELECT DISTINCT uid, objet, acheteur_id FROM decp "
            "ORDER BY acheteur_id"
        )
        w.execute(
            "CREATE TABLE titulaires_marches AS "
            "SELECT DISTINCT uid, objet, titulaire_id FROM decp "
            "ORDER BY titulaire_id"
        )
        w.execute(
            "CREATE TABLE acheteurs_departement AS "
            "SELECT DISTINCT acheteur_id, acheteur_nom, acheteur_departement_code "
            "FROM decp ORDER BY acheteur_nom"
        )
        w.execute(
            "CREATE TABLE titulaires_departement AS "
            "SELECT DISTINCT titulaire_id, titulaire_nom, titulaire_departement_code "
            "FROM decp ORDER BY titulaire_nom"
        )

    os.replace(tmp_path, db_path)
    logger.info(f"Base DuckDB construite : {db_path}")
```

- [ ] **Step 2: Run build tests and verify they pass**

Run: `uv run pytest tests/test_db.py -v -k "build"`

Expected: 4 passed (`test_build_filters_donnees_actuelles`, `test_build_converts_booleans_to_oui_non`, `test_build_replaces_null_org_names`, `test_build_creates_derived_tables`).

---

## Task 6: Implement startup guard, read-only connection, `schema`, `get_cursor`, `query_marches`

**Files:**

- Modify: `src/db.py`

- [ ] **Step 1: Append startup logic and query helpers**

Add at the bottom of `src/db.py`:

```python
def _resolve_db_path() -> Path:
    parquet = os.getenv("DATA_FILE_PARQUET_PATH")
    if not parquet:
        raise RuntimeError("DATA_FILE_PARQUET_PATH is not set")
    return Path(parquet).parent / "decp.duckdb"


def _ensure_database() -> Path:
    db_path = _resolve_db_path()
    parquet_path = Path(os.getenv("DATA_FILE_PARQUET_PATH"))
    lock_path = db_path.with_suffix(".duckdb.lock")

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if should_rebuild(db_path, parquet_path):
            build_database(db_path, parquet_path)
    return db_path


DB_PATH = _ensure_database()
conn: duckdb.DuckDBPyConnection = duckdb.connect(str(DB_PATH), read_only=True)
schema: pl.Schema = conn.execute("SELECT * FROM decp LIMIT 0").pl().schema


def get_cursor() -> duckdb.DuckDBPyConnection:
    """Return a per-request cursor that shares the process-wide connection."""
    return conn.cursor()


def query_marches(
    where_sql: str = "TRUE",
    params: tuple = (),
    columns: list[str] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
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
    return get_cursor().execute(sql, list(params)).pl()
```

- [ ] **Step 2: Run the full `test_db.py` suite**

Run: `uv run pytest tests/test_db.py -v`

Expected: all tests pass (9 total).

- [ ] **Step 3: Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "Implémentation de build_database, query_marches et connexion DuckDB"
```

---

## Task 7: Write failing test for concurrent build locking

**Files:**

- Modify: `tests/test_db.py`

- [ ] **Step 1: Append a lock-serialization test**

```python
import threading


def test_concurrent_build_serialized(tmp_path, monkeypatch):
    """Two workers starting at once must not stomp on each other's tmp file."""
    parquet_path = tmp_path / "source.parquet"
    db_path = tmp_path / "decp.duckdb"

    pl.DataFrame(
        [
            {
                "uid": "1", "id": "1", "objet": "x",
                "acheteur_id": "A", "acheteur_nom": "n",
                "titulaire_id": "T", "titulaire_nom": "n",
                "acheteur_departement_code": "75",
                "titulaire_departement_code": "75",
                "titulaire_typeIdentifiant": "SIRET",
                "montant": 1.0,
                "dateNotification": datetime.date(2025, 1, 1),
                "donneesActuelles": True,
                "marcheInnovant": False,
            }
        ]
    ).write_parquet(parquet_path)

    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", str(parquet_path))

    from src.db import build_database, should_rebuild
    import fcntl

    errors: list[Exception] = []

    def worker():
        try:
            lock_path = db_path.with_suffix(".duckdb.lock")
            with open(lock_path, "w") as lock_fd:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                if should_rebuild(db_path, parquet_path):
                    build_database(db_path, parquet_path)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert db_path.exists()
    assert not db_path.with_suffix(".duckdb.tmp").exists()
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_db.py::test_concurrent_build_serialized -v`

Expected: PASS (the lock and `should_rebuild` short-circuit inside the worker already implements correct serialization — this test verifies the contract, no code changes needed).

If it fails, fix the issue in `src/db.py` (most likely: `build_database` does not clean up `tmp_path` when re-entered). Then re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_db.py
git commit -m "Test de sérialisation de la construction concurrente de la base"
```

---

## Task 8: Make `tests/conftest.py` rebuild the DuckDB with the test parquet

**Files:**

- Modify: `tests/conftest.py`
- Modify: `pyproject.toml` (pytest env block)

- [ ] **Step 1: Force a fresh DuckDB rebuild in the test session**

The existing `test_data` fixture writes `tests/test.parquet` at session start. We must delete any leftover `tests/decp.duckdb` before `src.db` is imported by the app, because `src.db` is imported at module load by `src/utils.py`, which is in turn imported by pages.

Update `tests/conftest.py`:

```python
import datetime
import os
from pathlib import Path

import polars as pl
import pytest
from selenium.webdriver.chrome.options import Options


@pytest.fixture(scope="session", autouse=True)
def test_data():
    data = [
        {
            "uid": "1",
            "id": "1",
            "acheteur_nom": "ACHETEUR 1",
            "acheteur_id": "123",
            "titulaire_nom": "TITULAIRE 1",
            "titulaire_id": "345",
            "montant": 10,
            "dateNotification": datetime.date(2025, 1, 1),
            "codeCPV": "71600000",
            "donneesActuelles": True,
            "acheteur_departement_code": "75",
            "acheteur_departement_nom": "Paris",
            "acheteur_commune_nom": "Paris",
            "titulaire_departement_code": "35",
            "titulaire_departement_nom": "Ille-et-Vilaine",
            "titulaire_commune_nom": "Rennes",
            "titulaire_distance": 10,
            "titulaire_typeIdentifiant": "SIRET",
            "objet": "Objet test",
            "dureeRestanteMois": 12,
            "lieuExecution_code": "75001",
            "sourceFile": "test.xml",
            "sourceDataset": "test_dataset",
            "datePublicationDonnees": datetime.date(2025, 1, 1),
            "considerationsSociales": "",
            "considerationsEnvironnementales": "",
            "type": "Marché",
            "acheteur_categorie": "Collectivité",
            "titulaire_categorie": "PME",
        }
    ]
    parquet_path = Path(os.path.abspath("tests/test.parquet"))
    db_path = parquet_path.parent / "decp.duckdb"
    print(f"Writing test data to: {parquet_path}")

    pl.DataFrame(data).write_parquet(parquet_path)

    # Remove any stale DuckDB from a previous run so src.db rebuilds from
    # the freshly-written parquet at import time.
    for artifact in (db_path, db_path.with_suffix(".duckdb.tmp")):
        if artifact.exists():
            artifact.unlink()

    yield str(parquet_path)


def pytest_setup_options():
    options = Options()
    options.add_argument("--window-size=1200,1200 ")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": "/home/colin/git/decp.info",
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    return options
```

- [ ] **Step 2: Verify existing tests still import cleanly**

Run: `uv run pytest tests/test_db.py -v`

Expected: all 10 DB tests still pass (the conftest changes only affect integration tests).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "Suppression de la base DuckDB de test obsolète avant chaque session"
```

---

## Task 9: Migrate `src/utils.py` — introduce `src.db` imports, keep old globals

**Files:**

- Modify: `src/utils.py`

This task does **not** remove the old globals yet. It wires `src.db` in and re-points `schema` / `columns` so pages can start using them without a flag day.

- [ ] **Step 1: Import from `src.db` at the top of `utils.py`**

After the `from unidecode import unidecode` line, add:

```python
from src.db import conn as duckdb_conn  # noqa: F401  (exposed for convenience)
from src.db import get_cursor, query_marches, schema  # noqa: F401
```

- [ ] **Step 2: Replace the module-level assignments at the bottom**

Find lines 891–913 (the block starting with `df: pl.DataFrame = get_decp_data()`).

Replace the block with:

```python
df: pl.DataFrame = get_decp_data()
# schema and columns now come from src.db; overwrite in case any local code
# still reads them directly from utils.
schema = schema  # re-exported from src.db
columns = schema.names()

df_acheteurs = get_org_data(df, "acheteur")
df_titulaires = get_org_data(df, "titulaire")
df_acheteurs_departement: pl.DataFrame = (
    df_acheteurs.select(["acheteur_id", "acheteur_nom", "acheteur_departement_code"])
    .unique()
    .sort("acheteur_nom")
)
df_titulaires_departement: pl.DataFrame = (
    df_titulaires.select(
        ["titulaire_id", "titulaire_nom", "titulaire_departement_code"]
    )
    .unique()
    .sort("titulaire_nom")
)
df_acheteurs_marches: pl.DataFrame = (
    df.select("uid", "objet", "acheteur_id").unique().sort("acheteur_id")
)
df_titulaires_marches: pl.DataFrame = (
    df.select("uid", "objet", "titulaire_id").unique().sort("titulaire_id")
)
```

No removals — we keep the old globals alive. Pages that already use `schema` / `columns` now transparently get them from `src.db`.

- [ ] **Step 3: Run the Selenium test suite**

Run: `uv run pytest tests/test_main.py -v`

Expected: all tests pass. The app loads; nothing has changed behaviorally yet.

- [ ] **Step 4: Commit**

```bash
git add src/utils.py
git commit -m "Intégration de src.db dans utils (coexistence avec les globaux)"
```

---

## Task 10: Migrate `src/pages/marche.py` (1 call site)

**Files:**

- Modify: `src/pages/marche.py`

- [ ] **Step 1: Replace `df` with `query_marches`**

Edit the import block:

```python
from src.utils import (
    data_schema,
    format_values,
    make_org_jsonld,
    meta_content,
    unformat_montant,
)
from src.db import query_marches
```

Replace the body of `get_marche_data`:

```python
def get_marche_data(url) -> tuple[dict, list]:
    marche_uid = url.split("/")[-1]

    # Filtre SQL côté DuckDB, puis Polars pour le post-traitement
    dff_marche = query_marches("uid = ?", (marche_uid,))
    if dff_marche.height == 0:
        return {}, []

    lff = dff_marche.lazy()
    dff_titulaires = lff.select(cs.starts_with("titulaire")).collect(engine="streaming")
    dff_marche_unique = lff.unique("uid").collect(engine="streaming")
    dff_marche_unique = format_values(dff_marche_unique)

    return dff_marche_unique.to_dicts()[0], dff_titulaires.to_dicts()
```

- [ ] **Step 2: Smoke-test**

Run: `uv run pytest tests/test_main.py -v`

Expected: all tests pass.

Manually: `uv run run.py`, navigate to `/marches/<any_uid_from_test_data>` (e.g. `/marches/1`), confirm page renders with the buyer, amount, and titulaire list.

- [ ] **Step 3: Commit**

```bash
git add src/pages/marche.py
git commit -m "marche.py : utilisation de query_marches au lieu du df global"
```

---

## Task 11: Migrate `src/pages/acheteur.py`

**Files:**

- Modify: `src/pages/acheteur.py`

- [ ] **Step 1: Replace `df` imports**

Update the import block:

```python
from src.utils import (
    columns,
    df_acheteurs,
    filter_table_data,
    format_number,
    get_annuaire_data,
    get_button_properties,
    get_default_hidden_columns,
    # ... any other existing non-df imports
)
from src.db import query_marches, schema
```

(Remove `df` from the `src.utils` import list.)

- [ ] **Step 2: Replace `df.columns` at line 73**

```python
columns=[{"id": col, "name": col} for col in schema.names()],
```

- [ ] **Step 3: Replace `df.collect_schema()` at line 303**

```python
dff = pl.DataFrame(schema=schema)
```

- [ ] **Step 4: Replace `df.lazy().filter(...)` in `get_acheteur_marches_data`**

```python
def get_acheteur_marches_data(url, ach_year: str) -> tuple:
    acheteur_siret = url.split("/")[-1]
    lff = query_marches("acheteur_id = ?", (acheteur_siret,)).lazy()
    if ach_year and ach_year != "Toutes les années":
        ach_year = int(ach_year)
        lff = lff.filter(pl.col("dateNotification").dt.year() == ach_year)
    lff = lff.sort(["dateNotification", "uid"], descending=True, nulls_last=True)
    dff: pl.DataFrame = lff.collect(engine="streaming")
    download_disabled, download_text, download_title = get_button_properties(dff.height)
    data = dff.to_dicts()
    return data, download_disabled, download_text, download_title
```

- [ ] **Step 5: Run tests and smoke-test**

Run: `uv run pytest tests/test_main.py -v`

Manually: `uv run run.py`, navigate to `/acheteurs/123` (test data SIRET), confirm KPIs, charts, and table render.

- [ ] **Step 6: Commit**

```bash
git add src/pages/acheteur.py
git commit -m "acheteur.py : migration vers query_marches et schema depuis src.db"
```

---

## Task 12: Migrate `src/pages/titulaire.py`

**Files:**

- Modify: `src/pages/titulaire.py`

- [ ] **Step 1: Replace imports and call sites**

Remove `df` from the `src.utils` import list. Add:

```python
from src.db import query_marches, schema
```

- [ ] **Step 2: Replace `df.columns` at line 72**

```python
columns=[{"id": col, "name": col} for col in schema.names()],
```

- [ ] **Step 3: Replace `df.lazy().filter(...)` in `get_titulaire_marches_data`**

```python
def get_titulaire_marches_data(url, titulaire_year: str) -> tuple:
    titulaire_siret = url.split("/")[-1]
    lff = query_marches(
        "titulaire_id = ? AND titulaire_typeIdentifiant = 'SIRET'",
        (titulaire_siret,),
    ).lazy()
    if titulaire_year and titulaire_year != "Toutes les années":
        lff = lff.filter(
            pl.col("dateNotification").cast(pl.String).str.starts_with(titulaire_year)
        )
    lff = lff.sort(["dateNotification", "uid"], descending=True, nulls_last=True)
    lff = lff.fill_null("")
    dff: pl.DataFrame = lff.collect(engine="streaming")
    # ... rest of function unchanged
```

- [ ] **Step 4: Run tests and smoke-test**

Run: `uv run pytest tests/test_main.py -v`

Manually: `uv run run.py`, navigate to `/titulaires/345` (test SIRET), confirm it renders.

- [ ] **Step 5: Commit**

```bash
git add src/pages/titulaire.py
git commit -m "titulaire.py : migration vers query_marches et schema depuis src.db"
```

---

## Task 13: Migrate `src/pages/arbre/departement.py`

**Files:**

- Modify: `src/pages/arbre/departement.py`

- [ ] **Step 1: Replace imports and queries**

```python
import polars as pl
from dash import Input, Output, callback, dcc, html, register_page

from src.utils import departements
from src.db import get_cursor

# ... (register_page and layout unchanged) ...


@callback(
    Output(component_id="departement_marches", component_property="children"),
    Input(component_id="departement_url", component_property="pathname"),
)
def departement_marches(url):
    departement = url.split("/")[-1]

    def make_link_list(org_type) -> list:
        table = (
            "acheteurs_departement" if org_type == "acheteur"
            else "titulaires_departement" if org_type == "titulaire"
            else None
        )
        if table is None:
            raise ValueError
        col_prefix = org_type
        rows = get_cursor().execute(
            f"SELECT {col_prefix}_id, {col_prefix}_nom "
            f"FROM {table} "
            f"WHERE {col_prefix}_departement_code = ? "
            f"ORDER BY {col_prefix}_nom",
            [departement],
        ).fetchall()

        link_list = []
        for org_id, org_nom in rows:
            li = html.Li(
                [
                    dcc.Link(
                        org_nom,
                        href=url + f"/{org_type}/{org_id}",
                        title=f"Marchés publics de {org_nom}",
                    ),
                    " ",
                    dcc.Link(
                        "(page dédiée)",
                        href=f"/{org_type}s/{org_id}",
                        title=f"Page dédiée aux marchés publics de {org_nom}",
                    ),
                ]
            )
            link_list.append(li)
        return link_list

    content = [
        html.H3("Acheteurs publics du département"),
        html.Ul(make_link_list("acheteur")),
        html.H3("Titulaires du département"),
        html.Ul(make_link_list("titulaire")),
    ]
    return content
```

- [ ] **Step 2: Run tests and smoke-test**

Run: `uv run pytest tests/test_main.py -v`

Manually: `uv run run.py`, navigate to `/departements/75`, confirm list of acheteurs and titulaires renders.

- [ ] **Step 3: Commit**

```bash
git add src/pages/arbre/departement.py
git commit -m "arbre/departement.py : requête DuckDB directe pour les listes départementales"
```

---

## Task 14: Migrate `src/pages/arbre/liste_marches_org.py`

**Files:**

- Modify: `src/pages/arbre/liste_marches_org.py`

- [ ] **Step 1: Replace imports and queries**

```python
import polars as pl
from dash import Input, Output, callback, dcc, html, register_page

from src.utils import df_acheteurs, df_titulaires
from src.db import get_cursor

name = "Liste des marchés publics"


def make_org_nom_verbe(org_type, org_id) -> tuple:
    if org_type == "titulaire":
        source = df_titulaires
        verbe = "remportés"
    elif org_type == "acheteur":
        source = df_acheteurs
        verbe = "attribués"
    else:
        raise ValueError

    org_nom = (
        source.filter(pl.col(f"{org_type}_id") == org_id)
        .select(f"{org_type}_nom")
        .item(0, 0)
    )
    return org_nom, verbe


# ... (register_page / layout unchanged) ...


@callback(
    Output(component_id="liste_marches", component_property="children"),
    Input(component_id="liste_marches_url", component_property="pathname"),
)
def liste_marches(url):
    org_type = url.split("/")[-2]
    org_id = url.split("/")[-1]

    def make_link_list() -> list:
        table = (
            "acheteurs_marches" if org_type == "acheteur"
            else "titulaires_marches" if org_type == "titulaire"
            else None
        )
        if table is None:
            raise ValueError
        rows = get_cursor().execute(
            f"SELECT uid, objet FROM {table} WHERE {org_type}_id = ?",
            [org_id],
        ).fetchall()

        return [
            html.Li(
                dcc.Link(
                    objet,
                    href=f"/marches/{uid}",
                    title=f"Marchés public attribué : {objet}",
                )
            )
            for uid, objet in rows
        ]

    nom, verbe = make_org_nom_verbe(org_type, org_id)
    return [
        html.H3(f"Marchés publics {verbe} par {nom}"),
        html.Ul(make_link_list()),
    ]
```

- [ ] **Step 2: Run tests and smoke-test**

Run: `uv run pytest tests/test_main.py -v`

Manually: `uv run run.py`, navigate to `/departements/75/acheteur/123`, confirm list of marchés renders.

- [ ] **Step 3: Commit**

```bash
git add src/pages/arbre/liste_marches_org.py
git commit -m "arbre/liste_marches_org.py : requêtes DuckDB pour les listes de marchés"
```

---

## Task 15: Migrate `src/pages/tableau.py`

**Files:**

- Modify: `src/pages/tableau.py`

- [ ] **Step 1: Replace imports**

Remove `df` from `src.utils` imports; remove `schema` from `src.utils` imports if present, re-import it from `src.db`:

```python
from src.utils import (
    columns,
    filter_table_data,
    get_default_hidden_columns,
    invert_columns,
    logger,
    meta_content,
    prepare_table_data,
    sort_table_data,
    update_date_iso,
)
from src.db import query_marches, schema
```

- [ ] **Step 2: Replace `df.columns` at line 64**

```python
columns=[{"id": col, "name": col} for col in schema.names()],
```

- [ ] **Step 3: Replace `df.width` at line 131**

In the `dcc.Markdown` block, replace `{str(df.width)}` with `{len(schema.names())}`.

- [ ] **Step 4: Replace `df.lazy()` at line 319 in `download_data`**

```python
def download_data(n_clicks, filter_query, sort_by, hidden_columns: list = None):
    lff: pl.LazyFrame = query_marches().lazy()

    if hidden_columns:
        lff = lff.drop(hidden_columns)

    if filter_query:
        lff = filter_table_data(lff, filter_query, "tab download")

    if sort_by and len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    def to_bytes(buffer):
        lff.collect(engine="streaming").write_excel(buffer, worksheet="DECP")

    date = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    return dcc.send_bytes(to_bytes, filename=f"decp_{date}.xlsx")
```

Note: `query_marches()` with no arguments returns the full table into a Polars frame, which is then lazily filtered. This is equivalent to today's `df.lazy()` — memory profile is identical to the current path during download. We accept this: the download endpoint is infrequent and downloads are bounded by `filter_query` in practice. A future optimization could push the filter into SQL, but it requires reimplementing `filter_table_data` in SQL. Out of scope.

- [ ] **Step 5: Run tests and smoke-test**

Run: `uv run pytest tests/test_main.py -v`

Manually: `uv run run.py`, navigate to `/tableau`, apply a filter, try the download button.

- [ ] **Step 6: Commit**

```bash
git add src/pages/tableau.py
git commit -m "tableau.py : migration vers query_marches et schema depuis src.db"
```

---

## Task 16: Migrate `src/pages/observatoire.py`

**Files:**

- Modify: `src/pages/observatoire.py`

- [ ] **Step 1: Replace imports**

Remove `df` from `src.utils` imports; add `from src.db import query_marches, schema`. The `columns` import from `src.utils` stays (it already resolves to `schema.names()` via Task 9).

- [ ] **Step 2: Replace `df.columns` at line 75**

Wherever `df.columns` is used, replace with `schema.names()`.

- [ ] **Step 3: Replace `df.lazy()` at lines 668, 793, 884**

Each call site currently reads `df.lazy()`. Replace with `query_marches().lazy()`:

```python
# Line ~668
lff: pl.LazyFrame = query_marches().lazy()
lff = prepare_dashboard_data(lff=lff, **filter_params)

# Line ~793
lff = prepare_dashboard_data(lff=query_marches().lazy(), **(filter_params or {}))

# Line ~884
lff = prepare_dashboard_data(lff=query_marches().lazy(), **(filter_params or {}))
```

Same caveat as `tableau.py` download: this materializes the full table before filtering in Polars. Since `observatoire` results are already cached via `@cache.memoize(timeout=3600)`, the rebuild cost is amortized. Future optimization (pushing `prepare_dashboard_data` filters into SQL) is tracked separately and out of scope.

- [ ] **Step 4: Run tests and smoke-test**

Run: `uv run pytest tests/test_main.py -v`

Manually: `uv run run.py`, navigate to `/observatoire`, apply and remove filters, confirm charts render.

- [ ] **Step 5: Commit**

```bash
git add src/pages/observatoire.py
git commit -m "observatoire.py : migration vers query_marches et schema depuis src.db"
```

---

## Task 17: Migrate `src/figures.py`

**Files:**

- Modify: `src/figures.py`

- [ ] **Step 1: Remove `df` from the `src.utils` import block**

```python
from src.utils import (
    add_links,
    data_schema,
    departements_geojson,
    format_number,
    setup_table_columns,
)
from src.db import schema
```

- [ ] **Step 2: Replace `df.columns` at line 777**

```python
for col in schema.names()
```

- [ ] **Step 3: Run tests and smoke-test**

Run: `uv run pytest tests/test_main.py -v`

Manually: `uv run run.py`, exercise pages that render charts (`/acheteurs/123`, `/observatoire`).

- [ ] **Step 4: Commit**

```bash
git add src/figures.py
git commit -m "figures.py : suppression de l'import df global, usage de schema depuis src.db"
```

---

## Task 18: Remove the in-memory globals from `src/utils.py`

**Files:**

- Modify: `src/utils.py`

No page now references `df`, `df_acheteurs_departement`, `df_titulaires_departement`, `df_acheteurs_marches`, `df_titulaires_marches` (verify with grep below). `df_acheteurs` and `df_titulaires` remain (homepage search).

- [ ] **Step 1: Verify no consumers remain**

Run:

```bash
rg '\bdf\b|df_acheteurs_departement|df_titulaires_departement|df_acheteurs_marches|df_titulaires_marches' src/
```

Expected: only matches inside `src/utils.py` (the globals themselves and `get_decp_data`/`get_org_data`) and no matches in `src/pages/` or `src/figures.py`.

- [ ] **Step 2: Repoint `df_acheteurs` / `df_titulaires` to DuckDB**

In `src/utils.py`, replace the bottom-of-file block (lines 891–913 in the current file) with:

```python
# df_acheteurs / df_titulaires sont conservés en mémoire pour alimenter
# la recherche sur la page d'accueil (autocomplétion, filtrage par sous-chaîne
# à chaque frappe). Les colonnes reproduisent la sortie historique de
# get_org_data(df, org_type).
def _build_org_frame(org_type: str) -> pl.DataFrame:
    org_cols = [
        c for c in schema.names()
        if c.startswith(f"{org_type}_")
        and c not in (f"{org_type}_latitude", f"{org_type}_longitude")
    ]
    select_list = ", ".join(org_cols)
    group_list = ", ".join(org_cols)
    sql = (
        f"SELECT {select_list}, COUNT(*) AS \"Marchés\" "
        f"FROM decp GROUP BY {group_list}"
    )
    return get_cursor().execute(sql).pl()


df_acheteurs = _build_org_frame("acheteur")
df_titulaires = _build_org_frame("titulaire")

columns = schema.names()
```

- [ ] **Step 3: Delete now-unused functions**

Remove `get_decp_data` (lines 234–272) — it has been inlined into `src.db._load_source_frame`. Remove `get_org_data` (lines 275–284) — replaced by `_build_org_frame`.

- [ ] **Step 4: Remove the `from polars.exceptions import ComputeError` import if no longer used**

Run:

```bash
rg 'ComputeError' src/utils.py
```

If empty, remove the import line near the top of `utils.py`.

Same check for `from time import localtime, sleep`:

```bash
rg '\bsleep\b|\blocaltime\b' src/utils.py
```

Remove anything unused.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`

Expected: all tests pass.

- [ ] **Step 6: Manual smoke test of every page**

```bash
uv run run.py
```

Visit in a browser:

- `/` (recherche) — type in the acheteur and titulaire search fields, confirm autocomplete works.
- `/acheteurs/123` — confirm renders.
- `/titulaires/345` — confirm renders.
- `/marches/1` — confirm renders.
- `/tableau` — filter, sort, download.
- `/observatoire` — apply filters, confirm charts.
- `/departements` and `/departements/75` — confirm lists.
- `/departements/75/acheteur/123` — confirm marchés list.

- [ ] **Step 7: Commit**

```bash
git add src/utils.py
git commit -m "Suppression des dataframes globaux remplacés par DuckDB"
```

---

## Task 19: Measure memory impact

**Files:** none (documentation commit only)

- [ ] **Step 1: Measure RSS before (from a reference point on `main`)**

Check out `main` in a separate worktree, start the app pointing at `decp_prod.parquet`, wait for import to finish, then:

```bash
ps -o rss= -p $(pgrep -f "gunicorn app:server" | head -1)
```

Record the value (expect ~several GB with 1.5M rows in memory).

- [ ] **Step 2: Measure RSS after (on this branch)**

Back on the feature branch, same command. Record the value.

- [ ] **Step 3: Document the result**

Append a `## Outcome` section to the spec file `docs/superpowers/specs/2026-04-15-duckdb-migration-design.md` with the two RSS measurements and the ratio.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-04-15-duckdb-migration-design.md
git commit -m "Mesure de l'impact mémoire post-migration DuckDB"
```

---

## Task 20: Final verification and branch readiness

- [ ] **Step 1: Run full test suite clean**

```bash
uv run pytest -v
```

Expected: all green.

- [ ] **Step 2: Run pre-commit hooks on all files**

```bash
pre-commit run --all-files
```

Expected: all hooks pass.

- [ ] **Step 3: Confirm no stray references remain**

```bash
rg '\bdf\b' src/ | rg -v 'dff|df_acheteurs|df_titulaires|data_schema|self\.df'
```

Expected: no results (or only matches inside comments / docstrings).

- [ ] **Step 4: Verify the DB file is ignored by git**

```bash
git status --ignored | rg duckdb
```

Expected: `decp.duckdb` (and `.tmp`, `.lock` if present) listed under ignored files.

Ready for PR / merge via the `finishing-a-development-branch` skill.

---

## Self-Review Notes

- **Spec coverage:** every section of `docs/superpowers/specs/2026-04-15-duckdb-migration-design.md` maps to a task:

  - Goal / Approach summary → Task 6 (`query_marches`), Tasks 10–17 (migration), Task 18 (in-memory helpers).
  - Cache invalidation rule → Tasks 2–3 (`should_rebuild` + tests).
  - Concurrency → Tasks 5–7 (`build_database` + lock test).
  - Build logic → Task 5 (reuses `_load_source_frame` with Polars transforms).
  - Module layout — `src/db.py` public surface → Task 6.
  - Configuration (`DATA_FILE_PARQUET_PATH` reused; no new env var except `REBUILD_DUCKDB`) → Task 6 (`_resolve_db_path`).
  - Testing → Tasks 2, 4, 7, 8.
  - Migration order → Tasks 10 (marche), 11 (acheteur), 12 (titulaire), 13–14 (arbre), 15 (tableau), 16 (observatoire), 17 (figures), 18 (remove globals).
  - Out-of-scope items (cache.py, observatoire-localstorage work, parquet schema, SQL views) → not touched.

- **Type consistency:** `schema` is `pl.Schema` everywhere; `conn` is `duckdb.DuckDBPyConnection`; `query_marches` signature matches the spec. `_load_source_frame` is internal to `src.db` (single underscore, not exported).

- **Placeholder scan:** no "TBD", no "similar to task N"; each step shows complete code or exact commands.
