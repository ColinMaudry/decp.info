# Connecteur MCP (scope B, #111) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conditionner l'accès au serveur MCP colibre (`/_mcp`) à un abonnement actif, via un jeton Bearer statique dédié que l'abonné génère depuis `/compte/mcp` (« Connecteur MCP »).

**Architecture:** Réutilise la table `api_tokens` (jetons `colibre_…` hachés) en ajoutant une colonne `kind` (`'api'`|`'mcp'`). Un garde Flask `before_request` sur `/_mcp` valide le jeton (`kind='mcp'`, non révoqué) puis l'abonnement actif du propriétaire. Une page compte gérée par formulaires Flask (POST + CSRF) permet de générer/révoquer les jetons et documente la connexion pour Claude, Gemini, Mistral et ChatGPT.

**Tech Stack:** Python, Flask, Flask-Login, Flask-WTF (CSRF), Dash 4.4 (`use_pages`), SQLite, Dash MCP (scope A déjà livré).

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `from src.api import tokens_db`).
- Copie UI en français ; libellé de section exact : **« Connecteur MCP »**.
- Lancer les tests avec **`uv run pytest`** (l'activation venv via Bash n'est pas fiable ici).
- Avant tout `git add`/`commit`, exécuter **`pre-commit`** (ruff + prettier) ; si des fichiers sont reformatés, les ré-ajouter avant de committer.
- Chaque tâche ne lance QUE le fichier de test qui la concerne. Le `uv run pytest` complet (sans chemin) est réservé à la dernière tâche.
- Jetons : préfixe `colibre_`, SHA-256 stocké (jamais le clair), clair affiché **une seule fois**.
- `kind` ∈ {`'api'`, `'mcp'`}, défaut `'api'`. Les jetons CLI existants restent `'api'`.
- Garde `/_mcp` : **401** (jeton absent/invalide/révoqué/`kind≠'mcp'`) avec en-tête `WWW-Authenticate: Bearer realm="colibre-mcp"` ; **403** (jeton `mcp` valide mais `user_id` nul ou abonnement inactif).
- Vérification d'abonnement = `TOUS_ABONNES or has_active_subscription(user_id)` (même sémantique que le reste de l'app).
- Migrations : convention `NNNN_description`, la prochaine est **`0007`** (la dernière est `0006_create_admin_actions`).
- `DASH_MCP_ENABLED` reste `false` par défaut ; ne pas le forcer dans le code ni dans les tests.

## File Structure

| Fichier                                     | Rôle                                                                           | Tâche |
| ------------------------------------------- | ------------------------------------------------------------------------------ | ----- |
| `src/api/tokens_db.py` (modif)              | Colonne `kind`, `create_token(kind=)`, `list_user_tokens`, `revoke_user_token` | 1     |
| `src/migrations.py` (modif)                 | Migration `0007` ajoute `kind` aux DB existantes                               | 2     |
| `src/api/__init__.py` (modif)               | `init_api` initialise le schéma `api_tokens` au démarrage                      | 2     |
| `src/mcp/auth.py` (créer)                   | Garde `before_request` sur `/_mcp`                                             | 3     |
| `src/app.py` (modif)                        | Exemption CSRF `/_mcp` + `init_mcp_auth`                                       | 4     |
| `src/api/auth.py` (modif)                   | `require_token` refuse `kind='mcp'` ; retire le `print` de debug               | 5     |
| `src/mcp/account.py` (créer)                | Blueprint Flask : POST création / révocation de jetons                         | 6     |
| `src/pages/compte/mcp.py` (créer)           | Page Dash « Connecteur MCP » (liste, formulaire, instructions clients)         | 7     |
| `src/pages/_compte_shell.py` (modif)        | Entrée de section « Connecteur MCP »                                           | 7     |
| `.template.env`, `CHANGELOG.md` (modif)     | Doc config + changelog                                                         | 8     |
| `tests/api/test_tokens_db.py` (modif)       | Tests data layer                                                               | 1     |
| `tests/api/test_migrations.py` (créer)      | Test migration 0007                                                            | 2     |
| `tests/api/test_init_api_schema.py` (créer) | Test init schema au démarrage                                                  | 2     |
| `tests/mcp/test_auth.py` (créer)            | Tests du garde `/_mcp`                                                         | 3     |
| `tests/mcp/test_app_wiring.py` (créer)      | Test intégration app (CSRF + garde câblés)                                     | 4     |
| `tests/api/test_auth.py` (modif)            | Tests refus `kind='mcp'` côté REST                                             | 5     |
| `tests/mcp/test_account_routes.py` (créer)  | Tests blueprint création/révocation                                            | 6     |
| `tests/mcp/test_account_page.py` (créer)    | Tests page compte                                                              | 7     |

---

### Task 1: Couche données `api_tokens` — colonne `kind` + fonctions par utilisateur

**Files:**

- Modify: `src/api/tokens_db.py`
- Test: `tests/api/test_tokens_db.py`

**Interfaces:**

