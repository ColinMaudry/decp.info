# MCP OAuth 2.1 (scope B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire de colibre son propre serveur d'autorisation OAuth 2.1 conforme MCP pour que Claude.ai / Claude Desktop / ChatGPT se connectent au connecteur MCP, en conservant le chemin jeton statique (clients CLI).

**Architecture:** authlib (déjà en dépendance) fournit les grants OAuth 2.1 (authorization_code+PKCE, refresh, DCR) ; le stockage est en SQLite brut (pattern `src/api/tokens_db.py`). colibre est à la fois serveur d'autorisation et resource server sur le même Flask ; l'étape de consentement réutilise la session flask_login. Les tokens d'accès sont opaques, liés en audience (`resource`, RFC 8707), validés par lookup haché dans le garde `/_mcp` unifié.

**Tech Stack:** Python, Flask, authlib 1.7.2, sqlite3, flask_login, pytest.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `from src.mcp.oauth import store`).
- Stockage : `sqlite3` brut, pas de SQLAlchemy. Suivre le pattern `src/api/tokens_db.py` (`_connect(db_path)` contextmanager, `init_schema(db_path)`, hachage SHA-256).
- Chemin de la base : variable d'env `USERS_DB_PATH` (mêmes fichier/DB que `api_tokens`, `subscriptions`, `users`).
- Base URL / issuer : `APP_BASE_URL` (sans slash final). HTTPS obligatoire hors dev ; localhost toléré en dev.
- Audience canonique du serveur MCP : `f"{APP_BASE_URL}/_mcp"`.
- Durées de vie : access token **3600 s (1 h)**, refresh token **5184000 s (60 j)**. Rotation du refresh à chaque usage.
- Scopes annoncés : `["mcp", "offline_access"]`.
- Activation : tout le câblage OAuth vit dans le bloc `if _mcp_enabled:` de `src/app.py` (piloté par `DASH_MCP_ENABLED=true`).
- `pre-commit` doit être exécuté avant chaque `git add` (ruff formate). Lancer les tests avec `uv run pytest`.
- Tests d'un module ciblés sur leur propre fichier ; ne pas lancer toute la suite avant la dernière tâche.

---

## File Structure

- Create `src/mcp/oauth/__init__.py` — package vide.
- Create `src/mcp/oauth/store.py` — CRUD sqlite : clients (DCR), codes d'autorisation, tokens.
- Create `src/mcp/oauth/metadata.py` — documents JSON RFC 9728 (PRM) + RFC 8414 (AS).
- Create `src/mcp/oauth/consent.py` — gate abonnement + rendu HTML des écrans consentement / abonnement requis.
- Create `src/mcp/oauth/server.py` — configuration authlib (grants, `query_client`, `save_token`, DCR).
- Create `src/mcp/oauth/routes.py` — blueprint Flask (well-known, /oauth/register, /authorize, /token, /revoke) + `init_oauth(app)`.
- Create `src/mcp/usage.py` — journal `mcp_usage` (record, count_since, purge).
- Modify `src/migrations.py` — 4 migrations (oauth_clients, oauth_codes, oauth_tokens, mcp_usage).
- Modify `src/mcp/auth.py` — garde `/_mcp` unifié (statique + OAuth), header `resource_metadata`, journal usage.
- Modify `src/pages/compte/mcp.py` — instructions Claude.ai / ChatGPT.
- Modify `src/app.py` — `init_oauth`, exemption CSRF, init schémas, purge au démarrage.
- Test files under `tests/mcp/`.

---

### Task 1: OAuth store — schéma & clients (DCR)

**Files:**

- Create: `src/mcp/oauth/__init__.py`
- Create: `src/mcp/oauth/store.py`
- Test: `tests/mcp/test_oauth_store.py`

**Interfaces:**

- Produces:

  - `init_schema(db_path) -> None`
  - `create_client(db_path, client_id: str, metadata: dict) -> None`
  - `get_client(db_path, client_id: str) -> dict | None` — renvoie `{"client_id", "client_metadata": dict, "created_at"}`

- [ ] **Step 1: Create empty package file**

Create `src/mcp/oauth/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `tests/mcp/test_oauth_store.py`:

```python
from src.mcp.oauth import store


def test_create_and_get_client(tmp_path):
    db = tmp_path / "u.sqlite"
    store.init_schema(db)
    meta = {"redirect_uris": ["https://claude.ai/api/mcp/auth_callback"], "scope": "mcp"}
    store.create_client(db, "abc123", meta)
    row = store.get_client(db, "abc123")
    assert row["client_id"] == "abc123"
    assert row["client_metadata"] == meta
    assert store.get_client(db, "nope") is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_oauth_store.py -v`
Expected: FAIL (`ModuleNotFoundError` or `AttributeError: init_schema`).

- [ ] **Step 4: Write minimal implementation**

Create `src/mcp/oauth/store.py`:

```python
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id       TEXT PRIMARY KEY,
    client_metadata TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_codes (
    code_hash             TEXT PRIMARY KEY,
    client_id             TEXT NOT NULL,
    user_id               INTEGER NOT NULL,
    redirect_uri          TEXT,
    code_challenge        TEXT,
    code_challenge_method TEXT,
    scope                 TEXT,
    resource              TEXT,
    expires_at            TEXT NOT NULL,
    used                  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id                 INTEGER PRIMARY KEY,
    access_token_hash  TEXT NOT NULL UNIQUE,
    refresh_token_hash TEXT UNIQUE,
    client_id          TEXT NOT NULL,
    user_id            INTEGER NOT NULL,
    scope              TEXT,
    resource           TEXT NOT NULL,
    issued_at          TEXT NOT NULL,
    access_expires_at  TEXT NOT NULL,
    refresh_expires_at TEXT,
    revoked_at         TEXT,
    count_total        INTEGER NOT NULL DEFAULT 0,
    last_used_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_access ON oauth_tokens(access_token_hash);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_refresh ON oauth_tokens(refresh_token_hash);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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


def create_client(db_path, client_id: str, metadata: dict) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO oauth_clients (client_id, client_metadata, created_at) "
            "VALUES (?, ?, ?)",
            (client_id, json.dumps(metadata), _utcnow_iso()),
        )
        conn.commit()


