# API privée decp.info — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer une API HTTP privée tabulaire `/api/v1/data` protégée par tokens Bearer, documentée via OpenAPI/Swagger, avec suivi de consommation (Matomo + compteurs SQLite).

**Architecture:** Blueprint flask-smorest monté sur le serveur Flask existant (sous Dash), partage la connexion DuckDB read-only de `src/db.py`. Tokens stockés hashés (SHA-256) dans `users.sqlite`, CLI d'administration. Suivi async par worker thread (SQLite) + httpx fire-and-forget (Matomo).

**Tech Stack:** Flask, flask-smorest, marshmallow, DuckDB (existant), SQLite (stdlib), httpx (existant), Polars (existant), pytest.

**Spec de référence :** `docs/superpowers/specs/2026-05-13-api-privee-design.md`

---

## File Structure

**À créer :**

```
src/api/
├── __init__.py        # init_api(server)
├── routes.py          # endpoints /data, /schema, /health
├── schemas.py         # marshmallow request/response schemas
├── filters.py         # parsing & validation des filtres
├── auth.py            # @require_token
├── tracking.py        # worker SQLite + Matomo httpx
├── tokens_db.py       # CRUD api_tokens
└── tokens_cli.py      # python -m src.api.tokens_cli ...

tests/api/
├── __init__.py
├── conftest.py        # fixtures api_client, valid_token_header, revoked_token_header
├── test_tokens_db.py
├── test_tokens_cli.py
├── test_filters.py
├── test_auth.py
├── test_health.py
├── test_endpoints_schema.py
├── test_endpoints_data.py
└── test_tracking.py
```

**À modifier :**

- `pyproject.toml` : nouvelles deps + nouvelles variables `pytest-env`
- `.template.env` : nouvelles variables `MATOMO_*` et `USERS_DB_PATH`
- `src/app.py` : appel à `init_api(app.server)` après l'init Dash
- `CHANGELOG.md` : entrée pour la version qui livre l'API

---

## Task 1: Dépendances et infrastructure de test

**Files:**

- Modify: `pyproject.toml`
- Modify: `.template.env`
- Create: `src/api/__init__.py` (vide)
- Create: `tests/api/__init__.py` (vide)

- [ ] **Step 1: Ajouter `flask-smorest` aux dépendances**

Dans `pyproject.toml`, section `[project].dependencies`, ajouter après `"flask-cors>=6.0.2"` :

```toml
  "flask-smorest>=0.46.0",
  "marshmallow>=3.20.0",
```

- [ ] **Step 2: Ajouter les variables d'env pytest**

Dans `pyproject.toml`, section `[tool.pytest.ini_options].env`, ajouter à la liste :

```toml
  "USERS_DB_PATH=tests/users.test.sqlite",
  "MATOMO_TRACKING_ENABLED=false",
```

- [ ] **Step 3: Étendre `.template.env`**

Ajouter à la fin de `.template.env` :

```bash

# API privée
USERS_DB_PATH=./users.sqlite
MATOMO_URL=https://analytics.maudry.com/matomo.php
MATOMO_SITE_ID=14
MATOMO_TRACKING_ENABLED=true
```

- [ ] **Step 4: Installer les nouvelles dépendances**

Run: `source .venv/bin/activate && rtk pip install -e . --group=dev`

Expected: install OK, `pip show flask-smorest` shows version.

- [ ] **Step 5: Créer les packages vides**

Créer `src/api/__init__.py` avec contenu vide (juste un commentaire).

```python
# decp.info — API privée. init_api(server) sera ajouté Task 6.
```

Créer `tests/api/__init__.py` avec contenu vide.

- [ ] **Step 6: Vérifier que pytest tourne toujours**

Run: `rtk pre-commit run --all-files`
Expected: PASS (formatages éventuels appliqués).

Run: `rtk pytest tests/ -x --co -q 2>&1 | tail -20`
Expected: la collection se fait sans erreur (peu importe le nb de tests).

- [ ] **Step 7: Commit**

```bash
rtk git add pyproject.toml .template.env src/api/__init__.py tests/api/__init__.py
rtk git commit -m "API: dépendances et squelette de package (#78)"
```

---

## Task 2: Module `tokens_db` (SQLite CRUD)

**Files:**

- Create: `src/api/tokens_db.py`
- Create: `tests/api/conftest.py`
- Create: `tests/api/test_tokens_db.py`

- [ ] **Step 1: Écrire la fixture `temp_db` partagée**

Créer `tests/api/conftest.py` :

```python
import os
from pathlib import Path

import pytest


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Une SQLite éphémère pour les tests qui modifient la DB."""
    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    from src.api import tokens_db
    tokens_db.init_schema(db_path)
    return db_path
```

- [ ] **Step 2: Écrire les tests de `tokens_db`**

Créer `tests/api/test_tokens_db.py` :

```python
import sqlite3

from src.api import tokens_db


def test_init_schema_creates_table(temp_db):
    with sqlite3.connect(str(temp_db)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_tokens'"
        ).fetchall()
    assert rows == [("api_tokens",)]


def test_create_token_returns_plaintext_and_stores_hash(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "test-label")
    assert token.startswith("decpinfo_")
    assert len(token) == len("decpinfo_") + 64  # 32 octets hex = 64 chars
    assert token_id >= 1

    with sqlite3.connect(str(temp_db)) as conn:
        row = conn.execute(
            "SELECT token_hash, label, count_total FROM api_tokens WHERE id = ?",
            (token_id,),
        ).fetchone()
    assert row[1] == "test-label"
    assert row[2] == 0
    assert row[0] != token  # stocké en clair impossible
    assert len(row[0]) == 64  # sha256 hex


def test_get_token_by_plaintext_returns_row(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row is not None
    assert row["id"] == token_id
    assert row["label"] == "x"
    assert row["revoked_at"] is None


def test_get_token_unknown_returns_none(temp_db):
    assert tokens_db.get_token_by_plaintext(temp_db, "decpinfo_zzz") is None


def test_revoke_token_sets_revoked_at(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    tokens_db.revoke_token(temp_db, token_id)
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row["revoked_at"] is not None


def test_increment_usage_updates_counter_and_timestamp(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    tokens_db.increment_usage(temp_db, token_id)
    tokens_db.increment_usage(temp_db, token_id)
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row["count_total"] == 2
    assert row["last_used_at"] is not None


def test_list_tokens_returns_all(temp_db):
    tokens_db.create_token(temp_db, "a")
    tokens_db.create_token(temp_db, "b")
    rows = tokens_db.list_tokens(temp_db)
    assert [r["label"] for r in rows] == ["a", "b"]
```

