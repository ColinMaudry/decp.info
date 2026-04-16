# DuckDB migration — design spec

**Date:** 2026-04-15
**Branch:** dev
**Status:** Approved, ready for planning

## Goal

Replace the global Polars dataframes that `src/utils.py` materializes at import time (`df` and the five derived frames, lines 891–913) with a DuckDB database on disk. The main table holds ~1.5M rows from `decp_prod.parquet`. Per-request queries pull only what each page needs, dramatically reducing steady-state RSS memory.

Polars stays the primary API for small result sets and post-processing. DuckDB carries the heavy filtering, joining, and aggregation.

## Approach summary

- **Approach A — compatibility layer.** A new `src/db.py` module exposes a `query_marches(where_sql, params, columns, ...)` helper that runs SQL and returns a `pl.DataFrame`. Most existing `df.filter(pl.col(...) == x)` call sites translate mechanically to `query_marches("col = ?", (x,))`. The shape of downstream Polars code is unchanged.
- **Two small helpers stay in memory.** `df_acheteurs` and `df_titulaires` (tens of thousands of rows, consumed by the autocomplete search on every keystroke) are kept as module-level Polars frames. They are populated from DuckDB at import time, not from Parquet.
- **Four derived tables live in DuckDB**, built at startup alongside the main table: `acheteurs_marches`, `titulaires_marches`, `acheteurs_departement`, `titulaires_departement`.
- **Connection model.** One read-only `duckdb.connect(..., read_only=True)` at module load, shared across the process. `conn.cursor()` per Dash callback for thread-safety. The read-write connection is short-lived and only used during the startup build phase.

## Cache invalidation rule

At startup, rebuild the DuckDB file if:

1. **The DB file does not exist**, OR
2. **`decp_prod.parquet.mtime > duckdb.mtime`**, **unless** `DEVELOPMENT=true` and `REBUILD_DUCKDB != true` — in which case the DB stays as-is (fast dev reloads).

Production auto-rebuilds when the source Parquet is newer. Development keeps a stable DB across reloads unless the developer explicitly sets `REBUILD_DUCKDB=true` to force a rebuild.

## Concurrency

Multi-worker Gunicorn startup and crashed-mid-build scenarios are handled by a file lock, not by polling for the tmp file's existence:

```python
with open(DB_PATH.with_suffix(".duckdb.lock"), "w") as lock_fd:
    fcntl.flock(lock_fd, fcntl.LOCK_EX)          # blocks if another worker is building
    if should_rebuild(DB_PATH, PARQUET_PATH):
        build_database(DB_PATH, PARQUET_PATH)
conn = duckdb.connect(str(DB_PATH), read_only=True)
```

- Worker A acquires the lock, builds, atomically renames tmp → final, releases the lock.
- Worker B blocks on `flock`, then re-checks `should_rebuild`, sees the fresh DB, skips building.
- `fcntl.flock` is auto-released on process death, so a crash never deadlocks the next worker.
- `build_database` unlinks any pre-existing tmp file before starting (safe because it holds the lock) — handles an abandoned tmp from a crashed previous build.

## Build logic

The build keeps **one source of truth** for transforms by reusing the existing Polars pipeline:

```python
def build_database(db_path, parquet_path):
    tmp_path = db_path.with_suffix(".duckdb.tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    frame = get_decp_data()   # existing function in utils.py
    with duckdb.connect(str(tmp_path)) as w:
        w.register("frame", frame)
        w.execute("CREATE TABLE decp AS SELECT * FROM frame")
        w.execute("CREATE TABLE acheteurs_marches AS "
                  "SELECT DISTINCT uid, objet, acheteur_id FROM decp "
                  "ORDER BY acheteur_id")
        w.execute("CREATE TABLE titulaires_marches AS "
                  "SELECT DISTINCT uid, objet, titulaire_id FROM decp "
                  "ORDER BY titulaire_id")
        w.execute("CREATE TABLE acheteurs_departement AS "
                  "SELECT DISTINCT acheteur_id, acheteur_nom, acheteur_departement_code "
                  "FROM decp ORDER BY acheteur_nom")
        w.execute("CREATE TABLE titulaires_departement AS "
                  "SELECT DISTINCT titulaire_id, titulaire_nom, titulaire_departement_code "
                  "FROM decp ORDER BY titulaire_nom")
    os.replace(tmp_path, db_path)
```