def get_client(db_path, client_id: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["client_metadata"] = json.loads(d["client_metadata"])
    return d
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_oauth_store.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/mcp/oauth/__init__.py src/mcp/oauth/store.py tests/mcp/test_oauth_store.py
git add src/mcp/oauth/__init__.py src/mcp/oauth/store.py tests/mcp/test_oauth_store.py
git commit -m "feat(mcp): store OAuth — schéma + clients DCR (#114)"
```

---

### Task 2: OAuth store — codes d'autorisation

**Files:**

- Modify: `src/mcp/oauth/store.py`
- Test: `tests/mcp/test_oauth_store.py`

**Interfaces:**

- Consumes: `init_schema`, `_connect`, `_hash`, `_utcnow_iso` (Task 1).
- Produces:

  - `save_code(db_path, code: str, *, client_id, user_id, redirect_uri, code_challenge, code_challenge_method, scope, resource, expires_at: str) -> None`
  - `get_code(db_path, code: str) -> dict | None` — clés : `client_id, user_id, redirect_uri, code_challenge, code_challenge_method, scope, resource, expires_at, used`
  - `delete_code(db_path, code: str) -> None`

- [ ] **Step 1: Write the failing test**

Append to `tests/mcp/test_oauth_store.py`:

```python
def test_save_get_delete_code(tmp_path):
    db = tmp_path / "u.sqlite"
    store.init_schema(db)
    store.save_code(
        db,
        "thecode",
        client_id="abc",
        user_id=7,
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        code_challenge="chal",
        code_challenge_method="S256",
        scope="mcp",
        resource="https://colibre.fr/_mcp",
        expires_at="2999-01-01T00:00:00+00:00",
    )
    row = store.get_code(db, "thecode")
    assert row["user_id"] == 7
    assert row["code_challenge"] == "chal"
    assert row["resource"] == "https://colibre.fr/_mcp"
    store.delete_code(db, "thecode")
    assert store.get_code(db, "thecode") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_oauth_store.py::test_save_get_delete_code -v`
Expected: FAIL (`AttributeError: save_code`).

- [ ] **Step 3: Write minimal implementation**

Append to `src/mcp/oauth/store.py`:

```python
def save_code(
    db_path,
    code: str,
    *,
    client_id: str,
    user_id: int,
    redirect_uri: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
    scope: str | None,
    resource: str | None,
    expires_at: str,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO oauth_codes (code_hash, client_id, user_id, redirect_uri, "
            "code_challenge, code_challenge_method, scope, resource, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _hash(code),
                client_id,
                user_id,
                redirect_uri,
                code_challenge,
                code_challenge_method,
                scope,
                resource,
                expires_at,
            ),
        )
        conn.commit()


def get_code(db_path, code: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_codes WHERE code_hash = ?", (_hash(code),)
        ).fetchone()
    return dict(row) if row else None


def delete_code(db_path, code: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM oauth_codes WHERE code_hash = ?", (_hash(code),))
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_oauth_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/oauth/store.py tests/mcp/test_oauth_store.py
git add src/mcp/oauth/store.py tests/mcp/test_oauth_store.py
git commit -m "feat(mcp): store OAuth — codes d'autorisation (#114)"
```

---

### Task 3: OAuth store — tokens (access/refresh, rotation, usage)

**Files:**

- Modify: `src/mcp/oauth/store.py`
- Test: `tests/mcp/test_oauth_store.py`

**Interfaces:**

- Consumes: helpers de Task 1.
- Produces:

  - `save_token(db_path, *, access_token, refresh_token, client_id, user_id, scope, resource, access_expires_at, refresh_expires_at) -> int` (renvoie l'id de ligne)
  - `get_token_by_access(db_path, access_token: str) -> dict | None` — clés dont `id, user_id, resource, access_expires_at, revoked_at`
  - `get_token_by_refresh(db_path, refresh_token: str) -> dict | None`
  - `revoke_token(db_path, token_id: int) -> None`
  - `increment_usage(db_path, token_id: int) -> None`

- [ ] **Step 1: Write the failing test**

Append to `tests/mcp/test_oauth_store.py`:

```python
def test_save_get_revoke_token(tmp_path):
    db = tmp_path / "u.sqlite"
    store.init_schema(db)
    tid = store.save_token(
        db,
        access_token="acc",
        refresh_token="ref",
        client_id="abc",
        user_id=7,
        scope="mcp",
        resource="https://colibre.fr/_mcp",
        access_expires_at="2999-01-01T00:00:00+00:00",
        refresh_expires_at="2999-01-01T00:00:00+00:00",
    )
    assert store.get_token_by_access(db, "acc")["id"] == tid
    assert store.get_token_by_refresh(db, "ref")["user_id"] == 7
    store.increment_usage(db, tid)
    assert store.get_token_by_access(db, "acc")["count_total"] == 1
    store.revoke_token(db, tid)
    assert store.get_token_by_access(db, "acc")["revoked_at"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_oauth_store.py::test_save_get_revoke_token -v`
Expected: FAIL (`AttributeError: save_token`).

- [ ] **Step 3: Write minimal implementation**

Append to `src/mcp/oauth/store.py`:

```python
def save_token(
    db_path,
    *,
    access_token: str,
    refresh_token: str | None,
    client_id: str,
    user_id: int,
    scope: str | None,
    resource: str,
    access_expires_at: str,
    refresh_expires_at: str | None,
) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO oauth_tokens (access_token_hash, refresh_token_hash, "
            "client_id, user_id, scope, resource, issued_at, access_expires_at, "
            "refresh_expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _hash(access_token),
                _hash(refresh_token) if refresh_token else None,
                client_id,
                user_id,
                scope,
                resource,
                _utcnow_iso(),
                access_expires_at,
                refresh_expires_at,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_token_by_access(db_path, access_token: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE access_token_hash = ?",
            (_hash(access_token),),
        ).fetchone()
    return dict(row) if row else None


def get_token_by_refresh(db_path, refresh_token: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE refresh_token_hash = ?",
            (_hash(refresh_token),),
        ).fetchone()
    return dict(row) if row else None


def revoke_token(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE oauth_tokens SET revoked_at = ? WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()


def increment_usage(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE oauth_tokens SET count_total = count_total + 1, last_used_at = ? "
            "WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_oauth_store.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/oauth/store.py tests/mcp/test_oauth_store.py
git add src/mcp/oauth/store.py tests/mcp/test_oauth_store.py
git commit -m "feat(mcp): store OAuth — tokens access/refresh + usage (#114)"
```

---

### Task 4: Journal d'usage `mcp_usage`

**Files:**

- Create: `src/mcp/usage.py`
- Test: `tests/mcp/test_usage.py`

**Interfaces:**

- Produces:

  - `init_schema(db_path) -> None`
  - `record(db_path, user_id: int, token_id: int, kind: str) -> None` — best-effort, ne lève jamais
  - `count_since(db_path, user_id: int, iso_ts: str) -> int`
  - `purge_older_than(db_path, days: int = 90) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_usage.py`:

```python
from datetime import datetime, timedelta, timezone

from src.mcp import usage


def test_record_and_count_since(tmp_path):
    db = tmp_path / "u.sqlite"
    usage.init_schema(db)
    usage.record(db, user_id=7, token_id=1, kind="oauth")
    usage.record(db, user_id=7, token_id=1, kind="oauth")
    usage.record(db, user_id=9, token_id=2, kind="static")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert usage.count_since(db, 7, past) == 2
    assert usage.count_since(db, 9, past) == 1


def test_record_never_raises(tmp_path):
    # base non initialisée → record ne doit pas lever
    usage.record(tmp_path / "missing.sqlite", user_id=1, token_id=1, kind="oauth")


def test_purge_older_than(tmp_path):
    db = tmp_path / "u.sqlite"
    usage.init_schema(db)
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(timespec="seconds")
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO mcp_usage (user_id, token_id, kind, created_at) VALUES (7, 1, 'oauth', ?)",
        (old,),
    )
    conn.commit()
    conn.close()
    usage.purge_older_than(db, days=90)
    past = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    assert usage.count_since(db, 7, past) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_usage.py -v`
Expected: FAIL (`ModuleNotFoundError: src.mcp.usage`).

- [ ] **Step 3: Write minimal implementation**

Create `src/mcp/usage.py`:

```python
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_usage (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER,
    token_id   INTEGER,
    kind       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mcp_usage_user ON mcp_usage(user_id, created_at);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def record(db_path, user_id: int, token_id: int, kind: str) -> None:
    """Journalise une requête /_mcp authentifiée. Best-effort : n'échoue jamais."""
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "INSERT INTO mcp_usage (user_id, token_id, kind, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, token_id, kind, _utcnow_iso()),
            )
            conn.commit()
    except sqlite3.Error:
        pass


def count_since(db_path, user_id: int, iso_ts: str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM mcp_usage WHERE user_id = ? AND created_at >= ?",
            (user_id, iso_ts),
        ).fetchone()
    return row[0]


def purge_older_than(db_path, days: int = 90) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
        timespec="seconds"
    )
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM mcp_usage WHERE created_at < ?", (cutoff,))
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_usage.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/usage.py tests/mcp/test_usage.py
git add src/mcp/usage.py tests/mcp/test_usage.py
git commit -m "feat(mcp): journal d'usage mcp_usage (détection niveau 1, #114)"
```

---

### Task 5: Documents de découverte (metadata RFC 9728 / 8414)

**Files:**

- Create: `src/mcp/oauth/metadata.py`
- Test: `tests/mcp/test_oauth_metadata.py`

**Interfaces:**

- Produces:

  - `mcp_resource(base_url: str) -> str` → `f"{base}/_mcp"`
  - `protected_resource_metadata(base_url: str) -> dict`
  - `authorization_server_metadata(base_url: str) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_oauth_metadata.py`:

```python
from src.mcp.oauth import metadata

BASE = "https://colibre.fr"


def test_protected_resource_metadata():
    m = metadata.protected_resource_metadata(BASE)
    assert m["resource"] == "https://colibre.fr/_mcp"
    assert m["authorization_servers"] == ["https://colibre.fr"]
    assert "offline_access" in m["scopes_supported"]


def test_authorization_server_metadata():
    m = metadata.authorization_server_metadata(BASE)
    assert m["issuer"] == "https://colibre.fr"
    assert m["authorization_endpoint"] == "https://colibre.fr/oauth/authorize"
    assert m["token_endpoint"] == "https://colibre.fr/oauth/token"
    assert m["registration_endpoint"] == "https://colibre.fr/oauth/register"
    assert m["code_challenge_methods_supported"] == ["S256"]
    assert m["token_endpoint_auth_methods_supported"] == ["none"]
    assert set(m["grant_types_supported"]) == {"authorization_code", "refresh_token"}
    assert "offline_access" in m["scopes_supported"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_oauth_metadata.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

Create `src/mcp/oauth/metadata.py`:

```python
SCOPES = ["mcp", "offline_access"]


def mcp_resource(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/_mcp"


def protected_resource_metadata(base_url: str) -> dict:
    base = base_url.rstrip("/")
    return {
        "resource": mcp_resource(base),
        "authorization_servers": [base],
        "scopes_supported": SCOPES,
        "bearer_methods_supported": ["header"],
    }


def authorization_server_metadata(base_url: str) -> dict:
    base = base_url.rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "scopes_supported": SCOPES,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_oauth_metadata.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/oauth/metadata.py tests/mcp/test_oauth_metadata.py
git add src/mcp/oauth/metadata.py tests/mcp/test_oauth_metadata.py
git commit -m "feat(mcp): documents de découverte OAuth (RFC 9728/8414, #114)"
```

---

### Task 6: Gate abonnement & écrans de consentement

**Files:**

- Create: `src/mcp/oauth/consent.py`
- Test: `tests/mcp/test_oauth_consent.py`

**Interfaces:**

- Consumes: `src.subscriptions.db.has_active_subscription(user_id) -> bool`, `src.utils.TOUS_ABONNES`.
- Produces:

  - `subscription_ok(user_id: int) -> bool` — `TOUS_ABONNES or has_active_subscription(user_id)`
  - `render_subscription_required() -> str` — HTML
  - `render_consent(client_name: str, redirect_uri: str, scope: str) -> str` — HTML avec un `<form method="post">` (bouton `confirm=yes` / `confirm=no`) et le **hostname** du redirect_uri affiché

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_oauth_consent.py`:

```python
from src.mcp.oauth import consent


def test_subscription_ok_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", True)
    assert consent.subscription_ok(999) is True


def test_subscription_ok_delegates(monkeypatch):
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    monkeypatch.setattr(
        "src.mcp.oauth.consent.has_active_subscription", lambda uid: uid == 7
    )
    assert consent.subscription_ok(7) is True
    assert consent.subscription_ok(8) is False


def test_render_consent_shows_redirect_host():
    html = consent.render_consent(
        "Claude", "https://claude.ai/api/mcp/auth_callback", "mcp"
    )
    assert "claude.ai" in html
    assert "Claude" in html
    assert 'name="confirm"' in html


def test_render_subscription_required_links_abonnement():
    html = consent.render_subscription_required()
    assert "/compte/abonnement" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_oauth_consent.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

Create `src/mcp/oauth/consent.py`:

```python
from urllib.parse import urlparse

from markupsafe import escape

from src.subscriptions.db import has_active_subscription
from src.utils import TOUS_ABONNES


def subscription_ok(user_id: int) -> bool:
    return bool(TOUS_ABONNES or has_active_subscription(user_id))


def render_subscription_required() -> str:
    return (
        "<!doctype html><html lang=fr><head><meta charset=utf-8>"
        "<title>Abonnement requis — colibre</title></head><body>"
        "<h1>Abonnement requis</h1>"
        "<p>Le connecteur MCP colibre nécessite un abonnement actif.</p>"
        '<p><a href="/compte/abonnement">Gérer mon abonnement</a></p>'
        "</body></html>"
    )


def render_consent(client_name: str, redirect_uri: str, scope: str) -> str:
    host = urlparse(redirect_uri).netloc or redirect_uri
    return (
        "<!doctype html><html lang=fr><head><meta charset=utf-8>"
        "<title>Autoriser l'accès — colibre</title></head><body>"
        f"<h1>Autoriser {escape(client_name)} ?</h1>"
        f"<p><strong>{escape(client_name)}</strong> demande à lire les données "
        "colibre en votre nom via le connecteur MCP.</p>"
        f"<p>Vous serez redirigé vers <strong>{escape(host)}</strong>.</p>"
        '<form method="post">'
        '<button name="confirm" value="yes" type="submit">Autoriser</button> '
        '<button name="confirm" value="no" type="submit">Refuser</button>'
        "</form></body></html>"
    )
```

Note : `markupsafe` est déjà une dépendance transitive (Flask/Jinja).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_oauth_consent.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/oauth/consent.py tests/mcp/test_oauth_consent.py
git add src/mcp/oauth/consent.py tests/mcp/test_oauth_consent.py
git commit -m "feat(mcp): gate abonnement + écrans de consentement OAuth (#114)"
```

---

### Task 7: Configuration authlib (grants, DCR)

**Files:**

- Create: `src/mcp/oauth/server.py`
- Test: `tests/mcp/test_oauth_server.py` (smoke : l'objet serveur se construit et enregistre les grants/endpoints)

**Interfaces:**

- Consumes: `store` (Tasks 1-3), `metadata.mcp_resource` (Task 5).
- Produces:
  - `ACCESS_TTL = 3600`, `REFRESH_TTL = 5184000`
  - `create_authorization_server(app) -> AuthorizationServer` — configure `query_client`/`save_token`, enregistre `AuthorizationCodeGrant` (avec PKCE requis), `RefreshTokenGrant`, et l'endpoint DCR `ClientRegistrationEndpoint`.

> **Note authlib 1.7.2 :** les noms de méthodes des mixins (`ClientMixin`, `TokenMixin`, `AuthorizationCodeMixin`) et de l'endpoint DCR sont fixés par la version installée. Le code ci-dessous suit l'API stable d'authlib 1.x ; la **Task 9** (test d'intégration bout-en-bout) est le contrat qui valide le câblage. Si un test échoue sur un nom de méthode, ajuster d'après le message d'erreur authlib.

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_oauth_server.py`:

```python
from flask import Flask

from src.mcp.oauth import server


def test_create_authorization_server(monkeypatch, tmp_path):
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "u.sqlite"))
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x"
    srv = server.create_authorization_server(app)
    assert srv is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_oauth_server.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

Create `src/mcp/oauth/server.py`:

```python
import os
import time
from datetime import datetime, timedelta, timezone

from authlib.integrations.flask_oauth2 import AuthorizationServer
from authlib.oauth2.rfc6749 import grants
from authlib.oauth2.rfc7591 import ClientRegistrationEndpoint
from authlib.oauth2.rfc7636 import CodeChallenge

from src.mcp.oauth import metadata, store

ACCESS_TTL = 3600  # 1 h
REFRESH_TTL = 5184000  # 60 j


def _db() -> str:
    return os.environ["USERS_DB_PATH"]


def _base() -> str:
    return os.getenv("APP_BASE_URL", "").rstrip("/")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def _expired(iso_ts: str) -> bool:
    return datetime.fromisoformat(iso_ts) < datetime.now(timezone.utc)


class _Client:
    def __init__(self, row: dict):
        self.client_id = row["client_id"]
        self.client_metadata = row["client_metadata"]

    def get_client_id(self):
        return self.client_id

    def get_default_redirect_uri(self):
        uris = self.client_metadata.get("redirect_uris") or []
        return uris[0] if uris else None

    def get_allowed_scope(self, scope):
        if not scope:
            return ""
        allowed = set((self.client_metadata.get("scope") or "").split())
        return " ".join(s for s in scope.split() if s in allowed)

    def check_redirect_uri(self, redirect_uri):
        return redirect_uri in (self.client_metadata.get("redirect_uris") or [])

    def check_client_secret(self, client_secret):
        return False  # client public

    def check_endpoint_auth_method(self, method, endpoint):
        return method == "none"

    def check_response_type(self, response_type):
        return response_type == "code"

    def check_grant_type(self, grant_type):
        return grant_type in ("authorization_code", "refresh_token")


def query_client(client_id):
    row = store.get_client(_db(), client_id)
    return _Client(row) if row else None


def save_token(token, request):
    resource = (
        request.form.get("resource")
        or request.args.get("resource")
        or metadata.mcp_resource(_base())
    )
    now = time.time()
    store.save_token(
        _db(),
        access_token=token["access_token"],
        refresh_token=token.get("refresh_token"),
        client_id=request.client.get_client_id(),
        user_id=int(request.user),
        scope=token.get("scope", ""),
        resource=resource,
        access_expires_at=_iso(now + token.get("expires_in", ACCESS_TTL)),
        refresh_expires_at=_iso(now + REFRESH_TTL),
    )


class _AuthCode:
    def __init__(self, row: dict):
        self._row = row
        self.user_id = row["user_id"]
        self.code_challenge = row["code_challenge"]
        self.code_challenge_method = row["code_challenge_method"]

    def get_redirect_uri(self):
        return self._row["redirect_uri"]

    def get_scope(self):
        return self._row["scope"] or ""


class AuthorizationCodeGrant(grants.AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

    def save_authorization_code(self, code, request):
        store.save_code(
            _db(),
            code,
            client_id=request.client.get_client_id(),
            user_id=int(request.user),
            redirect_uri=request.redirect_uri,
            code_challenge=request.data.get("code_challenge"),
            code_challenge_method=request.data.get("code_challenge_method"),
            scope=request.scope,
            resource=request.data.get("resource") or metadata.mcp_resource(_base()),
            expires_at=_iso(time.time() + 300),
        )

    def query_authorization_code(self, code, client):
        row = store.get_code(_db(), code)
        if (
            row
            and row["client_id"] == client.get_client_id()
            and not _expired(row["expires_at"])
        ):
            return _AuthCode(row)
        return None

    def delete_authorization_code(self, authorization_code):
        # code_challenge est unique par code ; on supprime par le hash côté store
        # via le code d'origine reconstruit impossible → on stocke le code clair
        # dans l'objet. Ici authorization_code provient de query ; on supprime par
        # la ligne complète.
        store.delete_code(_db(), authorization_code._raw_code)

    def authenticate_user(self, authorization_code):
        return authorization_code.user_id


class RefreshTokenGrant(grants.RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    INCLUDE_NEW_REFRESH_TOKEN = True  # rotation

    def authenticate_refresh_token(self, refresh_token):
        row = store.get_token_by_refresh(_db(), refresh_token)
        if not row or row["revoked_at"] is not None:
            return None
        if row["refresh_expires_at"] and _expired(row["refresh_expires_at"]):
            return None
        return row

    def authenticate_user(self, credential):
        from src.mcp.oauth.consent import subscription_ok

        uid = credential["user_id"]
        # Re-vérifie l'abonnement au refresh : perdu → invalid_grant.
        if not subscription_ok(uid):
            return None
        return uid

    def revoke_old_credential(self, credential):
        store.revoke_token(_db(), credential["id"])


class _RegistrationEndpoint(ClientRegistrationEndpoint):
    def authenticate_token(self, request):
        # DCR ouverte (client public) : pas de jeton d'enregistrement requis.
        return True

    def resolve_public_key(self, request):
        return None

    def get_server_metadata(self):
        return metadata.authorization_server_metadata(_base())

    def save_client(self, client_info, client_metadata, request):
        client_id = client_info["client_id"]
        store.create_client(_db(), client_id, dict(client_metadata))
        return _Client(
            {"client_id": client_id, "client_metadata": dict(client_metadata)}
        )


def create_authorization_server(app) -> AuthorizationServer:
    server = AuthorizationServer(app, query_client=query_client, save_token=save_token)
    server.register_grant(AuthorizationCodeGrant, [CodeChallenge(required=True)])
    server.register_grant(RefreshTokenGrant)
    server.register_endpoint(_RegistrationEndpoint)
    return server
```

> **Contrat de suppression de code (PKCE)** : pour que `delete_authorization_code` retrouve la ligne, `query_authorization_code` doit conserver le code clair. Ajouter dans `_AuthCode.__init__` : `self._raw_code = None`, puis dans `query_authorization_code`, après construction : `obj = _AuthCode(row); obj._raw_code = code; return obj`. (Le store indexe par hash ; on redonne le code clair reçu à `delete_code`.)

Corriger `query_authorization_code` en conséquence :

```python
    def query_authorization_code(self, code, client):
        row = store.get_code(_db(), code)
        if (
            row
            and row["client_id"] == client.get_client_id()
            and not _expired(row["expires_at"])
        ):
            obj = _AuthCode(row)
            obj._raw_code = code
            return obj
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_oauth_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/oauth/server.py tests/mcp/test_oauth_server.py
git add src/mcp/oauth/server.py tests/mcp/test_oauth_server.py
git commit -m "feat(mcp): configuration authlib (grants + PKCE + DCR, #114)"
```

---

### Task 8: Blueprint routes — well-known & DCR

**Files:**

- Create: `src/mcp/oauth/routes.py`
- Test: `tests/mcp/test_oauth_routes_metadata.py`

**Interfaces:**

- Consumes: `metadata` (Task 5), `server.create_authorization_server` (Task 7), `consent` (Task 6), `store` (Tasks 1-3).
- Produces:

  - `oauth_bp` (Blueprint)
  - `init_oauth(app) -> None` — crée le serveur authlib, enregistre les routes `/authorize` et `/token` sur le serveur, enregistre `oauth_bp` (well-known + `/oauth/register` + `/oauth/revoke`) sur `app`.

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_oauth_routes_metadata.py`:

```python
import pytest
from flask import Flask


@pytest.fixture
def oauth_app(monkeypatch, tmp_path):
    from src.mcp.oauth import routes, store

    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "u.sqlite"))
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    store.init_schema(tmp_path / "u.sqlite")
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x"
    routes.init_oauth(app)
    return app


def test_protected_resource_wellknown(oauth_app):
    resp = oauth_app.test_client().get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    assert resp.get_json()["resource"] == "https://colibre.fr/_mcp"


def test_protected_resource_wellknown_mcp_suffix(oauth_app):
    resp = oauth_app.test_client().get("/.well-known/oauth-protected-resource/_mcp")
    assert resp.status_code == 200
    assert resp.get_json()["resource"] == "https://colibre.fr/_mcp"


def test_as_metadata_and_openid(oauth_app):
    for path in (
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
    ):
        resp = oauth_app.test_client().get(path)
        assert resp.status_code == 200
        assert resp.get_json()["code_challenge_methods_supported"] == ["S256"]


def test_dynamic_client_registration(oauth_app):
    resp = oauth_app.test_client().post(
        "/oauth/register",
        json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "client_name": "Claude",
            "token_endpoint_auth_method": "none",
        },
    )
    assert resp.status_code == 201
    assert "client_id" in resp.get_json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_oauth_routes_metadata.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

Create `src/mcp/oauth/routes.py`:

```python
import os

from flask import Blueprint, jsonify, request

from src.mcp.oauth import metadata, server

oauth_bp = Blueprint("mcp_oauth", __name__)

_server = None  # AuthorizationServer, initialisé par init_oauth


def _base() -> str:
    return os.getenv("APP_BASE_URL", "").rstrip("/")


@oauth_bp.route("/.well-known/oauth-protected-resource")
@oauth_bp.route("/.well-known/oauth-protected-resource/_mcp")
def protected_resource():
    return jsonify(metadata.protected_resource_metadata(_base()))


@oauth_bp.route("/.well-known/oauth-authorization-server")
@oauth_bp.route("/.well-known/oauth-authorization-server/_mcp")
@oauth_bp.route("/.well-known/openid-configuration")
def as_metadata():
    return jsonify(metadata.authorization_server_metadata(_base()))


@oauth_bp.route("/oauth/register", methods=["POST"])
def register():
    return _server.create_endpoint_response("client_registration")


@oauth_bp.route("/oauth/revoke", methods=["POST"])
def revoke():
    return _server.create_endpoint_response("revocation")


def init_oauth(app) -> None:
    global _server
    _server = server.create_authorization_server(app)

    from src.mcp.oauth.authorize import authorize as _authorize  # Task 9
    from src.mcp.oauth.authorize import token as _token  # Task 9

    app.add_url_rule(
        "/oauth/authorize", "oauth_authorize", _authorize, methods=["GET", "POST"]
    )
    app.add_url_rule("/oauth/token", "oauth_token", _token, methods=["POST"])
    app.register_blueprint(oauth_bp)
```

> **Note :** `init_oauth` importe `authorize`/`token` depuis `src/mcp/oauth/authorize.py`, créé en Task 9. Pour faire passer les tests de CETTE tâche (qui ne touchent ni `/authorize` ni `/token`), créer d'abord un stub minimal `src/mcp/oauth/authorize.py` :
>
> ```python
> def authorize():
>     return "", 501
>
>
> def token():
>     return "", 501
> ```
>
> La Task 9 remplace ce stub par l'implémentation réelle.

Also register the revocation endpoint in `server.py` `create_authorization_server` (ajout) :

```python
    from authlib.oauth2.rfc7009 import RevocationEndpoint

    class _RevocationEndpoint(RevocationEndpoint):
        def query_token(self, token_string, token_type_hint):
            return store.get_token_by_access(_db(), token_string) or store.get_token_by_refresh(
                _db(), token_string
            )

        def revoke_token(self, token, request):
            store.revoke_token(_db(), token["id"])

    server.register_endpoint(_RevocationEndpoint)
```

(Ajouter ces lignes dans `create_authorization_server` avant le `return server`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_oauth_routes_metadata.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/oauth/routes.py src/mcp/oauth/server.py src/mcp/oauth/authorize.py tests/mcp/test_oauth_routes_metadata.py
git add src/mcp/oauth/routes.py src/mcp/oauth/server.py src/mcp/oauth/authorize.py tests/mcp/test_oauth_routes_metadata.py
git commit -m "feat(mcp): routes découverte + DCR + révocation OAuth (#114)"
```

---

### Task 9: Flux authorize + token (bout-en-bout, gate abonnement)

**Files:**

- Modify: `src/mcp/oauth/authorize.py` (remplace le stub)
- Test: `tests/mcp/test_oauth_flow.py`

**Interfaces:**

- Consumes: `_server` de `routes` (via import), `consent` (Task 6), flask_login `current_user`.
- Produces:

  - `authorize()` — GET : validation + login + gate abonnement + écran consentement ; POST : émission du code.
  - `token()` — délègue à authlib.

- [ ] **Step 1: Write the failing test**

Create `tests/mcp/test_oauth_flow.py`:

```python
import base64
import hashlib
import re

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin, login_user


class _U(UserMixin):
    def __init__(self, uid):
        self.id = uid


def _pkce():
    verifier = "a" * 64
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


@pytest.fixture
def flow_app(monkeypatch, tmp_path):
    from src.auth import db as auth_db
    from src.mcp.oauth import routes, store
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "u.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()
    store.init_schema(db_path)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "x"
    app.config["SERVER_NAME"] = "colibre.fr"
    lm = LoginManager()
    lm.init_app(app)
    lm.user_loader(lambda uid: _U(int(uid)))
    routes.init_oauth(app)

    @app.route("/_test_login/<int:uid>")
    def _test_login(uid):
        login_user(_U(uid))
        return "ok"

    yield app, db_path
    auth_db.reset_conn_for_tests()


def _register(client):
    resp = client.post(
        "/oauth/register",
        json={
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "client_name": "Claude",
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "scope": "mcp offline_access",
        },
    )
    return resp.get_json()["client_id"]


def test_authorize_requires_subscription(flow_app, monkeypatch):
    from src.auth import db as auth_db

    app, _ = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("nosub@ex.fr", "h")
    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    _, challenge = _pkce()
    resp = client.get(
        "/oauth/authorize",
        query_string={
            "client_id": cid,
            "response_type": "code",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "scope": "mcp",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": "https://colibre.fr/_mcp",
        },
    )
    assert b"Abonnement requis" in resp.data


def test_full_flow_issues_audience_bound_token(flow_app, monkeypatch):
    from src.auth import db as auth_db
    from src.mcp.oauth import store
    from src.subscriptions import db as sub_db

    app, db_path = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("sub@ex.fr", "h")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")

    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    verifier, challenge = _pkce()
    qs = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "scope": "mcp",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": "https://colibre.fr/_mcp",
    }
    # GET affiche le consentement
    assert b"Autoriser" in client.get("/oauth/authorize", query_string=qs).data
    # POST confirme → redirection avec ?code=
    resp = client.post("/oauth/authorize", query_string=qs, data={"confirm": "yes"})
    assert resp.status_code == 302
    code = re.search(r"code=([^&]+)", resp.headers["Location"]).group(1)
    # échange du code
    tok = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": cid,
            "code_verifier": verifier,
            "resource": "https://colibre.fr/_mcp",
        },
    )
    assert tok.status_code == 200
    access = tok.get_json()["access_token"]
    row = store.get_token_by_access(db_path, access)
    assert row["user_id"] == uid
    assert row["resource"] == "https://colibre.fr/_mcp"


def test_wrong_verifier_rejected(flow_app, monkeypatch):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    app, _ = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("sub2@ex.fr", "h")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")
    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    _, challenge = _pkce()
    qs = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "scope": "mcp",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    resp = client.post("/oauth/authorize", query_string=qs, data={"confirm": "yes"})
    code = re.search(r"code=([^&]+)", resp.headers["Location"]).group(1)
    tok = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": cid,
            "code_verifier": "wrong" * 13,
        },
    )
    assert tok.status_code == 400
    assert tok.get_json()["error"] == "invalid_grant"


def _obtain_tokens(client, cid, monkeypatch):
    verifier, challenge = _pkce()
    qs = {
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "scope": "mcp offline_access",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    resp = client.post("/oauth/authorize", query_string=qs, data={"confirm": "yes"})
    code = re.search(r"code=([^&]+)", resp.headers["Location"]).group(1)
    tok = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": cid,
            "code_verifier": verifier,
        },
    )
    return tok.get_json()


def test_refresh_rotates_and_requires_subscription(flow_app, monkeypatch):
    from src.auth import db as auth_db
    from src.mcp.oauth import store
    from src.subscriptions import db as sub_db

    app, db_path = flow_app
    monkeypatch.setattr("src.mcp.oauth.consent.TOUS_ABONNES", False)
    uid = auth_db.create_user("ref@ex.fr", "h")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")
    client = app.test_client()
    client.get(f"/_test_login/{uid}")
    cid = _register(client)
    first = _obtain_tokens(client, cid, monkeypatch)
    assert "refresh_token" in first

    # Refresh réussi → nouveau refresh (rotation), ancien révoqué.
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": first["refresh_token"],
            "client_id": cid,
        },
    )
    assert r.status_code == 200
    assert r.get_json()["refresh_token"] != first["refresh_token"]
    assert store.get_token_by_refresh(db_path, first["refresh_token"])["revoked_at"]

    # Abonnement perdu → refresh refusé (invalid_grant).
    new_refresh = r.get_json()["refresh_token"]
    monkeypatch.setattr(
        "src.mcp.oauth.consent.has_active_subscription", lambda u: False
    )
    r2 = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": new_refresh,
            "client_id": cid,
        },
    )
    assert r2.status_code == 400
    assert r2.get_json()["error"] == "invalid_grant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_oauth_flow.py -v`
Expected: FAIL (le stub renvoie 501).

- [ ] **Step 3: Write the implementation**

Replace `src/mcp/oauth/authorize.py`:

```python
from urllib.parse import urlencode

from flask import redirect, request
from flask_login import current_user

from src.mcp.oauth import consent


def _login_redirect():
    target = f"/oauth/authorize?{urlencode(request.args)}"
    return redirect(f"/connexion?next={target}")


def authorize():
    from src.mcp.oauth.routes import _server

    if not current_user.is_authenticated:
        return _login_redirect()

    if not consent.subscription_ok(int(current_user.id)):
        return consent.render_subscription_required(), 403

    if request.method == "GET":
        grant = _server.get_consent_grant(end_user=current_user)
        client = grant.client
        scope = grant.request.scope or "mcp"
        return consent.render_consent(
            client.client_metadata.get("client_name", client.get_client_id()),
            grant.request.redirect_uri or client.get_default_redirect_uri(),
            scope,
        )

    # POST
    if request.form.get("confirm") != "yes":
        return _server.create_authorization_response(grant_user=None)
    return _server.create_authorization_response(grant_user=current_user.id)


def token():
    from src.mcp.oauth.routes import _server

    return _server.create_token_response()
```

> **Note authlib** : `get_consent_grant(end_user=...)`, `create_authorization_response(grant_user=...)` et `create_token_response()` sont les méthodes de `AuthorizationServer`. `grant_user` doit être ce que `authenticate_user` renverra plus tard — ici l'`user_id` (int), cohérent avec `AuthorizationCodeGrant.authenticate_user` qui lit `authorization_code.user_id`. Si authlib exige un objet, adapter `save_authorization_code` (`int(request.user)`) — le test bout-en-bout tranche.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_oauth_flow.py -v`
Expected: PASS (4 tests). Ajuster le câblage authlib jusqu'au vert si un nom de méthode diffère (cf. notes Task 7/9).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/oauth/authorize.py tests/mcp/test_oauth_flow.py
git add src/mcp/oauth/authorize.py tests/mcp/test_oauth_flow.py
git commit -m "feat(mcp): flux OAuth authorize+token avec gate abonnement (#114)"
```

---

### Task 10: Garde `/_mcp` unifié (statique + OAuth)

**Files:**

- Modify: `src/mcp/auth.py`
- Test: `tests/mcp/test_auth.py` (étendre)

**Interfaces:**

- Consumes: `store.get_token_by_access`, `store.increment_usage` (Task 3), `metadata.mcp_resource` (Task 5), `usage.record` (Task 4).
- Produces (comportement) : garde accepte un token OAuth valide ; 401 porte `resource_metadata` ; journalise `mcp_usage` sur succès.

- [ ] **Step 1: Write the failing test**

Append to `tests/mcp/test_auth.py`:

```python
def test_oauth_token_active_subscription_passes(mcp_app, monkeypatch):
    import time

    from src.mcp.oauth import server, store

    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    app, db_path = mcp_app
    store.init_schema(db_path)
    uid = _subscribed_uid()
    store.create_client(db_path, "cid", {"redirect_uris": []})
    store.save_token(
        db_path,
        access_token="opaque123",
        refresh_token=None,
        client_id="cid",
        user_id=uid,
        scope="mcp",
        resource="https://colibre.fr/_mcp",
        access_expires_at=server._iso(time.time() + 3600),
        refresh_expires_at=None,
    )
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": "Bearer opaque123"}
    )
    assert resp.status_code == 200


def test_oauth_token_wrong_audience_401(mcp_app, monkeypatch):
    import time

    from src.mcp.oauth import server, store

    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    app, db_path = mcp_app
    store.init_schema(db_path)
    uid = _subscribed_uid()
    store.save_token(
        db_path,
        access_token="badaud",
        refresh_token=None,
        client_id="cid",
        user_id=uid,
        scope="mcp",
        resource="https://evil.example/_mcp",
        access_expires_at=server._iso(time.time() + 3600),
        refresh_expires_at=None,
    )
    resp = app.test_client().post("/_mcp", headers={"Authorization": "Bearer badaud"})
    assert resp.status_code == 401


def test_401_carries_resource_metadata(mcp_app, monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    app, _ = mcp_app
    resp = app.test_client().post("/_mcp")
    assert resp.status_code == 401
    assert "resource_metadata=" in resp.headers["WWW-Authenticate"]


def test_oauth_token_no_subscription_403(mcp_app, monkeypatch):
    import time

    from src.auth import db as auth_db
    from src.mcp.oauth import server, store

    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    monkeypatch.setattr("src.mcp.auth.TOUS_ABONNES", False)
    app, db_path = mcp_app
    store.init_schema(db_path)
    uid = auth_db.create_user("nosuboauth@ex.fr", "h")  # aucun abonnement
    store.save_token(
        db_path,
        access_token="nosubtok",
        refresh_token=None,
        client_id="cid",
        user_id=uid,
        scope="mcp",
        resource="https://colibre.fr/_mcp",
        access_expires_at=server._iso(time.time() + 3600),
        refresh_expires_at=None,
    )
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": "Bearer nosubtok"}
    )
    assert resp.status_code == 403
```

> **Note fixture** : la fixture `mcp_app` de `tests/mcp/test_auth.py` doit initialiser aussi les schémas OAuth et usage. Modifier la fixture pour ajouter, après `tokens_db.init_schema(db_path)` :
>
> ```python
>     from src.mcp import usage
>     from src.mcp.oauth import store as oauth_store
>
>     oauth_store.init_schema(db_path)
>     usage.init_schema(db_path)
> ```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_auth.py -k "oauth or resource_metadata" -v`
Expected: FAIL (garde ne connaît pas les tokens OAuth ; header sans `resource_metadata`).

- [ ] **Step 3: Write the implementation**

Replace `src/mcp/auth.py`:

```python
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from src.api import tokens_db
from src.mcp import usage
from src.mcp.oauth import metadata, store
from src.subscriptions.db import has_active_subscription
from src.utils import TOUS_ABONNES


def _base() -> str:
    return os.getenv("APP_BASE_URL", "").rstrip("/")


def _resource_metadata_url() -> str:
    return f"{_base()}/.well-known/oauth-protected-resource/_mcp"


def _unauthorized():
    resp = jsonify(
        {"error": "unauthorized", "message": "Jeton MCP absent ou invalide."}
    )
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = (
        f'Bearer realm="colibre-mcp", resource_metadata="{_resource_metadata_url()}"'
    )
    return resp


def _forbidden():
    resp = jsonify(
        {
            "error": "no_active_subscription",
            "message": "Un abonnement colibre actif est requis pour le connecteur MCP.",
        }
    )
    resp.status_code = 403
    return resp


def _expired(iso_ts: str) -> bool:
    return datetime.fromisoformat(iso_ts) < datetime.now(timezone.utc)


def _authorize_static(db_path, token):
    row = tokens_db.get_token_by_plaintext(db_path, token)
    if row is None or row["revoked_at"] is not None or row["kind"] != "mcp":
        return None, None
    return row["user_id"], ("static", row["id"])


def _authorize_oauth(db_path, token):
    row = store.get_token_by_access(db_path, token)
    if row is None or row["revoked_at"] is not None:
        return None, None
    if _expired(row["access_expires_at"]):
        return None, None
    if row["resource"] != metadata.mcp_resource(_base()):
        return None, None
    return row["user_id"], ("oauth", row["id"])


def _authenticate_mcp():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return _unauthorized()
    token = header[len("Bearer ") :].strip()
    if not token:
        return _unauthorized()

    db_path = os.environ["USERS_DB_PATH"]
    if token.startswith("colibre_"):
        user_id, meta = _authorize_static(db_path, token)
    else:
        user_id, meta = _authorize_oauth(db_path, token)

    if meta is None:
        return _unauthorized()
    if user_id is None:
        return _forbidden()
    if not (TOUS_ABONNES or has_active_subscription(user_id)):
        return _forbidden()

    kind, token_id = meta
    if kind == "static":
        tokens_db.increment_usage(db_path, token_id)
    else:
        store.increment_usage(db_path, token_id)
    usage.record(db_path, user_id, token_id, kind)
    return None


def init_mcp_auth(server: Flask) -> None:
    """Enregistre le garde d'authentification du serveur MCP (/_mcp)."""

    @server.before_request
    def _guard_mcp():
        if request.path == "/_mcp" or request.path.startswith("/_mcp/"):
            return _authenticate_mcp()
        return None
```

> **Régression à vérifier** : le test existant `test_missing_header_401_with_challenge` asserte l'égalité stricte `== 'Bearer realm="colibre-mcp"'`. Le header contient désormais `resource_metadata`. Mettre à jour cette assertion existante en `assert resp.headers["WWW-Authenticate"].startswith('Bearer realm="colibre-mcp"')`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_auth.py -v`
Expected: PASS (tous, dont les 3 nouveaux et l'existant mis à jour).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/auth.py tests/mcp/test_auth.py
git add src/mcp/auth.py tests/mcp/test_auth.py
git commit -m "feat(mcp): garde /_mcp unifié statique+OAuth, audience & usage (#114)"
```

---

### Task 11: Migrations & câblage `app.py`

**Files:**

- Modify: `src/migrations.py`
- Modify: `src/app.py`
- Test: `tests/mcp/test_app_wiring.py` (étendre)

**Interfaces:**

- Consumes: `store.init_schema`, `usage.init_schema`, `usage.purge_older_than`, `routes.init_oauth`.
- Produces (comportement) : au démarrage avec `DASH_MCP_ENABLED=true`, les tables OAuth/usage existent et les routes well-known répondent.

- [ ] **Step 1: Add migrations**

Append to `_MIGRATIONS` in `src/migrations.py` (les tables sont aussi créées par `init_schema` ; ces migrations garantissent la trace + une DB existante) :

```python
    (
        "0008_create_oauth_clients",
        "CREATE TABLE IF NOT EXISTS oauth_clients ("
        "client_id TEXT PRIMARY KEY, client_metadata TEXT NOT NULL, "
        "created_at TEXT NOT NULL)",
    ),
    (
        "0009_create_oauth_codes",
        "CREATE TABLE IF NOT EXISTS oauth_codes ("
        "code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_id INTEGER NOT NULL, "
        "redirect_uri TEXT, code_challenge TEXT, code_challenge_method TEXT, "
        "scope TEXT, resource TEXT, expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0)",
    ),
    (
        "0010_create_oauth_tokens",
        "CREATE TABLE IF NOT EXISTS oauth_tokens ("
        "id INTEGER PRIMARY KEY, access_token_hash TEXT NOT NULL UNIQUE, "
        "refresh_token_hash TEXT UNIQUE, client_id TEXT NOT NULL, user_id INTEGER NOT NULL, "
        "scope TEXT, resource TEXT NOT NULL, issued_at TEXT NOT NULL, "
        "access_expires_at TEXT NOT NULL, refresh_expires_at TEXT, revoked_at TEXT, "
        "count_total INTEGER NOT NULL DEFAULT 0, last_used_at TEXT)",
    ),
    (
        "0011_create_mcp_usage",
        "CREATE TABLE IF NOT EXISTS mcp_usage ("
        "id INTEGER PRIMARY KEY, user_id INTEGER, token_id INTEGER, "
        "kind TEXT NOT NULL, created_at TEXT NOT NULL)",
    ),
```

- [ ] **Step 2: Write the failing test**

Append to `tests/mcp/test_app_wiring.py` (ou créer un test dédié si le fichier n'a pas de fixture réutilisable — vérifier son contenu d'abord) :

```python
def test_oauth_wellknown_served_when_mcp_enabled(monkeypatch):
    monkeypatch.setenv("DASH_MCP_ENABLED", "true")
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    import importlib

    import src.app as app_module

    importlib.reload(app_module)
    client = app_module.app.server.test_client()
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    assert resp.get_json()["resource"] == "https://colibre.fr/_mcp"
```

> **Note** : lire `tests/mcp/test_app_wiring.py` avant d'écrire ; il charge déjà l'app avec `DASH_MCP_ENABLED`. Réutiliser sa fixture/pattern de reload plutôt que d'en dupliquer un.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_app_wiring.py -k wellknown -v`
Expected: FAIL (routes well-known absentes).

- [ ] **Step 4: Wire into `app.py`**

Dans `src/app.py`, à l'intérieur du bloc `if _mcp_enabled:` (après `init_mcp_auth(app.server)`), ajouter :

```python
    # Serveur d'autorisation OAuth 2.1 (scope B2, #114) : découverte, DCR,
    # authorize/token, révocation. Réutilise la session flask_login.
    from src.mcp import usage  # noqa: E402
    from src.mcp.oauth import routes as oauth_routes  # noqa: E402
    from src.mcp.oauth import store as oauth_store  # noqa: E402

    _users_db = os.environ["USERS_DB_PATH"]
    oauth_store.init_schema(_users_db)
    usage.init_schema(_users_db)
    usage.purge_older_than(_users_db)

    oauth_routes.init_oauth(app.server)

    # Exempter les routes OAuth du CSRF (POST externes JSON-RPC/form sans jeton).
    if _auth_csrf is not None:
        for _rule in app.server.url_map.iter_rules():
            if _rule.rule.startswith("/oauth") or _rule.rule.startswith(
                "/.well-known/oauth"
            ):
                _vf = app.server.view_functions.get(_rule.endpoint)
                if _vf is not None:
                    _auth_csrf.exempt(_vf)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_app_wiring.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
pre-commit run --files src/migrations.py src/app.py tests/mcp/test_app_wiring.py
git add src/migrations.py src/app.py tests/mcp/test_app_wiring.py
git commit -m "feat(mcp): migrations OAuth/usage + câblage app.py (#114)"
```

---

### Task 12: Instructions client `/compte/mcp` (Claude.ai / ChatGPT)

**Files:**

- Modify: `src/pages/compte/mcp.py`
- Test: `tests/mcp/test_account_page.py` (étendre)

**Interfaces:**

- Consumes: rien de neuf ; modifie `client_instructions(url, token)` (fonction pure existante).
- Produces : l'accordéon inclut des entrées Claude.ai/Desktop et ChatGPT décrivant l'ajout par URL (flux OAuth), sans jeton.

- [ ] **Step 1: Write the failing test**

Append to `tests/mcp/test_account_page.py`:

```python
def test_client_instructions_include_oauth_apps():
    from src.pages.compte.mcp import client_instructions

    comp = client_instructions("https://colibre.fr/_mcp", "<VOTRE_JETON>")
    titles = _collect_titles(comp)
    assert any("Claude.ai" in t for t in titles)
    assert any("ChatGPT" in t for t in titles)


def _collect_titles(component):
    # Parcourt récursivement les AccordionItem pour collecter leurs `title`.
    found = []

    def walk(node):
        title = getattr(node, "title", None)
        if isinstance(title, str):
            found.append(title)
        children = getattr(node, "children", None)
        if isinstance(children, (list, tuple)):
            for c in children:
                walk(c)
        elif children is not None:
            walk(children)

    walk(component)
    return found
```

> **Note** : vérifier le contenu actuel de `tests/mcp/test_account_page.py` d'abord ; s'il teste déjà `client_instructions`, réutiliser son helper de parcours plutôt que d'en dupliquer un.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/mcp/test_account_page.py -k oauth_apps -v`
Expected: FAIL (pas d'item « Claude.ai » ; l'item actuel s'appelle « Claude Code » et « ChatGPT » existe mais avec l'ancien texte — l'assert Claude.ai échoue).

- [ ] **Step 3: Write the implementation**

Dans `src/pages/compte/mcp.py`, remplacer le corps de `client_instructions` pour ajouter une entrée Claude.ai/Desktop et réécrire l'entrée ChatGPT. Remplacer l'`AccordionItem` ChatGPT et ajouter un item Claude.ai (après l'item « Claude Code ») :

```python
            dbc.AccordionItem(
                title="Claude.ai / Claude Desktop / mobile",
                children=[
                    html.P(
                        "Aucun jeton à copier : ces applications utilisent OAuth."
                    ),
                    html.Ol(
                        [
                            html.Li("Paramètres → Connecteurs → Ajouter un connecteur personnalisé."),
                            html.Li(f"URL du serveur MCP : {url}"),
                            html.Li("Laissez le champ « Client Secret » vide (client public)."),
                            html.Li("Connectez-vous avec votre compte colibre, puis « Autoriser »."),
                        ]
                    ),
                ],
            ),
            dbc.AccordionItem(
                title="ChatGPT",
                children=[
                    html.P(
                        "ChatGPT utilise aussi OAuth (aucun jeton à copier). Dans les "
                        "connecteurs, ajoutez un connecteur par URL :"
                    ),
                    html.Ol(
                        [
                            html.Li(f"URL du serveur MCP : {url}"),
                            html.Li("Connectez-vous avec colibre, puis autorisez l'accès."),
                        ]
                    ),
                    html.P(
                        "La disponibilité des connecteurs dépend de votre plan ChatGPT.",
                        className="text-muted",
                    ),
                ],
            ),
```

Et compléter le paragraphe d'intro de `layout()` (le `html.P` sous « Connecteur MCP ») pour distinguer jeton (CLI) et OAuth (apps) :

```python
            html.P(
                "Les clients en ligne de commande (Claude Code, Gemini, Mistral) se "
                "connectent avec un jeton généré ci-dessous. Les applications grand "
                "public (Claude.ai, ChatGPT) se connectent par OAuth, sans jeton à "
                "copier. Dans tous les cas, un abonnement actif est requis."
            ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/mcp/test_account_page.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/compte/mcp.py tests/mcp/test_account_page.py
git add src/pages/compte/mcp.py tests/mcp/test_account_page.py
git commit -m "feat(mcp): instructions OAuth Claude.ai/ChatGPT sur /compte/mcp (#114)"
```

---

### Task 13: `.template.env`, vérification finale & suite complète

**Files:**

- Modify: `.template.env`
- Test: toute la suite.

- [ ] **Step 1: Documenter la config**

Dans `.template.env`, sous la ligne `DASH_MCP_ENABLED`, ajouter :

```bash
# Le connecteur MCP OAuth (Claude.ai, ChatGPT) requiert APP_BASE_URL en HTTPS
# et que l'egress Anthropic 160.79.104.0/21 puisse joindre le serveur.
# APP_BASE_URL sert d'issuer OAuth et à construire les URLs de découverte.
```

- [ ] **Step 2: Lancer la suite MCP**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS (tous les fichiers `test_oauth_*`, `test_usage`, `test_auth`, `test_account_page`, `test_app_wiring`).

- [ ] **Step 3: Lancer la suite complète**

Run: `uv run pytest`
Expected: PASS (aucune régression sur l'API REST ni le reste).

- [ ] **Step 4: Commit**

```bash
pre-commit run --files .template.env
git add .template.env
git commit -m "docs(mcp): documenter APP_BASE_URL/egress pour le connecteur OAuth (#114)"
```

---

## Notes d'intégration authlib (référence transverse)

- authlib 1.7.2 : `from authlib.integrations.flask_oauth2 import AuthorizationServer`.
- `AuthorizationServer(app, query_client=..., save_token=...)` puis `register_grant`, `register_endpoint`.
- `get_consent_grant(end_user=...)`, `create_authorization_response(grant_user=...)`, `create_token_response()`, `create_endpoint_response(name)`.
- PKCE : `from authlib.oauth2.rfc7636 import CodeChallenge` → `register_grant(AuthorizationCodeGrant, [CodeChallenge(required=True)])`.
- DCR : `from authlib.oauth2.rfc7591 import ClientRegistrationEndpoint` (nom d'endpoint `"client_registration"`).
- Révocation : `from authlib.oauth2.rfc7009 import RevocationEndpoint` (nom `"revocation"`).
- Les noms exacts des méthodes des mixins peuvent varier légèrement ; **les tests d'intégration (Tasks 8-9) sont le contrat** — itérer jusqu'au vert en suivant les messages d'erreur authlib, sans changer le comportement testé.