- [ ] **Step 3: Lancer les tests et confirmer qu'ils échouent**

Run: `rtk pytest tests/api/test_tokens_db.py -v`
Expected: tous les tests FAIL avec `ImportError` ou `AttributeError` (module non écrit).

- [ ] **Step 4: Implémenter `tokens_db.py`**

Créer `src/api/tokens_db.py` :

```python
import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TOKEN_PREFIX = "decpinfo_"

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_tokens (
    id           INTEGER PRIMARY KEY,
    token_hash   TEXT NOT NULL UNIQUE,
    label        TEXT NOT NULL,
    user_id      INTEGER,
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    count_total  INTEGER NOT NULL DEFAULT 0,
    revoked_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def _connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_schema(db_path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def create_token(db_path, label: str, user_id: int | None = None) -> tuple[str, int]:
    token = TOKEN_PREFIX + secrets.token_hex(32)
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO api_tokens (token_hash, label, user_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (_hash(token), label, user_id, _utcnow_iso()),
        )
        conn.commit()
        return token, cur.lastrowid


def get_token_by_plaintext(db_path, token: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM api_tokens WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()
    return dict(row) if row else None


def revoke_token(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE api_tokens SET revoked_at = ? WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()


def increment_usage(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE api_tokens "
            "SET count_total = count_total + 1, last_used_at = ? "
            "WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()


def list_tokens(db_path) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM api_tokens ORDER BY id").fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Lancer les tests, confirmer qu'ils passent**

Run: `rtk pytest tests/api/test_tokens_db.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
rtk pre-commit run --files src/api/tokens_db.py tests/api/conftest.py tests/api/test_tokens_db.py
rtk git add src/api/tokens_db.py tests/api/conftest.py tests/api/test_tokens_db.py
rtk git commit -m "API: tokens_db SQLite CRUD (#78)"
```

---

## Task 3: CLI `tokens_cli` (create / list / revoke)

**Files:**

- Create: `src/api/tokens_cli.py`
- Create: `tests/api/test_tokens_cli.py`

- [ ] **Step 1: Écrire les tests CLI**

Créer `tests/api/test_tokens_cli.py` :

```python
import subprocess
import sys

from src.api import tokens_cli, tokens_db


def _run(args, env):
    return tokens_cli.main(args, env=env)


def test_create_prints_plaintext_token_once(temp_db, capsys):
    rc = _run(["create", "--label", "alice"], env={"USERS_DB_PATH": str(temp_db)})
    out = capsys.readouterr().out
    assert rc == 0
    assert "decpinfo_" in out
    tokens = tokens_db.list_tokens(temp_db)
    assert len(tokens) == 1
    assert tokens[0]["label"] == "alice"


def test_list_shows_tokens(temp_db, capsys):
    tokens_db.create_token(temp_db, "alice")
    tokens_db.create_token(temp_db, "bob")
    rc = _run(["list"], env={"USERS_DB_PATH": str(temp_db)})
    out = capsys.readouterr().out
    assert rc == 0
    assert "alice" in out
    assert "bob" in out


def test_revoke_sets_revoked_at(temp_db, capsys):
    _, token_id = tokens_db.create_token(temp_db, "alice")
    rc = _run(
        ["revoke", str(token_id)], env={"USERS_DB_PATH": str(temp_db)}
    )
    assert rc == 0
    tokens = tokens_db.list_tokens(temp_db)
    assert tokens[0]["revoked_at"] is not None
```

- [ ] **Step 2: Lancer les tests, confirmer FAIL**

Run: `rtk pytest tests/api/test_tokens_cli.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implémenter `tokens_cli.py`**

Créer `src/api/tokens_cli.py` :

```python
import argparse
import os
import sys

from src.api import tokens_db


def main(argv=None, env=None) -> int:
    env = env if env is not None else os.environ
    parser = argparse.ArgumentParser(prog="python -m src.api.tokens_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Créer un token API")
    p_create.add_argument("--label", required=True)
    p_create.add_argument("--user-id", type=int, default=None)

    sub.add_parser("list", help="Lister les tokens")

    p_revoke = sub.add_parser("revoke", help="Révoquer un token")
    p_revoke.add_argument("token_id", type=int)

    args = parser.parse_args(argv)
    db_path = env["USERS_DB_PATH"]
    tokens_db.init_schema(db_path)

    if args.cmd == "create":
        token, token_id = tokens_db.create_token(db_path, args.label, args.user_id)
        print(f"id={token_id} label={args.label}")
        print(f"token (à conserver, ne sera plus affiché) : {token}")
        return 0

    if args.cmd == "list":
        rows = tokens_db.list_tokens(db_path)
        if not rows:
            print("(aucun token)")
            return 0
        print(f"{'id':<4} {'label':<40} {'created_at':<26} {'last_used_at':<26} {'count':<7} revoked")
        for r in rows:
            print(
                f"{r['id']:<4} {r['label']:<40} {r['created_at']:<26} "
                f"{(r['last_used_at'] or '-'):<26} {r['count_total']:<7} "
                f"{r['revoked_at'] or ''}"
            )
        return 0

    if args.cmd == "revoke":
        tokens_db.revoke_token(db_path, args.token_id)
        print(f"token id={args.token_id} révoqué")
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: Lancer les tests, confirmer PASS**

Run: `rtk pytest tests/api/test_tokens_cli.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Tester manuellement le CLI**

```bash
USERS_DB_PATH=/tmp/cli.test.sqlite python -m src.api.tokens_cli create --label "test"
USERS_DB_PATH=/tmp/cli.test.sqlite python -m src.api.tokens_cli list
```

Expected: token affiché en sortie, puis listé.

- [ ] **Step 6: Commit**

```bash
rtk pre-commit run --files src/api/tokens_cli.py tests/api/test_tokens_cli.py
rtk git add src/api/tokens_cli.py tests/api/test_tokens_cli.py
rtk git commit -m "API: CLI tokens_cli (create/list/revoke) (#78)"
```

---

## Task 4: Module `filters` (parsing + génération SQL)

**Files:**

- Create: `src/api/filters.py`
- Create: `tests/api/test_filters.py`

- [ ] **Step 1: Écrire les tests de parsing & validation**

Créer `tests/api/test_filters.py` :