Why Polars, not SQL, for the row-level transforms:

- `booleans_to_strings` is not a simple cast — it replaces `true`/`false` with `"oui"`/`"non"` on every boolean column. Reimplementing in SQL risks drifting from the Polars version.
- The null-name replacement (`acheteur_nom`, `titulaire_nom` → `"[Identifiant non reconnu dans la base INSEE]"`) is also easier to keep identical in Polars.
- `w.register("frame", frame)` is zero-copy. The memory spike is one-time during build and released when the write connection closes.

`os.replace` is atomic on POSIX — the read-only connection that opens next always sees a complete DB.

## Module layout

### New: `src/db.py`

```python
conn: duckdb.DuckDBPyConnection       # read-only, module-level
schema: pl.Schema                     # from conn.execute("SELECT * FROM decp LIMIT 0").pl().schema

def get_cursor() -> duckdb.DuckDBPyConnection: ...
def query_marches(where_sql: str = "TRUE",
                  params: tuple = (),
                  columns: list[str] | None = None,
                  order_by: str | None = None,
                  limit: int | None = None) -> pl.DataFrame: ...
def should_rebuild(db_path: Path, parquet_path: Path) -> bool: ...
def build_database(db_path: Path, parquet_path: Path) -> None: ...
```

Only imports: `polars`, `duckdb`, `os`, `fcntl`, `pathlib`, `logging`. No app modules — prevents circular imports.

### Changes to `src/utils.py`

- `df: pl.DataFrame = get_decp_data()` — **removed** (after migration).
- `df_acheteurs`, `df_titulaires` — **kept as Polars globals**, populated via DuckDB at import time. The query mirrors today's `get_org_data(df, org_type)`: select all columns whose name starts with `acheteur_` (or `titulaire_`) except the `_latitude` / `_longitude` pair, plus `COUNT(*) AS "Marchés"`, grouped by the same set. Implementation can either:

  - enumerate the columns by filtering `schema.names()` at import time and build the `SELECT` / `GROUP BY` strings, or
  - call `get_org_data()` once against a small Polars frame returned by `SELECT <org_ cols> FROM decp`.

  Feeds `search_org` unchanged.

- `df_acheteurs_marches`, `df_titulaires_marches`, `df_acheteurs_departement`, `df_titulaires_departement` — **removed** as Python globals. Call sites query the corresponding DuckDB tables.
- `schema` — imported from `src/db.py` (stays a `pl.Schema` — so `schema.names()` and dtype lookups both work, no call-site changes beyond `acheteur.py:303`).
- `columns` — replaced with `schema.names()`.
- `get_decp_data()` — **kept** (used by `build_database`).
- `get_org_data()` — can be removed once `df_acheteurs` / `df_titulaires` are populated from DuckDB directly.

### Call-site translations

| Before (Polars global)                                       | After                                                                             |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| `df.filter(pl.col("acheteur_id") == aid)`                    | `query_marches("acheteur_id = ?", (aid,))`                                        |
| `df.filter(pl.col("uid") == uid).row(0, named=True)`         | `query_marches("uid = ?", (uid,)).row(0, named=True)`                             |
| `df.select("uid","objet","acheteur_id").filter(...)`         | `query_marches("...", (...), columns=["uid","objet","acheteur_id"])`              |
| `df.columns`                                                 | `schema.names()`                                                                  |
| `df_acheteurs_marches.filter(...)`                           | `get_cursor().execute("SELECT ... FROM acheteurs_marches WHERE ...", [...]).pl()` |
| `pl.DataFrame(schema=df.collect_schema())` (acheteur.py:303) | `pl.DataFrame(schema=schema)`                                                     |

Heavy dashboard aggregations (observatoire, tableau full-scan) use raw SQL via `get_cursor().execute(...).pl()` rather than the helper.

## Configuration

- **`DATA_FILE_PARQUET_PATH`** — unchanged.
- **DuckDB file location** — computed: `Path(DATA_FILE_PARQUET_PATH).parent / "decp.duckdb"`. No new env var.
- **`REBUILD_DUCKDB`** — new, optional, default `false`. In development, setting this to `true` forces a rebuild when the parquet is newer.
- **`DEVELOPMENT`** — unchanged; now also gates the auto-rebuild behavior per the rule above.