- Produces:

  - `create_token(db_path, label, user_id=None, kind='api') -> tuple[str, int]`
  - `list_user_tokens(db_path, user_id, kind='mcp') -> list[dict]`
  - `revoke_user_token(db_path, token_id, user_id) -> bool`
  - `api_tokens` a une colonne `kind TEXT NOT NULL DEFAULT 'api'`

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/api/test_tokens_db.py` :

```python
def test_create_token_defaults_to_api_kind(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row["kind"] == "api"


def test_create_token_with_mcp_kind(temp_db):
    token, _ = tokens_db.create_token(temp_db, "x", user_id=7, kind="mcp")
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row["kind"] == "mcp"
    assert row["user_id"] == 7


def test_list_user_tokens_filters_by_user_and_kind(temp_db):
    tokens_db.create_token(temp_db, "mcp-u1", user_id=1, kind="mcp")
    tokens_db.create_token(temp_db, "api-u1", user_id=1, kind="api")
    tokens_db.create_token(temp_db, "mcp-u2", user_id=2, kind="mcp")
    rows = tokens_db.list_user_tokens(temp_db, 1, "mcp")
    assert [r["label"] for r in rows] == ["mcp-u1"]


def test_revoke_user_token_revokes_own(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    assert tokens_db.revoke_user_token(temp_db, token_id, 1) is True
    assert tokens_db.get_token_by_plaintext(temp_db, token)["revoked_at"] is not None


def test_revoke_user_token_refuses_other_owner(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    assert tokens_db.revoke_user_token(temp_db, token_id, 999) is False
    assert tokens_db.get_token_by_plaintext(temp_db, token)["revoked_at"] is None


def test_revoke_user_token_already_revoked_returns_false(temp_db):
    _, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    assert tokens_db.revoke_user_token(temp_db, token_id, 1) is True
    assert tokens_db.revoke_user_token(temp_db, token_id, 1) is False
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/api/test_tokens_db.py -v`
Expected: FAIL (`kind` inconnu / `list_user_tokens`, `revoke_user_token` non définis).

- [ ] **Step 3: Implémenter**

Dans `src/api/tokens_db.py` :

1. Ajouter `kind` à `SCHEMA` (après `count_total`, avant `revoked_at` ou en fin — l'ordre importe peu) :

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS api_tokens (
    id           INTEGER PRIMARY KEY,
    token_hash   TEXT NOT NULL UNIQUE,
    label        TEXT NOT NULL,
    user_id      INTEGER,
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    count_total  INTEGER NOT NULL DEFAULT 0,
    revoked_at   TEXT,
    kind         TEXT NOT NULL DEFAULT 'api'
);
CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
"""
```

2. Remplacer `create_token` :

```python
def create_token(
    db_path, label: str, user_id: int | None = None, kind: str = "api"
) -> tuple[str, int]:
    token = TOKEN_PREFIX + secrets.token_hex(32)
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO api_tokens (token_hash, label, user_id, kind, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (_hash(token), label, user_id, kind, _utcnow_iso()),
        )
        conn.commit()
        return token, cur.lastrowid
```

3. Ajouter, après `list_tokens` :

```python
def list_user_tokens(db_path, user_id: int, kind: str = "mcp") -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM api_tokens WHERE user_id = ? AND kind = ? "
            "ORDER BY created_at DESC, id DESC",
            (user_id, kind),
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_user_token(db_path, token_id: int, user_id: int) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE api_tokens SET revoked_at = ? "
            "WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (_utcnow_iso(), token_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/api/test_tokens_db.py -v`
Expected: PASS (tous, dont les tests existants).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/api/tokens_db.py tests/api/test_tokens_db.py
git add src/api/tokens_db.py tests/api/test_tokens_db.py
git commit -m "feat(mcp): colonne kind + fonctions jetons par utilisateur (scope B #111)"
```

---

### Task 2: Migration `0007` + initialisation du schéma au démarrage

**Files:**

- Modify: `src/migrations.py`
- Modify: `src/api/__init__.py`
- Test: `tests/api/test_migrations.py` (créer), `tests/api/test_init_api_schema.py` (créer)

**Interfaces:**

- Consumes: `tokens_db.init_schema` (existant), `src.auth.db.get_conn` / `reset_conn_for_tests` (existants).
- Produces: sur toute DB (fraîche ou existante), `api_tokens.kind` existe après démarrage.

**Context:** Les jetons existants en prod n'ont pas `kind`. `init_api` (appelé ~L112 de `src/app.py`, AVANT `init_subscriptions`/`apply_pending` ~L129) doit garantir que `api_tokens` existe avant que la migration ne l'`ALTER`. La table `SCHEMA` d'une DB fraîche inclut déjà `kind` (Task 1) → l'`ALTER` lève alors _duplicate column name_, déjà toléré par `apply_pending()`.

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/api/test_migrations.py` :

```python
import sqlite3


def test_migration_0007_adds_kind_to_legacy_api_tokens(monkeypatch, tmp_path):
    from src import migrations
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()

    conn = auth_db.get_conn()
    conn.execute("DROP TABLE IF EXISTS api_tokens")
    # ancienne table SANS colonne kind
    conn.execute(
        "CREATE TABLE api_tokens ("
        "id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, "
        "label TEXT NOT NULL, user_id INTEGER, created_at TEXT NOT NULL, "
        "last_used_at TEXT, count_total INTEGER NOT NULL DEFAULT 0, revoked_at TEXT)"
    )
    conn.commit()

    migrations.apply_pending()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(api_tokens)").fetchall()]
    assert "kind" in cols

    # idempotent : un second passage ne lève pas
    migrations.apply_pending()
    auth_db.reset_conn_for_tests()
```

`tests/api/test_init_api_schema.py` :

```python
import sqlite3


def test_init_api_creates_api_tokens_table(monkeypatch, tmp_path):
    from flask import Flask

    from src.api import init_api, tracking

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    server = Flask(__name__)
    init_api(server)
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='api_tokens'"
            ).fetchall()
    finally:
        tracking.stop_worker()
    assert rows == [("api_tokens",)]
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/api/test_migrations.py tests/api/test_init_api_schema.py -v`
Expected: FAIL (`0007` absent → pas de `kind` ; `init_api` ne crée pas `api_tokens`).

- [ ] **Step 3: Implémenter**

Dans `src/migrations.py`, ajouter à la fin de la liste `_MIGRATIONS` (après `0006_create_admin_actions`) :

```python
    (
        "0007_add_kind_to_api_tokens",
        "ALTER TABLE api_tokens ADD COLUMN kind TEXT NOT NULL DEFAULT 'api'",
    ),
```

Dans `src/api/__init__.py`, fonction `init_api`, ajouter l'initialisation du schéma des jetons. Le module importe déjà `os` (en fin de fonction) et `routes`. Modifier ainsi :

```python
def init_api(server) -> None:
    """Enregistre le blueprint d'API privée sur le serveur Flask."""
    import os

    from src.api import tokens_db, tracking

    # Garantit que api_tokens existe avant que apply_pending (init_subscriptions,
    # plus tard) ne tente l'ALTER de la migration 0007.
    tokens_db.init_schema(os.environ["USERS_DB_PATH"])

    server.config.setdefault("API_TITLE", "colibre API")
    # ... (config inchangée) ...

    api = Api(server)
    api.register_blueprint(routes.bp)

    tracking.start_worker(os.environ["USERS_DB_PATH"])
```

(Retirer l'ancien bloc `import os` / `from src.api import tracking` en fin de fonction, désormais remontés.)

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/api/test_migrations.py tests/api/test_init_api_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/migrations.py src/api/__init__.py tests/api/test_migrations.py tests/api/test_init_api_schema.py
git add src/migrations.py src/api/__init__.py tests/api/test_migrations.py tests/api/test_init_api_schema.py
git commit -m "feat(mcp): migration 0007 kind + init schema jetons au démarrage (scope B #111)"
```

---

### Task 3: Garde `/_mcp` — `src/mcp/auth.py`

**Files:**

- Create: `src/mcp/auth.py`
- Test: `tests/mcp/test_auth.py` (créer)

**Interfaces:**

- Consumes: `tokens_db.get_token_by_plaintext`, `tokens_db.increment_usage`, `has_active_subscription`, `TOUS_ABONNES`.
- Produces: `init_mcp_auth(server: Flask) -> None` (enregistre un `before_request`).

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/mcp/test_auth.py` :

```python
import pytest
from flask import Flask


@pytest.fixture
def mcp_app(monkeypatch, tmp_path):
    from src.api import tokens_db
    from src.auth import db as auth_db
    from src.mcp.auth import init_mcp_auth
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()
    tokens_db.init_schema(db_path)

    app = Flask(__name__)

    @app.route("/_mcp", methods=["GET", "POST"])
    def _mcp():
        return "ok", 200

    init_mcp_auth(app)
    yield app, db_path
    auth_db.reset_conn_for_tests()


def _subscribed_uid():
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    uid = auth_db.create_user("mcp@ex.fr", "hash")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")
    return uid


def test_missing_header_401_with_challenge(mcp_app):
    app, _ = mcp_app
    resp = app.test_client().post("/_mcp")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == 'Bearer realm="colibre-mcp"'


def test_empty_bearer_401(mcp_app):
    app, _ = mcp_app
    resp = app.test_client().post("/_mcp", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401


def test_unknown_token_401(mcp_app):
    app, _ = mcp_app
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": "Bearer colibre_unknown"}
    )
    assert resp.status_code == 401


def test_revoked_mcp_token_401(mcp_app):
    from src.api import tokens_db

    app, db_path = mcp_app
    uid = _subscribed_uid()
    token, tid = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    tokens_db.revoke_user_token(db_path, tid, uid)
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


def test_api_kind_token_rejected_401(mcp_app):
    from src.api import tokens_db

    app, db_path = mcp_app
    uid = _subscribed_uid()
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="api")
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


def test_mcp_token_without_user_403(mcp_app):
    from src.api import tokens_db

    app, db_path = mcp_app
    token, _ = tokens_db.create_token(db_path, "x", user_id=None, kind="mcp")
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


def test_mcp_token_no_active_subscription_403(mcp_app):
    from src.api import tokens_db
    from src.auth import db as auth_db

    app, db_path = mcp_app
    uid = auth_db.create_user("nosub@ex.fr", "hash")  # aucun abonnement
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


def test_mcp_token_active_subscription_passes_and_increments(mcp_app):
    from src.api import tokens_db

    app, db_path = mcp_app
    uid = _subscribed_uid()
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert tokens_db.get_token_by_plaintext(db_path, token)["count_total"] == 1


def test_tous_abonnes_bypasses_subscription(mcp_app, monkeypatch):
    from src.api import tokens_db
    from src.auth import db as auth_db

    monkeypatch.setattr("src.mcp.auth.TOUS_ABONNES", True)
    app, db_path = mcp_app
    uid = auth_db.create_user("nosub2@ex.fr", "hash")
    token, _ = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")
    resp = app.test_client().post(
        "/_mcp", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/mcp/test_auth.py -v`
Expected: FAIL (`src.mcp.auth` n'existe pas).

- [ ] **Step 3: Implémenter**

`src/mcp/auth.py` :

```python
import os

from flask import Flask, jsonify, request

from src.api import tokens_db
from src.subscriptions.db import has_active_subscription
from src.utils import TOUS_ABONNES


def _unauthorized():
    resp = jsonify(
        {"error": "unauthorized", "message": "Jeton MCP absent ou invalide."}
    )
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Bearer realm="colibre-mcp"'
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


def _authenticate_mcp():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return _unauthorized()
    token = header[len("Bearer ") :].strip()
    if not token:
        return _unauthorized()

    db_path = os.environ["USERS_DB_PATH"]
    row = tokens_db.get_token_by_plaintext(db_path, token)
    if row is None or row["revoked_at"] is not None or row["kind"] != "mcp":
        return _unauthorized()

    user_id = row["user_id"]
    if user_id is None:
        return _forbidden()
    if not (TOUS_ABONNES or has_active_subscription(user_id)):
        return _forbidden()

    tokens_db.increment_usage(db_path, row["id"])
    return None


def init_mcp_auth(server: Flask) -> None:
    """Enregistre le garde d'authentification du serveur MCP (/_mcp)."""

    @server.before_request
    def _guard_mcp():
        if request.path == "/_mcp" or request.path.startswith("/_mcp/"):
            return _authenticate_mcp()
        return None
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/mcp/test_auth.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/auth.py tests/mcp/test_auth.py
git add src/mcp/auth.py tests/mcp/test_auth.py
git commit -m "feat(mcp): garde d'abonnement sur /_mcp (scope B #111)"
```

---

### Task 4: Câblage dans `src/app.py` (exemption CSRF + `init_mcp_auth`)

**Files:**

- Modify: `src/app.py`
- Test: `tests/mcp/test_app_wiring.py` (créer)

**Interfaces:**

- Consumes: `init_mcp_auth` (Task 3).

**Context:** `/_mcp` reçoit des POST JSON-RPC externes sans jeton CSRF → doit être exempté comme `/_dash`/`/_reload`. Le garde n'est câblé que quand `DASH_MCP_ENABLED=true`. Le test importe l'app avec ce flag pour vérifier que POST `/_mcp` sans jeton renvoie **401** (garde) et non **400/403 CSRF** — preuve que l'exemption ET le garde sont câblés.

- [ ] **Step 1: Écrire le test qui échoue**

`tests/mcp/test_app_wiring.py` :

```python
import importlib


def test_mcp_endpoint_guarded_and_csrf_exempt(monkeypatch, tmp_path):
    # DB éphémère + secrets requis par init_auth/init_subscriptions.
    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.test.sqlite"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("DASH_MCP_ENABLED", "true")

    from src.auth import db as auth_db

    auth_db.reset_conn_for_tests()

    import src.app as app_module

    app_module = importlib.reload(app_module)
    client = app_module.app.server.test_client()

    # Pas de jeton : le garde renvoie 401 (et NON une erreur CSRF 400/403),
    # ce qui prouve exemption CSRF + garde câblés sur /_mcp.
    resp = client.post("/_mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == 'Bearer realm="colibre-mcp"'

    auth_db.reset_conn_for_tests()
```

> Note implémenteur : si `importlib.reload(src.app)` pose problème d'effets de bord (double enregistrement de pages Dash), remplacer par un import direct protégé — mais l'app est conçue pour un import unique ; le `reload` isolé dans ce test suffit. Si le reload échoue pour une raison d'environnement (ex. `use_pages` duplication), documenter le blocage (NEEDS_CONTEXT) plutôt que de contourner en désactivant le garde.

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/mcp/test_app_wiring.py -v`
Expected: FAIL (sans câblage, POST `/_mcp` → 404/erreur CSRF, pas 401 avec le challenge).

- [ ] **Step 3: Implémenter**

Dans `src/app.py` :

1. Étendre la boucle d'exemption CSRF (actuellement `/_dash` / `/_reload`) :

```python
if _auth_csrf is not None:
    for _rule in app.server.url_map.iter_rules():
        if (
            _rule.rule.startswith("/_dash")
            or _rule.rule.startswith("/_reload")
            or _rule.rule.startswith("/_mcp")
        ):
            _vf = app.server.view_functions.get(_rule.endpoint)
            if _vf is not None:
                _auth_csrf.exempt(_vf)
```

> Attention à l'ordre : les routes `/_mcp` ne sont enregistrées qu'après `configure_mcp_server(...)`. La boucle d'exemption actuelle s'exécute AVANT le bloc `if _mcp_enabled:`. **Déplacer l'appel à l'exemption CSRF après le bloc MCP**, ou exempter `/_mcp` dans une seconde passe. Solution retenue : dans le bloc `if _mcp_enabled:`, après `configure_mcp_server(...)` et l'import des tools, ré-itérer l'`url_map` pour exempter `/_mcp` puis appeler `init_mcp_auth`.

2. Modifier le bloc `if _mcp_enabled:` :

```python
if _mcp_enabled:
    from dash.mcp import configure_mcp_server  # noqa: E402

    configure_mcp_server(
        include_layout=False,
        include_callbacks=False,
        include_pages=False,
        include_clientside_callbacks=False,
    )
    import src.mcp.tools  # noqa: E402,F401  # l'import enregistre les @mcp_enabled

    # Les routes /_mcp existent maintenant : exempter du CSRF (POST JSON-RPC
    # externe sans jeton) puis brancher le garde d'abonnement.
    from src.mcp.auth import init_mcp_auth  # noqa: E402

    if _auth_csrf is not None:
        for _rule in app.server.url_map.iter_rules():
            if _rule.rule.startswith("/_mcp"):
                _vf = app.server.view_functions.get(_rule.endpoint)
                if _vf is not None:
                    _auth_csrf.exempt(_vf)

    init_mcp_auth(app.server)
```

(La boucle d'exemption existante en haut peut garder uniquement `/_dash` / `/_reload` — ne pas y ajouter `/_mcp` puisque les routes n'existent pas encore à ce point.)

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/mcp/test_app_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/app.py tests/mcp/test_app_wiring.py
git add src/app.py tests/mcp/test_app_wiring.py
git commit -m "feat(mcp): câble le garde /_mcp + exemption CSRF dans l'app (scope B #111)"
```

---

### Task 5: L'API REST refuse les jetons `kind='mcp'`

**Files:**

- Modify: `src/api/auth.py`
- Test: `tests/api/test_auth.py`

**Context:** Jetons dédiés : un jeton `mcp` ne doit pas ouvrir `/api/v1`. Les jetons `api` (tous les jetons CLI existants) restent acceptés → comportement REST inchangé. On en profite pour retirer le `print(API_AUTH_DISABLED)` de debug (ligne 19).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/api/test_auth.py` :

```python
def test_mcp_kind_token_rejected_by_rest_api(temp_db):
    token, _ = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "invalid_token"


def test_api_kind_token_accepted_by_rest_api(temp_db):
    token, _ = tokens_db.create_token(temp_db, "x", kind="api")
    app = _make_app()
    resp = app.test_client().get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/api/test_auth.py -v`
Expected: FAIL (`test_mcp_kind_token_rejected_by_rest_api` : le jeton mcp est accepté → 200).

- [ ] **Step 3: Implémenter**

Dans `src/api/auth.py`, remplacer le corps de `wrapper` (retirer le `print`, ajouter le refus `mcp`) :

```python
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not API_AUTH_DISABLED:
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
            if row["kind"] == "mcp":
                # jeton dédié MCP : non valable sur l'API REST
                _abort_401("invalid_token")
            g.token_id = row["id"]
        return fn(*args, **kwargs)

    return wrapper
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/api/test_auth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/api/auth.py tests/api/test_auth.py
git add src/api/auth.py tests/api/test_auth.py
git commit -m "feat(mcp): l'API REST refuse les jetons kind=mcp (scope B #111)"
```

---

### Task 6: Blueprint de gestion des jetons — `src/mcp/account.py`

**Files:**

- Create: `src/mcp/account.py`
- Test: `tests/mcp/test_account_routes.py` (créer)

**Interfaces:**

- Consumes: `tokens_db.create_token`, `tokens_db.revoke_user_token`, `current_user`, la vérif d'abonnement.
- Produces: `mcp_account_bp` (Blueprint Flask) avec :

  - `POST /compte/mcp/creer` (champ form `label`) → crée un jeton `kind='mcp'`, stocke le clair dans `session["mcp_new_token"]`, redirige `/compte/mcp`.
  - `POST /compte/mcp/revoquer/<int:token_id>` → `revoke_user_token`, redirige `/compte/mcp`.
  - Les deux exigent authentification + abonnement actif (sinon redirection).

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/mcp/test_account_routes.py` :

```python
import pytest
from flask import Flask


@pytest.fixture
def account_client(monkeypatch, tmp_path):
    from src.api import tokens_db
    from src.auth import db as auth_db
    from src.auth.setup import init_auth
    from src.mcp.account import mcp_account_bp
    from src.subscriptions import db as sub_db

    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.test.sqlite"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    auth_db.reset_conn_for_tests()

    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    init_auth(app)  # login manager + CSRF (désactivé) + schéma auth
    sub_db.init_schema()
    db_path = tmp_path / "users.test.sqlite"
    tokens_db.init_schema(db_path)
    app.register_blueprint(mcp_account_bp)

    yield app, db_path
    auth_db.reset_conn_for_tests()


def _login(app, uid):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True
    return client


def _subscribed_uid():
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    uid = auth_db.create_user("sub@ex.fr", "hash")
    _, sub_id = sub_db.create_pending(uid, "colibre-1", "simple")
    sub_db.set_status(sub_id, "active")
    return uid


def test_creer_generates_mcp_token_for_subscriber(account_client):
    from src.api import tokens_db

    app, db_path = account_client
    uid = _subscribed_uid()
    client = _login(app, uid)

    resp = client.post("/compte/mcp/creer", data={"label": "Claude portable"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/compte/mcp")

    with client.session_transaction() as sess:
        assert sess.get("mcp_new_token", "").startswith("colibre_")

    rows = tokens_db.list_user_tokens(db_path, uid, "mcp")
    assert [r["label"] for r in rows] == ["Claude portable"]
    assert rows[0]["kind"] == "mcp"
    assert rows[0]["user_id"] == uid


def test_revoquer_own_token(account_client):
    from src.api import tokens_db

    app, db_path = account_client
    uid = _subscribed_uid()
    client = _login(app, uid)
    token, tid = tokens_db.create_token(db_path, "x", user_id=uid, kind="mcp")

    resp = client.post(f"/compte/mcp/revoquer/{tid}")
    assert resp.status_code == 302
    assert tokens_db.get_token_by_plaintext(db_path, token)["revoked_at"] is not None


def test_revoquer_other_users_token_is_noop(account_client):
    from src.api import tokens_db

    app, db_path = account_client
    uid = _subscribed_uid()
    client = _login(app, uid)
    other_token, other_id = tokens_db.create_token(
        db_path, "y", user_id=99999, kind="mcp"
    )

    resp = client.post(f"/compte/mcp/revoquer/{other_id}")
    assert resp.status_code == 302
    assert tokens_db.get_token_by_plaintext(db_path, other_token)["revoked_at"] is None


def test_creer_blocked_without_subscription(account_client):
    from src.api import tokens_db
    from src.auth import db as auth_db

    app, db_path = account_client
    uid = auth_db.create_user("nosub@ex.fr", "hash")  # pas d'abonnement
    client = _login(app, uid)

    resp = client.post("/compte/mcp/creer", data={"label": "x"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/compte/abonnement")
    assert tokens_db.list_user_tokens(db_path, uid, "mcp") == []


def test_creer_blocked_when_anonymous(account_client):
    app, db_path = account_client
    resp = app.test_client().post("/compte/mcp/creer", data={"label": "x"})
    assert resp.status_code == 302
    assert "/connexion" in resp.headers["Location"]
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/mcp/test_account_routes.py -v`
Expected: FAIL (`src.mcp.account` n'existe pas).

- [ ] **Step 3: Implémenter**

`src/mcp/account.py` :

```python
import os

from flask import Blueprint, redirect, request, session
from flask_login import current_user

from src.api import tokens_db

mcp_account_bp = Blueprint("mcp_account", __name__)

_LABEL_MAX = 100


def _has_active_subscription() -> bool:
    # Réutilise la vérification canonique (gère TOUS_ABONNES).
    from src.pages._compte_shell import current_user_has_subscription

    return current_user_has_subscription()


def _guard():
    """Renvoie une redirection si l'accès est refusé, sinon None."""
    if not current_user.is_authenticated:
        return redirect("/connexion?next=/compte/mcp")
    if not _has_active_subscription():
        return redirect("/compte/abonnement")
    return None


@mcp_account_bp.route("/compte/mcp/creer", methods=["POST"])
def creer():
    denied = _guard()
    if denied is not None:
        return denied
    label = (request.form.get("label") or "").strip()[:_LABEL_MAX] or "Sans nom"
    token, _ = tokens_db.create_token(
        os.environ["USERS_DB_PATH"], label, user_id=current_user.id, kind="mcp"
    )
    session["mcp_new_token"] = token
    return redirect("/compte/mcp")


@mcp_account_bp.route("/compte/mcp/revoquer/<int:token_id>", methods=["POST"])
def revoquer(token_id):
    denied = _guard()
    if denied is not None:
        return denied
    tokens_db.revoke_user_token(
        os.environ["USERS_DB_PATH"], token_id, current_user.id
    )
    return redirect("/compte/mcp")
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/mcp/test_account_routes.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/mcp/account.py tests/mcp/test_account_routes.py
git add src/mcp/account.py tests/mcp/test_account_routes.py
git commit -m "feat(mcp): blueprint création/révocation de jetons MCP (scope B #111)"
```

---

### Task 7: Page compte « Connecteur MCP » + section + enregistrement blueprint

**Files:**

- Create: `src/pages/compte/mcp.py`
- Modify: `src/pages/_compte_shell.py` (entrée SECTIONS)
- Modify: `src/app.py` (enregistrer `mcp_account_bp`)
- Test: `tests/mcp/test_account_page.py` (créer)

**Interfaces:**

- Consumes: `account_shell`, `account_guard`, `tokens_db.list_user_tokens`, `mcp_account_bp`.

**Context:** Suit le patron des pages `compte/` (`register_page` + `layout()` gardé par `account_guard`, mutations via formulaires POST CSRF). Le jeton fraîchement créé est lu **une seule fois** depuis `session`. Les instructions clients couvrent Claude/Gemini/Mistral (jeton) et ChatGPT (caveat OAuth → B2). Si `DASH_MCP_ENABLED != "true"`, la page affiche un bandeau « bientôt disponible » et masque le formulaire (évite de proposer un connecteur inopérant en prod avant activation).

- [ ] **Step 1: Écrire les tests qui échouent**

`tests/mcp/test_account_page.py` :

```python
def test_section_connecteur_mcp_present():
    from src.pages._compte_shell import SECTIONS

    keys = {s["key"]: s for s in SECTIONS}
    assert "mcp" in keys
    assert keys["mcp"]["label"] == "Connecteur MCP"
    assert keys["mcp"]["href"] == "/compte/mcp"
    assert keys["mcp"]["require_subscription"] is True


def test_page_module_registers_and_builds_client_instructions():
    # importe l'app pour la découverte use_pages en contexte propre
    from src.app import app  # noqa: F401
    from src.pages.compte import mcp as mcp_page

    # helper pur : construit les 4 blocs d'instructions clients
    blocks = mcp_page.client_instructions("https://colibre.fr/_mcp", "colibre_TESTTOKEN")
    text = str(blocks)
    assert "colibre_TESTTOKEN" in text
    assert "https://colibre.fr/_mcp" in text
    for client_name in ("Claude", "Gemini", "Mistral", "ChatGPT"):
        assert client_name in text
    # caveat ChatGPT (OAuth / itération future)
    assert "OAuth" in text
```

> Note : `client_instructions(url, token)` est une fonction pure exposée par la page pour rester testable sans rendu Dash complet. `token` peut être un placeholder `<VOTRE_JETON>` quand aucun jeton frais n'est disponible.

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/mcp/test_account_page.py -v`
Expected: FAIL (section absente ; module page inexistant).

- [ ] **Step 3: Implémenter**

1. Dans `src/pages/_compte_shell.py`, insérer l'entrée dans `SECTIONS` **avant** l'entrée `abonnement` :

```python
    {
        "key": "mcp",
        "label": "Connecteur MCP",
        "href": "/compte/mcp",
        "require_subscription": True,
    },
```

2. Créer `src/pages/compte/mcp.py` :

```python
import os

import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask import session
from flask_login import current_user

from src.api import tokens_db
from src.pages._compte_shell import account_guard, account_shell

register_page(
    __name__,
    path="/compte/mcp",
    title="Connecteur MCP | colibre",
    name="Connecteur MCP",
    description="Connectez votre agent IA aux données colibre via le protocole MCP.",
)

MCP_ENABLED = os.getenv("DASH_MCP_ENABLED") == "true"
_TOKEN_PLACEHOLDER = "<VOTRE_JETON>"


def _mcp_url() -> str:
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    return f"{base}/_mcp" if base else "/_mcp"


def _csrf(index: str):
    return dcc.Input(
        type="hidden",
        id={"type": "csrf-input", "index": index},
        name="csrf_token",
    )


def client_instructions(url: str, token: str):
    """Construit les blocs d'instructions par client (fonction pure, testable)."""
    claude = f'claude mcp add colibre --transport http {url} --header "Authorization: Bearer {token}"'
    gemini = f'gemini mcp add --transport http --header "Authorization: Bearer {token}" colibre {url}'
    return dbc.Accordion(
        start_collapsed=True,
        always_open=False,
        children=[
            dbc.AccordionItem(
                title="Claude (Code / Desktop)",
                children=html.Pre(html.Code(claude)),
            ),
            dbc.AccordionItem(
                title="Gemini CLI",
                children=[
                    html.Pre(html.Code(gemini)),
                    html.P(
                        "Ou dans ~/.gemini/settings.json : un serveur mcpServers.colibre "
                        f'avec "httpUrl": "{url}" et "headers": '
                        f'{{"Authorization": "Bearer {token}"}}.'
                    ),
                ],
            ),
            dbc.AccordionItem(
                title="Mistral Le Chat",
                children=html.P(
                    "Dans les connecteurs MCP, ajoutez un serveur HTTP d'URL "
                    f"{url}, authentification « API Token », en-tête "
                    f"« Authorization » = « Bearer {token} »."
                ),
            ),
            dbc.AccordionItem(
                title="ChatGPT",
                children=[
                    html.P(
                        "L'app ChatGPT grand public exige le flux OAuth 2.1 et "
                        "n'accepte pas de jeton statique. En attendant le connecteur "
                        "OAuth (itération future), utilisez la voie développeur "
                        "(API / Agents SDK OpenAI), qui accepte un serveur MCP distant "
                        f"d'URL {url} avec l'en-tête « Authorization: Bearer {token} »."
                    ),
                ],
            ),
        ],
    )


def _token_row(row: dict):
    statut = "Révoqué" if row["revoked_at"] else "Actif"
    actions = []
    if not row["revoked_at"]:
        actions = [
            html.Form(
                method="POST",
                action=f"/compte/mcp/revoquer/{row['id']}",
                children=[
                    _csrf(f"revoke-{row['id']}"),
                    dbc.Button(
                        "Révoquer", type="submit", color="danger", size="sm", outline=True
                    ),
                ],
            )
        ]
    return html.Tr(
        [
            html.Td(row["label"]),
            html.Td(row["created_at"]),
            html.Td(row["last_used_at"] or "—"),
            html.Td(statut),
            html.Td(actions),
        ]
    )


def layout(**_):
    guard = account_guard("/compte/mcp", require_subscription=True)
    if guard is not None:
        return guard

    if not MCP_ENABLED:
        contenu = html.Div(
            [
                html.H2("Connecteur MCP"),
                dbc.Alert(
                    "Le connecteur MCP sera bientôt disponible. Revenez prochainement.",
                    color="info",
                ),
            ]
        )
        return account_shell("mcp", contenu)

    url = _mcp_url()
    new_token = session.pop("mcp_new_token", None)

    alerts = []
    if new_token:
        alerts.append(
            dbc.Alert(
                [
                    html.Strong("Votre nouveau jeton (copiez-le maintenant, "),
                    html.Strong("il ne sera plus affiché) :"),
                    html.Pre(html.Code(new_token)),
                ],
                color="success",
            )
        )

    tokens = tokens_db.list_user_tokens(
        os.environ["USERS_DB_PATH"], current_user.id, "mcp"
    )
    table = dbc.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Nom"),
                        html.Th("Créé le"),
                        html.Th("Dernière utilisation"),
                        html.Th("Statut"),
                        html.Th(""),
                    ]
                )
            ),
            html.Tbody([_token_row(dict(r)) for r in tokens]),
        ],
        striped=True,
        bordered=False,
        hover=True,
    ) if tokens else html.P("Aucun jeton pour le moment.")

    create_form = html.Form(
        method="POST",
        action="/compte/mcp/creer",
        className="mb-4",
        children=[
            _csrf("mcp-create"),
            dbc.Label("Nom du jeton (ex. « Claude sur mon portable »)"),
            dbc.Input(type="text", name="label", required=True, className="mb-2"),
            dbc.Button("Générer un jeton", type="submit", color="primary"),
        ],
    )

    snippet_token = new_token or _TOKEN_PLACEHOLDER
    contenu = html.Div(
        [
            html.H2("Connecteur MCP"),
            html.P(
                "Générez un jeton pour connecter votre agent IA (Claude, Gemini, "
                "Mistral…) aux données colibre via le protocole MCP. Le jeton vaut "
                "votre identité : gardez-le secret. Un abonnement actif est requis."
            ),
            *alerts,
            html.H4("Générer un jeton", className="mt-3"),
            create_form,
            html.H4("Mes jetons", className="mt-4"),
            table,
            html.H4("Connecter un client", className="mt-4"),
            html.P(f"URL du serveur MCP : {url}"),
            client_instructions(url, snippet_token),
        ]
    )
    return account_shell("mcp", contenu)
```

3. Dans `src/app.py`, enregistrer le blueprint (toujours actif, après `init_subscriptions` par exemple — les routes POST sont inoffensives même MCP désactivé) :

```python
from src.mcp.account import mcp_account_bp  # noqa: E402

app.server.register_blueprint(mcp_account_bp)
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/mcp/test_account_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/compte/mcp.py src/pages/_compte_shell.py src/app.py tests/mcp/test_account_page.py
git add src/pages/compte/mcp.py src/pages/_compte_shell.py src/app.py tests/mcp/test_account_page.py
git commit -m "feat(mcp): page compte Connecteur MCP + instructions clients (scope B #111)"
```

---

### Task 8: Documentation config + CHANGELOG + suite complète

**Files:**

- Modify: `.template.env`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: `.template.env`** — compléter la doc de `DASH_MCP_ENABLED`

Localiser la ligne `DASH_MCP_ENABLED=false` et remplacer son commentaire par :

```bash
# Active le serveur MCP (/_mcp) ET le connecteur d'abonné (scope B, #111).
# À true, l'accès à /_mcp exige un jeton MCP (généré dans /compte/mcp) lié à un
# abonnement actif. Laisser false tant que le connecteur n'est pas déployé.
# Déploiement recommandé : activer d'abord sur test.colibre.fr (branche dev).
DASH_MCP_ENABLED=false
```

- [ ] **Step 2: `CHANGELOG.md`** — ajouter sous `### 3.0.0 Fonctionnalités par abonnement`

Ajouter, sous la même rubrique que l'entrée MCP de scope A :

```markdown
- Connecteur MCP : les abonnés génèrent un jeton dans « Mon compte › Connecteur MCP » pour connecter leur agent IA (Claude, Gemini, Mistral) au serveur MCP colibre ; l'accès est conditionné à un abonnement actif ([#111](https://github.com/ColinMaudry/colibre/issues/111)).
```

(Adapter le style de puce/format à celui de l'entrée scope A voisine ; lire le fichier d'abord.)

- [ ] **Step 3: Lancer la suite complète**

Run: `uv run pytest`
Expected: PASS (tout vert, hormis skips connus). Corriger toute régression avant de committer.

- [ ] **Step 4: Commit**

```bash
pre-commit run --files .template.env CHANGELOG.md
git add .template.env CHANGELOG.md
git commit -m "docs(mcp): config DASH_MCP_ENABLED + changelog connecteur (scope B #111)"
```

---

## Self-Review (auteur du plan)

**Couverture spec :**

- Jeton dédié `kind` + réutilisation `api_tokens` → Task 1 ✅
- Migration + init schéma → Task 2 ✅
- Garde `/_mcp` (401/403, WWW-Authenticate, increment_usage, TOUS_ABONNES) → Task 3 ✅
- Câblage app + exemption CSRF → Task 4 ✅
- API REST refuse `mcp` → Task 5 ✅
- Génération/révocation self-service (anti-IDOR, affichage unique, sécurité serveur) → Tasks 6-7 ✅
- Page « Connecteur MCP », section compte gardée, instructions 4 clients + caveat ChatGPT → Task 7 ✅
- Config + changelog → Task 8 ✅
- Hors périmètre (OAuth/DCR/PKCE, rate-limiting, refonte REST) : non implémentés ✅

**Placeholders :** aucun TODO/TBD. `<VOTRE_JETON>` (Task 7) est un placeholder d'affichage UI intentionnel, injecté avec le vrai jeton quand il vient d'être créé.

**Cohérence des types :** `create_token(db_path, label, user_id=None, kind='api')`, `list_user_tokens(db_path, user_id, kind='mcp')`, `revoke_user_token(db_path, token_id, user_id) -> bool`, `init_mcp_auth(server)`, `mcp_account_bp`, `client_instructions(url, token)` — noms/paramètres identiques entre définition (Tasks 1/3/6/7) et usages.

**Note ordre CSRF (Task 4) :** l'exemption `/_mcp` DOIT s'exécuter après `configure_mcp_server` (routes créées à ce moment) — capturé explicitement dans l'implémentation.