```python
import polars as pl
import pytest

from src.api.filters import FilterError, build_where


SCHEMA = pl.Schema(
    {
        "uid": pl.String,
        "objet": pl.String,
        "montant": pl.Float64,
        "annee": pl.Int64,
        "dateNotification": pl.Date,
    }
)


def test_no_filters_returns_true():
    where, params, order = build_where([], SCHEMA)
    assert where == "TRUE"
    assert params == []
    assert order is None


def test_exact_filter():
    where, params, _ = build_where([("uid__exact", "abc")], SCHEMA)
    assert where == '"uid" = ?'
    assert params == ["abc"]


def test_contains_filter_uses_like_wildcards():
    where, params, _ = build_where(
        [("objet__contains", "informatique")], SCHEMA
    )
    assert where == '"objet" LIKE ?'
    assert params == ["%informatique%"]


def test_notcontains_filter():
    where, params, _ = build_where(
        [("objet__notcontains", "x")], SCHEMA
    )
    assert where == '"objet" NOT LIKE ?'
    assert params == ["%x%"]


def test_comparison_operators_on_int():
    where, params, _ = build_where(
        [("annee__strictly_greater", "2023")], SCHEMA
    )
    assert where == '"annee" > ?'
    assert params == [2024 - 1]  # int coercion: 2023


def test_in_filter_splits_on_commas():
    where, params, _ = build_where(
        [("annee__in", "2022,2023,2024")], SCHEMA
    )
    assert where == '"annee" IN (?,?,?)'
    assert params == [2022, 2023, 2024]


def test_notin_filter():
    where, params, _ = build_where(
        [("annee__notin", "2020,2021")], SCHEMA
    )
    assert where == '"annee" NOT IN (?,?)'
    assert params == [2020, 2021]


def test_isnull_filter_ignores_value():
    where, params, _ = build_where(
        [("dateNotification__isnull", "anything")], SCHEMA
    )
    assert where == '"dateNotification" IS NULL'
    assert params == []


def test_isnotnull_filter():
    where, params, _ = build_where(
        [("dateNotification__isnotnull", "")], SCHEMA
    )
    assert where == '"dateNotification" IS NOT NULL'


def test_multiple_filters_joined_by_and():
    where, params, _ = build_where(
        [("uid__exact", "a"), ("annee__greater", "2020")], SCHEMA
    )
    assert where == '"uid" = ? AND "annee" >= ?'
    assert params == ["a", 2020]


def test_unknown_column_raises():
    with pytest.raises(FilterError) as exc:
        build_where([("foo__exact", "bar")], SCHEMA)
    assert "foo" in str(exc.value)
    assert exc.value.field == "foo__exact"


def test_unknown_operator_raises():
    with pytest.raises(FilterError) as exc:
        build_where([("uid__weird", "x")], SCHEMA)
    assert "weird" in str(exc.value)


def test_bad_int_value_raises():
    with pytest.raises(FilterError):
        build_where([("annee__exact", "notanint")], SCHEMA)


def test_bad_date_value_raises():
    with pytest.raises(FilterError):
        build_where([("dateNotification__exact", "notadate")], SCHEMA)


def test_date_iso_coercion():
    where, params, _ = build_where(
        [("dateNotification__greater", "2024-01-01")], SCHEMA
    )
    from datetime import date
    assert params == [date(2024, 1, 1)]


def test_reserved_params_are_ignored():
    where, params, order = build_where(
        [
            ("page", "2"),
            ("page_size", "100"),
            ("columns", "uid"),
            ("count", "false"),
            ("uid__exact", "z"),
        ],
        SCHEMA,
    )
    assert where == '"uid" = ?'
    assert params == ["z"]


def test_sort_returns_order_by():
    where, params, order = build_where(
        [("annee__sort", "desc"), ("uid__sort", "asc")], SCHEMA
    )
    assert where == "TRUE"
    assert order == '"annee" DESC, "uid" ASC'


def test_sort_invalid_direction_raises():
    with pytest.raises(FilterError):
        build_where([("uid__sort", "sideways")], SCHEMA)


def test_param_without_operator_raises():
    with pytest.raises(FilterError):
        build_where([("uidexact", "x")], SCHEMA)
```

- [ ] **Step 2: Lancer les tests, confirmer FAIL**

Run: `rtk pytest tests/api/test_filters.py -v`
Expected: FAIL avec `ImportError`.

- [ ] **Step 3: Implémenter `filters.py`**

Créer `src/api/filters.py` :

```python
from datetime import date, datetime

import polars as pl

OPERATORS = {
    "exact",
    "contains",
    "notcontains",
    "less",
    "greater",
    "strictly_less",
    "strictly_greater",
    "in",
    "notin",
    "isnull",
    "isnotnull",
    "sort",
}

RESERVED_PARAMS = {"page", "page_size", "columns", "count"}


class FilterError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


def _coerce(value: str, dtype: pl.DataType, key: str):
    if dtype == pl.String:
        return value
    if dtype.is_integer():
        try:
            return int(value)
        except ValueError:
            raise FilterError(
                f"Valeur entière attendue, reçu {value!r}", field=key
            )
    if dtype.is_float():
        try:
            return float(value)
        except ValueError:
            raise FilterError(
                f"Valeur décimale attendue, reçu {value!r}", field=key
            )
    if dtype == pl.Date:
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise FilterError(
                f"Date ISO 8601 attendue (YYYY-MM-DD), reçu {value!r}", field=key
            )
    if dtype == pl.Datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            raise FilterError(
                f"Datetime ISO 8601 attendu, reçu {value!r}", field=key
            )
    return value


def _split_key(key: str) -> tuple[str, str] | None:
    if "__" not in key:
        return None
    col, _, op = key.rpartition("__")
    if not col or not op:
        return None
    return col, op


def build_where(
    args: list[tuple[str, str]], schema: pl.Schema
) -> tuple[str, list, str | None]:
    """Parse query params into (where_sql, params, order_by_sql).

    args: list of (key, value) tuples preserving URL order (Werkzeug MultiDict
    preserves insertion order on `request.args.items(multi=True)`).
    """
    where_parts: list[str] = []
    params: list = []
    order_parts: list[str] = []

    for key, value in args:
        if key in RESERVED_PARAMS:
            continue

        parsed = _split_key(key)
        if not parsed:
            raise FilterError(f"Paramètre non reconnu : {key}", field=key)
        col, op = parsed

        if op not in OPERATORS:
            raise FilterError(f"Opérateur inconnu : __{op}", field=key)

        if col not in schema:
            raise FilterError(f"Colonne inconnue : {col!r}", field=key)

        if op == "sort":
            direction = value.lower()
            if direction not in ("asc", "desc"):
                raise FilterError(
                    f"Tri attendu 'asc' ou 'desc', reçu {value!r}", field=key
                )
            order_parts.append(f'"{col}" {direction.upper()}')
            continue

        if op in ("isnull", "isnotnull"):
            sql = "IS NULL" if op == "isnull" else "IS NOT NULL"
            where_parts.append(f'"{col}" {sql}')
            continue

        dtype = schema[col]

        if op in ("in", "notin"):
            values = [_coerce(v.strip(), dtype, key) for v in value.split(",")]
            placeholders = ",".join(["?"] * len(values))
            sql_op = "IN" if op == "in" else "NOT IN"
            where_parts.append(f'"{col}" {sql_op} ({placeholders})')
            params.extend(values)
            continue

        v = _coerce(value, dtype, key)

        op_sql = {
            "exact": "=",
            "less": "<=",
            "greater": ">=",
            "strictly_less": "<",
            "strictly_greater": ">",
        }
        if op in op_sql:
            where_parts.append(f'"{col}" {op_sql[op]} ?')
            params.append(v)
        elif op == "contains":
            where_parts.append(f'"{col}" LIKE ?')
            params.append(f"%{v}%")
        elif op == "notcontains":
            where_parts.append(f'"{col}" NOT LIKE ?')
            params.append(f"%{v}%")

    where_sql = " AND ".join(where_parts) if where_parts else "TRUE"
    order_sql = ", ".join(order_parts) if order_parts else None
    return where_sql, params, order_sql
```