## Testing

- `tests/conftest.py` (or a startup hook in `src/db.py`) ensures the test run builds the DuckDB in a temp directory derived from the parquet path — `tests/test.parquet` → `tests/decp.duckdb`. This file is added to `.gitignore`.
- Tests already set `DEVELOPMENT=true`; they must also set `REBUILD_DUCKDB=true` on cold test runs to force a fresh build from the test parquet.
- The existing Selenium suite exercises every page and is the primary acceptance signal.

## Migration order

Incremental — `df` global coexists with `src/db.py` until every page is migrated.

1. **Add `src/db.py`** (build, lock, `query_marches`, `schema`). `df` global unchanged.
2. **Migrate `marche.py`** — single-row lookup by `uid`, one call site.
3. **Migrate `acheteur.py`, `titulaire.py`** — filter by id.
4. **Migrate `arbre/departement.py`, `arbre/liste_marches_org.py`** — use the new derived DuckDB tables.
5. **Migrate `tableau.py`** — may need raw SQL.
6. **Migrate `observatoire.py`** — heaviest aggregations, most likely raw SQL.
7. **Migrate `figures.py`** — uses `df` in chart generation.
8. **Remove** `df`, `df_*_marches`, `df_*_departement` globals, `get_org_data()`, and the `df = get_decp_data()` call from `utils.py`. Move `schema` / `columns` exports to `src/db.py`.

### Verification gates

- `uv run pytest` green after every page migration.
- Manual smoke test via `uv run run.py` of the migrated page before proceeding.
- RSS memory measurement (`ps -o rss`) of a cold `gunicorn app:server` with the prod parquet, before and after, to confirm the memory reduction.

## Out of scope

- Changes to `src/cache.py` (flask-caching stays).
- The in-progress observatoire-localstorage-filters work on `dev`.
- Schema changes to the parquet.
- SQL views beyond the four derived tables.
- Multi-database or replication setups.

## Risks and mitigations

| Risk                                                                          | Mitigation                                                                                                                       |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `booleans_to_strings` reimplemented in SQL and drifts from Polars version     | Transforms stay in Polars via `w.register("frame", frame)`. One source of truth.                                                 |
| Two Gunicorn workers rebuild concurrently                                     | `fcntl.flock` serializes the build; second worker re-checks and skips.                                                           |
| Crashed build leaves stale `.tmp` file                                        | Build unlinks any pre-existing tmp before starting (safe under lock).                                                            |
| `schema` shape change breaks `acheteur.py:303`                                | `schema` stays a `pl.Schema` object, not a list. One call site (`collect_schema()` → module `schema`) updated.                   |
| Test runs inherit a stale DuckDB from a previous run with a different parquet | Tests force `REBUILD_DUCKDB=true` on cold runs; test DB added to `.gitignore`.                                                   |
| Read-only connection opened before build finishes in another worker           | Lock held across build + rename; read-only `connect` happens after lock release. Atomic `os.replace` guarantees a complete file. |

## Outcome

### Memory impact

Memory measurement against the production parquet (`decp_prod.parquet`, ~1.5M rows) requires a running gunicorn process with access to the production data file. The measurement was deferred to the post-merge smoke test on the staging server (test.decp.info).

**Expected reduction:** The removed globals (`df`, `df_acheteurs_departement`, `df_titulaires_departement`, `df_acheteurs_marches`, `df_titulaires_marches`) previously materialised the full 1.5M-row Parquet in memory as multiple Polars frames. At ~300 bytes/row × 5 frames, steady-state RSS reduction is estimated at **1–2 GB per worker**. The retained `df_acheteurs` and `df_titulaires` (autocomplete search) represent only the distinct-organisation subset (~tens of thousands of rows) and are negligible.

**What remains in memory:**

- `df_acheteurs` — distinct acheteurs with Marchés count (populated from DuckDB at startup)
- `df_titulaires` — same for titulaires
- DuckDB's own page cache (disk-backed, grows under load, evicted by OS)

All per-request data is fetched from DuckDB and discarded after the callback returns.