- [ ] **Step 4: Lancer les tests, confirmer PASS**

Run: `rtk pytest tests/api/test_filters.py -v`
Expected: PASS (~20 tests).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files src/api/filters.py tests/api/test_filters.py
rtk git add src/api/filters.py tests/api/test_filters.py
rtk git commit -m "API: parser de filtres et génération SQL paramétré (#78)"
```

---

## Task 5: Décorateur `@require_token`

**Files:**

- Create: `src/api/auth.py`
- Create: `tests/api/test_auth.py`

- [ ] **Step 1: Écrire les tests d'auth**

Créer `tests/api/test_auth.py` :

```python
from flask import Flask, g, jsonify

from src.api import tokens_db
from src.api.auth import require_token


def _make_app():
    app = Flask(__name__)

    @app.route("/protected")
    @require_token
    def protected():
        return jsonify({"token_id": g.token_id})

    return app


def test_missing_header_returns_401(temp_db):
    app = _make_app()
    resp = app.test_client().get("/protected")
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "missing_token"


def test_bearer_without_value_returns_401(temp_db):
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": "Bearer "}
    )
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "missing_token"


def test_invalid_token_returns_401(temp_db):
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": "Bearer decpinfo_unknown"}
    )
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "invalid_token"


def test_revoked_token_returns_401(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    tokens_db.revoke_token(temp_db, token_id)
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "revoked_token"


def test_valid_token_sets_g_and_calls_view(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["token_id"] == token_id
```

- [ ] **Step 2: Lancer les tests, confirmer FAIL**

Run: `rtk pytest tests/api/test_auth.py -v`
Expected: FAIL avec `ImportError` sur `src.api.auth`.

- [ ] **Step 3: Implémenter `auth.py`**

Créer `src/api/auth.py` :

```python
import os
from functools import wraps

from flask import abort, g, jsonify, make_response, request

from src.api import tokens_db


def _abort_401(message: str):
    resp = make_response(jsonify({"message": message}), 401)
    abort(resp)


def require_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            _abort_401("missing_token")
        token = header[len("Bearer ") :].strip()
        if not token:
            _abort_401("missing_token")
        db_path = os.environ["USERS_DB_PATH"]
        row = tokens_db.get_token_by_plaintext(db_path, token)
        if row is None:
            _abort_401("invalid_token")
        if row["revoked_at"] is not None:
            _abort_401("revoked_token")
        g.token_id = row["id"]
        return fn(*args, **kwargs)

    return wrapper
```

- [ ] **Step 4: Lancer les tests, confirmer PASS**

Run: `rtk pytest tests/api/test_auth.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files src/api/auth.py tests/api/test_auth.py
rtk git add src/api/auth.py tests/api/test_auth.py
rtk git commit -m "API: décorateur @require_token (#78)"
```

---

## Task 6: Squelette de blueprint + `/health`

**Files:**

- Modify: `src/api/__init__.py`
- Create: `src/api/routes.py`
- Create: `tests/api/test_health.py`

- [ ] **Step 1: Écrire le test `/health`**

Créer `tests/api/test_health.py` :

```python
from flask import Flask

from src.api import init_api


def _make_app():
    app = Flask(__name__)
    init_api(app)
    return app


def test_health_returns_ok_without_auth():
    app = _make_app()
    resp = app.test_client().get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
```

- [ ] **Step 2: Lancer le test, confirmer FAIL**

Run: `rtk pytest tests/api/test_health.py -v`
Expected: FAIL (`init_api` n'existe pas).

- [ ] **Step 3: Implémenter `__init__.py` avec blueprint flask-smorest**

Remplacer le contenu de `src/api/__init__.py` :

```python
from flask_smorest import Api, Blueprint

from src.api import routes


def init_api(server) -> None:
    """Enregistre le blueprint d'API privée sur le serveur Flask."""
    server.config.setdefault("API_TITLE", "decp.info API")
    server.config.setdefault("API_VERSION", "v1")
    server.config.setdefault("OPENAPI_VERSION", "3.0.3")
    server.config.setdefault("OPENAPI_URL_PREFIX", "/api/v1")
    server.config.setdefault("OPENAPI_JSON_PATH", "openapi.json")
    server.config.setdefault("OPENAPI_SWAGGER_UI_PATH", "swagger")
    server.config.setdefault(
        "OPENAPI_SWAGGER_UI_URL",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    )

    api = Api(server)
    api.register_blueprint(routes.bp)
```

- [ ] **Step 4: Implémenter `routes.py` avec uniquement `/health`**

Créer `src/api/routes.py` :

```python
from flask_smorest import Blueprint

bp = Blueprint(
    "api_v1",
    "api_v1",
    url_prefix="/api/v1",
    description="API privée decp.info — accès tabulaire aux marchés publics.",
)


@bp.route("/health")
def health():
    """Sonde de santé, sans authentification."""
    return {"status": "ok"}
```

- [ ] **Step 5: Lancer le test, confirmer PASS**

Run: `rtk pytest tests/api/test_health.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
rtk pre-commit run --files src/api/__init__.py src/api/routes.py tests/api/test_health.py
rtk git add src/api/__init__.py src/api/routes.py tests/api/test_health.py
rtk git commit -m "API: blueprint flask-smorest + endpoint /health (#78)"
```

---

## Task 7: Brancher l'API dans l'app Dash

**Files:**

- Modify: `src/app.py`

- [ ] **Step 1: Écrire un test d'intégration**

Ajouter à la fin de `tests/api/test_health.py` :

```python
def test_health_via_real_app():
    """Vérifie que init_api est bien branché dans src.app."""
    from src.app import app as dash_app

    resp = dash_app.server.test_client().get("/api/v1/health")
    assert resp.status_code == 200
```

- [ ] **Step 2: Lancer le test, confirmer FAIL**

Run: `rtk pytest tests/api/test_health.py::test_health_via_real_app -v`
Expected: FAIL (404 — l'API n'est pas branchée).

- [ ] **Step 3: Brancher `init_api` dans `src/app.py`**

Dans `src/app.py`, après la ligne `cache.init_app(...)` (vers la ligne 52, juste avant la définition de `@app.server.route("/robots.txt")`), ajouter :

```python
from src.api import init_api

init_api(app.server)
```

L'import en haut du fichier serait plus propre mais romprait l'ordre des dépendances (l'API a besoin que `src.db.conn` soit prêt). Le faire ici garantit l'ordre.

- [ ] **Step 4: Lancer les tests, confirmer PASS**

Run: `rtk pytest tests/api/test_health.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Vérifier que l'app Dash démarre toujours**

Run: `rtk pytest tests/ -x --co -q 2>&1 | tail -5`
Expected: collection sans erreur.

- [ ] **Step 6: Commit**

```bash
rtk pre-commit run --files src/app.py tests/api/test_health.py
rtk git add src/app.py tests/api/test_health.py
rtk git commit -m "API: branchement init_api dans l'app Dash (#78)"
```

---

## Task 8: Endpoint `/schema`

**Files:**

- Modify: `src/api/routes.py`
- Create: `tests/api/test_endpoints_schema.py`

- [ ] **Step 1: Étendre `tests/api/conftest.py` avec une fixture token "vivant"**

Ajouter à `tests/api/conftest.py` (à la fin) :

```python
@pytest.fixture
def api_client(monkeypatch, tmp_path):
    """Client Flask test avec USERS_DB_PATH éphémère et blueprint API monté."""
    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    from flask import Flask

    from src.api import init_api, tokens_db

    tokens_db.init_schema(db_path)
    server = Flask(__name__)
    init_api(server)
    return server.test_client(), db_path


@pytest.fixture
def valid_token_header(api_client):
    from src.api import tokens_db

    _, db_path = api_client
    token, _ = tokens_db.create_token(db_path, "test-token")
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 2: Écrire les tests de `/schema`**

Créer `tests/api/test_endpoints_schema.py` :

```python
def test_schema_without_token_returns_401(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/schema")
    assert resp.status_code == 401


def test_schema_returns_columns(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/schema", headers=valid_token_header)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "columns" in data
    assert isinstance(data["columns"], list)
    assert len(data["columns"]) > 0
    first = data["columns"][0]
    assert set(first.keys()) >= {"name", "type"}
    # uid doit être présent dans le schéma DECP de test
    names = [c["name"] for c in data["columns"]]
    assert "uid" in names
```

- [ ] **Step 3: Lancer les tests, confirmer FAIL**

Run: `rtk pytest tests/api/test_endpoints_schema.py -v`
Expected: FAIL (route /schema absente → 404).

- [ ] **Step 4: Implémenter `/schema` dans `routes.py`**

Ajouter à la fin de `src/api/routes.py` :

```python
from src.api.auth import require_token
from src.db import schema as duckdb_schema


@bp.route("/schema")
@require_token
def schema():
    """Liste des colonnes disponibles dans le dataset DECP."""
    cols = [
        {"name": name, "type": str(dtype)}
        for name, dtype in duckdb_schema.items()
    ]
    return {"columns": cols}
```

- [ ] **Step 5: Lancer les tests, confirmer PASS**

Run: `rtk pytest tests/api/test_endpoints_schema.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
rtk pre-commit run --files src/api/routes.py tests/api/conftest.py tests/api/test_endpoints_schema.py
rtk git add src/api/routes.py tests/api/conftest.py tests/api/test_endpoints_schema.py
rtk git commit -m "API: endpoint /schema (#78)"
```

---

## Task 9: Endpoint `/data` — pagination de base sans filtres

**Files:**

- Modify: `src/api/routes.py`
- Create: `tests/api/test_endpoints_data.py`

- [ ] **Step 1: Écrire les premiers tests `/data`**

Créer `tests/api/test_endpoints_data.py` :

```python
def test_data_without_token_returns_401(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/data")
    assert resp.status_code == 401


def test_data_default_pagination(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) >= {"data", "meta", "links"}
    assert isinstance(body["data"], list)
    assert len(body["data"]) <= 50  # default page_size
    assert body["meta"]["page"] == 1
    assert body["meta"]["page_size"] == 50
    assert "total" in body["meta"]


def test_data_count_false_omits_total(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?count=false", headers=valid_token_header
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "total" not in body["meta"]


def test_data_page_size_max_enforced(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?page_size=5000", headers=valid_token_header
    )
    assert resp.status_code == 400


def test_data_page_size_below_min_rejected(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?page_size=0", headers=valid_token_header
    )
    assert resp.status_code == 400


def test_data_pagination_links(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?page=1&page_size=1", headers=valid_token_header
    )
    body = resp.get_json()
    assert body["links"]["prev"] is None
    if body["meta"]["total"] > 1:
        assert body["links"]["next"] is not None
        assert "page=2" in body["links"]["next"]
```

- [ ] **Step 2: Lancer les tests, confirmer FAIL**

Run: `rtk pytest tests/api/test_endpoints_data.py -v`
Expected: FAIL (404 sur /data).

- [ ] **Step 3: Ajouter la route `/data` dans `routes.py`**

Ajouter à `src/api/routes.py` (après `/schema`) :

```python
from flask import request
from flask_smorest import abort

from src.api.filters import FilterError, build_where
from src.db import count_marches, query_marches, schema as duckdb_schema


MAX_PAGE_SIZE = 1000


def _parse_pagination():
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "50"))
    except ValueError:
        abort(400, message="page et page_size doivent être des entiers")
    if page < 1:
        abort(400, message="page doit être >= 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        abort(
            400,
            message=f"page_size doit être dans [1, {MAX_PAGE_SIZE}]",
        )
    return page, page_size


def _parse_columns():
    raw = request.args.get("columns")
    if not raw:
        return None
    cols = [c.strip() for c in raw.split(",") if c.strip()]
    unknown = [c for c in cols if c not in duckdb_schema]
    if unknown:
        abort(400, message=f"Colonnes inconnues : {unknown}")
    return cols


def _build_links(page, page_size, total):
    base = request.path
    qs = request.args.to_dict(flat=False)
    qs.pop("page", None)

    def url_for(p):
        from urllib.parse import urlencode
        params = [(k, v) for k, vs in qs.items() for v in vs]
        params.append(("page", str(p)))
        return f"{base}?{urlencode(params)}"

    prev_url = url_for(page - 1) if page > 1 else None
    next_url = None
    if total is None or page * page_size < total:
        next_url = url_for(page + 1)
    return {"prev": prev_url, "next": next_url}


@bp.route("/data")
@require_token
def data():
    """Endpoint tabulaire : filtres dynamiques sur les colonnes DECP."""
    page, page_size = _parse_pagination()
    columns = _parse_columns()
    count = request.args.get("count", "true").lower() != "false"

    try:
        where_sql, params, order_sql = build_where(
            list(request.args.items(multi=True)), duckdb_schema
        )
    except FilterError as e:
        abort(400, message=str(e), errors={"field": e.field})

    df = query_marches(
        where_sql=where_sql,
        params=params,
        columns=columns,
        order_by=order_sql,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    # JSON ne sérialise pas date/datetime nativement → cast en string ISO
    import polars as pl
    import polars.selectors as cs

    df_ready = df.with_columns(cs.temporal().cast(pl.String))

    total = count_marches(where_sql, params) if count else None
    meta = {"page": page, "page_size": page_size}
    if total is not None:
        meta["total"] = total

    return {
        "data": df_ready.to_dicts(),
        "meta": meta,
        "links": _build_links(page, page_size, total),
    }
```

- [ ] **Step 4: Lancer les tests, confirmer PASS**

Run: `rtk pytest tests/api/test_endpoints_data.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files src/api/routes.py tests/api/test_endpoints_data.py
rtk git add src/api/routes.py tests/api/test_endpoints_data.py
rtk git commit -m "API: endpoint /data avec pagination et filtres (#78)"
```

---

## Task 10: Endpoint `/data` — filtres, tri, columns (intégration)

**Files:**

- Modify: `tests/api/test_endpoints_data.py`

- [ ] **Step 1: Ajouter les tests d'intégration filtres + tri + columns**

Ajouter à `tests/api/test_endpoints_data.py` :

```python
def test_data_filter_exact_string(api_client, valid_token_header):
    client, _ = api_client
    # On choisit une valeur qui existe dans test.parquet : récupère via la 1re ligne
    base = client.get("/api/v1/data?page_size=1", headers=valid_token_header).get_json()
    assert base["data"], "test.parquet vide ?"
    uid = base["data"][0]["uid"]

    resp = client.get(
        f"/api/v1/data?uid__exact={uid}", headers=valid_token_header
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert all(row["uid"] == uid for row in body["data"])


def test_data_unknown_column_filter_returns_400(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?colonne_inexistante__exact=x",
        headers=valid_token_header,
    )
    assert resp.status_code == 400


def test_data_columns_selection(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?columns=uid,objet&page_size=3",
        headers=valid_token_header,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    for row in body["data"]:
        assert set(row.keys()) == {"uid", "objet"}


def test_data_columns_unknown_returns_400(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?columns=uid,foobar",
        headers=valid_token_header,
    )
    assert resp.status_code == 400


def test_data_sort_desc(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get(
        "/api/v1/data?dateNotification__sort=desc&page_size=5",
        headers=valid_token_header,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    dates = [row["dateNotification"] for row in body["data"] if row.get("dateNotification")]
    assert dates == sorted(dates, reverse=True)
```

- [ ] **Step 2: Lancer les tests**

Run: `rtk pytest tests/api/test_endpoints_data.py -v`
Expected: PASS (5 nouveaux tests, 11 au total). Si des FAIL surgissent, c'est généralement lié à l'absence d'une colonne dans `tests/test.parquet` — adapter la valeur de test à ce qui existe.

- [ ] **Step 3: Commit**

```bash
rtk git add tests/api/test_endpoints_data.py
rtk git commit -m "API: tests d'intégration filtres/tri/columns (#78)"
```

---

## Task 11: Suivi de consommation — compteur SQLite asynchrone

**Files:**

- Create: `src/api/tracking.py`
- Modify: `src/api/routes.py`
- Create: `tests/api/test_tracking.py`

- [ ] **Step 1: Écrire le test du worker compteur**

Créer `tests/api/test_tracking.py` :

```python
import time

from src.api import tokens_db, tracking


def test_counter_worker_increments_count(temp_db):
    _, token_id = tokens_db.create_token(temp_db, "x")

    tracking.start_worker(str(temp_db))
    try:
        tracking.enqueue_counter_update(token_id)
        tracking.enqueue_counter_update(token_id)
        # Laisser le worker drainer la queue
        tracking.flush(timeout=2.0)
    finally:
        tracking.stop_worker()

    rows = tokens_db.list_tokens(temp_db)
    assert rows[0]["count_total"] == 2
    assert rows[0]["last_used_at"] is not None


def test_after_request_hook_increments_counter_async(
    api_client, valid_token_header
):
    client, db_path = api_client
    # Récupérer le token_id du token créé par la fixture
    from src.api import tokens_db, tracking

    rows = tokens_db.list_tokens(db_path)
    token_id = rows[0]["id"]

    # Faire une requête (qui doit déclencher l'incrément)
    client.get("/api/v1/health")  # pas authentifiée → ne compte pas
    client.get("/api/v1/schema", headers=valid_token_header)

    tracking.flush(timeout=2.0)

    rows = tokens_db.list_tokens(db_path)
    assert rows[0]["count_total"] == 1
```

- [ ] **Step 2: Lancer les tests, confirmer FAIL**

Run: `rtk pytest tests/api/test_tracking.py -v`
Expected: FAIL (`src.api.tracking` n'existe pas).

- [ ] **Step 3: Implémenter `tracking.py` (compteur seulement, Matomo arrivera Task 12)**

Créer `src/api/tracking.py` :

```python
import queue
import threading
from typing import Optional

from src.api import tokens_db
from src.utils import logger

_STOP_SENTINEL = object()
_queue: Optional[queue.Queue] = None
_worker_thread: Optional[threading.Thread] = None
_db_path: Optional[str] = None


def _worker_loop(q: queue.Queue, db_path: str) -> None:
    while True:
        item = q.get()
        try:
            if item is _STOP_SENTINEL:
                return
            kind, payload = item
            if kind == "counter":
                token_id = payload
                try:
                    tokens_db.increment_usage(db_path, token_id)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "tracking: échec increment_usage token_id=%s",
                        token_id,
                        exc_info=True,
                    )
        finally:
            q.task_done()


def start_worker(db_path: str) -> None:
    global _queue, _worker_thread, _db_path
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _db_path = db_path
    _queue = queue.Queue()
    _worker_thread = threading.Thread(
        target=_worker_loop, args=(_queue, db_path), daemon=True
    )
    _worker_thread.start()


def stop_worker() -> None:
    global _worker_thread, _queue
    if _worker_thread is None:
        return
    _queue.put(_STOP_SENTINEL)
    _worker_thread.join(timeout=2.0)
    _worker_thread = None
    _queue = None


def enqueue_counter_update(token_id: int) -> None:
    if _queue is None:
        return  # tracking désactivé (tests par ex.)
    _queue.put(("counter", token_id))


def flush(timeout: float = 2.0) -> None:
    """Attend que la queue soit drainée. Utile en test."""
    if _queue is None:
        return
    _queue.join()
```

- [ ] **Step 4: Brancher le hook `after_request` dans `routes.py`**

Ajouter à `src/api/routes.py` (avant la définition de `bp.route("/data")`, mais après l'init de `bp`) :

```python
from flask import g

from src.api import tracking


@bp.after_request
def _track_consumption(response):
    token_id = getattr(g, "token_id", None)
    if token_id is not None:
        tracking.enqueue_counter_update(token_id)
    return response
```

- [ ] **Step 5: Démarrer le worker au moment du `init_api`**

Modifier `src/api/__init__.py` pour ajouter dans `init_api` (après `api.register_blueprint(routes.bp)`) :

```python
    import os

    from src.api import tracking

    tracking.start_worker(os.environ["USERS_DB_PATH"])
```

- [ ] **Step 6: Adapter la fixture `api_client` pour démarrer/arrêter le worker proprement**

Modifier `tests/api/conftest.py`, fixture `api_client` :

```python
@pytest.fixture
def api_client(monkeypatch, tmp_path):
    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    from flask import Flask

    from src.api import init_api, tokens_db, tracking

    tokens_db.init_schema(db_path)
    server = Flask(__name__)
    init_api(server)
    yield server.test_client(), db_path
    tracking.stop_worker()
```

- [ ] **Step 7: Lancer les tests, confirmer PASS**

Run: `rtk pytest tests/api/test_tracking.py tests/api/test_endpoints_schema.py tests/api/test_endpoints_data.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
rtk pre-commit run --files src/api/tracking.py src/api/routes.py src/api/__init__.py tests/api/conftest.py tests/api/test_tracking.py
rtk git add src/api/tracking.py src/api/routes.py src/api/__init__.py tests/api/conftest.py tests/api/test_tracking.py
rtk git commit -m "API: compteur de consommation SQLite asynchrone (#78)"
```

---

## Task 12: Suivi de consommation — événements Matomo (fire-and-forget)

**Files:**

- Modify: `src/api/tracking.py`
- Modify: `src/api/routes.py`
- Modify: `tests/api/test_tracking.py`

- [ ] **Step 1: Écrire les tests Matomo (avec mock httpx)**

Ajouter à `tests/api/test_tracking.py` :

```python
def test_matomo_disabled_skips_call(monkeypatch, api_client, valid_token_header):
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "false")
    client, _ = api_client
    called = []

    from src.api import tracking

    monkeypatch.setattr(
        tracking,
        "_post_matomo",
        lambda **kw: called.append(kw),
    )
    client.get("/api/v1/health")
    tracking.flush(timeout=2.0)
    assert called == []


def test_matomo_enabled_posts_event(
    monkeypatch, api_client, valid_token_header
):
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
    captured = []

    from src.api import tracking

    monkeypatch.setattr(
        tracking,
        "_post_matomo",
        lambda **kw: captured.append(kw),
    )

    client, _ = api_client
    client.get("/api/v1/schema", headers=valid_token_header)
    tracking.flush(timeout=2.0)

    assert len(captured) == 1
    call = captured[0]
    assert call["params"]["idsite"] == "42"
    assert call["params"]["rec"] == "1"
    assert "token-" in call["params"]["uid"]
    assert call["params"]["dimension2"] == "200"
```

- [ ] **Step 2: Lancer les tests, confirmer FAIL**

Run: `rtk pytest tests/api/test_tracking.py -v -k matomo`
Expected: FAIL (`_post_matomo` n'existe pas).

- [ ] **Step 3: Étendre `tracking.py` avec l'envoi Matomo**

Ajouter à `src/api/tracking.py` (en haut, après les imports existants) :

```python
import os
import httpx
```

Étendre `_worker_loop` pour gérer un nouveau type `"matomo"` :

```python
def _worker_loop(q: queue.Queue, db_path: str) -> None:
    while True:
        item = q.get()
        try:
            if item is _STOP_SENTINEL:
                return
            kind, payload = item
            if kind == "counter":
                token_id = payload
                try:
                    tokens_db.increment_usage(db_path, token_id)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "tracking: échec increment_usage token_id=%s",
                        token_id,
                        exc_info=True,
                    )
            elif kind == "matomo":
                try:
                    _post_matomo(**payload)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "tracking: échec envoi Matomo", exc_info=True
                    )
        finally:
            q.task_done()


def _post_matomo(url: str, params: dict) -> None:
    """POST fire-and-forget vers la Tracking API Matomo. Mockable en test."""
    httpx.post(url, data=params, timeout=5.0)


def enqueue_matomo_event(
    token_id: int,
    path: str,
    query_string: str,
    status_code: int,
    user_agent: str,
) -> None:
    if _queue is None:
        return
    if os.getenv("MATOMO_TRACKING_ENABLED", "false").lower() != "true":
        return
    url = os.getenv("MATOMO_URL")
    site_id = os.getenv("MATOMO_SITE_ID")
    if not url or not site_id:
        return
    full_url = f"https://decp.info{path}"
    if query_string:
        full_url += f"?{query_string}"
    params = {
        "idsite": site_id,
        "rec": "1",
        "url": full_url,
        "action_name": f"API {path}",
        "uid": f"token-{token_id}",
        "dimension1": str(token_id),
        "dimension2": str(status_code),
        "ua": user_agent,
    }
    _queue.put(("matomo", {"url": url, "params": params}))
```

- [ ] **Step 4: Compléter le hook `after_request` pour envoyer aussi à Matomo**

Modifier `src/api/routes.py`, la fonction `_track_consumption` :

```python
@bp.after_request
def _track_consumption(response):
    token_id = getattr(g, "token_id", None)
    if token_id is not None:
        tracking.enqueue_counter_update(token_id)
        tracking.enqueue_matomo_event(
            token_id=token_id,
            path=request.path,
            query_string=request.query_string.decode("utf-8", errors="replace"),
            status_code=response.status_code,
            user_agent=request.headers.get("User-Agent", ""),
        )
    return response
```

- [ ] **Step 5: Lancer les tests, confirmer PASS**

Run: `rtk pytest tests/api/test_tracking.py -v`
Expected: PASS (tous tests dont les 2 nouveaux Matomo).

- [ ] **Step 6: Commit**

```bash
rtk pre-commit run --files src/api/tracking.py src/api/routes.py tests/api/test_tracking.py
rtk git add src/api/tracking.py src/api/routes.py tests/api/test_tracking.py
rtk git commit -m "API: envoi Matomo fire-and-forget en async (#78)"
```

---

## Task 13: Documentation OpenAPI explicite + Changelog

**Files:**

- Modify: `src/api/routes.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Ajouter docstrings et statuts OpenAPI sur les routes**

Modifier les routes dans `src/api/routes.py` pour enrichir Swagger. Exemple sur `/data` (ajouter en docstring) :

```python
@bp.route("/data")
@require_token
def data():
    """Récupère des marchés publics filtrés.

    Filtres en query string sous la forme `<colonne>__<opérateur>=<valeur>`.

    Opérateurs : exact, contains, notcontains, less, greater,
    strictly_less, strictly_greater, in, notin, isnull, isnotnull, sort.

    Paramètres réservés : page (défaut 1), page_size (défaut 50, max 1000),
    columns (csv), count (true|false ; mettre false pour économiser le COUNT(*)).
    """
    ...  # corps inchangé
```

Faire de même pour `/schema` et `/health` (une ligne suffit).

- [ ] **Step 2: Vérifier manuellement la doc Swagger**

Run: `rtk python run.py &` puis ouvrir <http://127.0.0.1:8050/api/v1/swagger> dans un navigateur.
Expected: Swagger UI affiche les 3 endpoints, doc lisible.

Arrêter le serveur (Ctrl-C ou `kill %1`).

- [ ] **Step 3: Ajouter l'entrée Changelog**

Lire `CHANGELOG.md` pour comprendre le format puis ajouter en haut, sous la section "Unreleased" (ou créer cette section) :

```markdown
## [Unreleased]

### Ajouté

- API privée tabulaire `/api/v1/data` (filtres dynamiques, pagination, tri).
- Endpoint `/api/v1/schema` (description du dataset).
- Endpoint `/api/v1/health` (sonde monitoring).
- Documentation interactive Swagger UI à `/api/v1/swagger`.
- CLI d'administration des tokens : `python -m src.api.tokens_cli` (create, list, revoke).
- Suivi de consommation : compteurs SQLite (`api_tokens.count_total`, `last_used_at`) + événements Matomo async.

### Configuration

- Nouvelles variables d'environnement : `USERS_DB_PATH`, `MATOMO_URL`, `MATOMO_SITE_ID`, `MATOMO_TRACKING_ENABLED`.
- Création de 2 Custom Dimensions côté Matomo : `dimension1=token_id`, `dimension2=http_status`.
```

- [ ] **Step 4: Lancer toute la suite de tests**

Run: `rtk pytest tests/api/ -v`
Expected: tous les tests PASS.

Run: `rtk pytest tests/ -x` (suite complète, y compris l'app Dash)
Expected: pas de régression (la suite Dash existante peut être longue, c'est normal).

- [ ] **Step 5: Commit**

```bash
rtk pre-commit run --files src/api/routes.py CHANGELOG.md
rtk git add src/api/routes.py CHANGELOG.md
rtk git commit -m "API: documentation OpenAPI et CHANGELOG (#78)"
```

---

## Task 14: Mention de l'API sur la page À propos

**Files:**

- Modify: `src/pages/a_propos.py` (vérifier le nom exact)

- [ ] **Step 1: Repérer la page À propos**

Run: `rtk ls src/pages/`
Identifier le fichier correspondant à `/a-propos` (probablement `a_propos.py` ou `apropos.py`).

- [ ] **Step 2: Ajouter une section "API"**

Dans le layout de la page, ajouter une section markdown ou un bloc HTML :

```python
dcc.Markdown("""
### API privée

Une API HTTP est disponible pour accéder aux mêmes données par programme.
Documentation interactive : [Swagger UI](/api/v1/swagger).

L'accès se fait sur token. Pour en obtenir un, contactez
[colin@maudry.com](mailto:colin@maudry.com).
"""),
```

- [ ] **Step 3: Vérifier visuellement**

Run: `rtk python run.py &`
Ouvrir <http://127.0.0.1:8050/a-propos> et confirmer que la section apparaît.
Arrêter le serveur.

- [ ] **Step 4: Commit**

```bash
rtk pre-commit run --files src/pages/a_propos.py
rtk git add src/pages/a_propos.py
rtk git commit -m "API: mention sur la page À propos (#78)"
```

---

## Notes pour l'exécution

- **Couverture spec** : chaque section du spec a une ou plusieurs tâches associées (deps → Task 1, tokens_db → Task 2, CLI → Task 3, filters → Task 4, auth → Task 5, blueprint+health → Task 6, branchement → Task 7, schema → Task 8, data → Tasks 9-10, tracking SQLite → Task 11, Matomo → Task 12, OpenAPI+changelog → Task 13).
- **`tests/test.parquet`** : peut ne pas contenir toutes les colonnes citées dans les tests (cf. CLAUDE.md). Si un test échoue parce qu'une colonne n'existe pas dans la fixture, l'adapter à une colonne effectivement présente.
- **`src/db.py:127`** ouvre une connexion DuckDB read-only au moment de l'import. Cela peut être lent au premier lancement de la suite de tests (rebuild de la base). C'est normal.
- **Worker tracking** : démarré dans `init_api`, démon. Pas de cleanup nécessaire en prod (mourra avec le process). En test, la fixture `api_client` appelle `stop_worker()` pour propreté.
- **Git flow** : on est déjà sur `feature/78_api`. Tous les commits y vont. Pas de `git push` (cf. CLAUDE.md).
