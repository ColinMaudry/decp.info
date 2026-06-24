# Connexion avec LinkedIn (OIDC) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre la création de compte / connexion via LinkedIn (OIDC) en parallèle de l'auth email+mot de passe existante.

**Architecture:** Authlib (intégration Flask) gère le flux OIDC LinkedIn. Deux routes (`/auth/linkedin`, `/auth/linkedin/callback`) s'ajoutent au blueprint `auth` existant. Une fonction `resolve_oauth_user` relie l'identité LinkedIn à un compte (existant par email, ou nouveau). Le schéma SQLite gagne une table `oauth_identities` et rend `password_hash` nullable.

**Tech Stack:** Flask, Flask-Login, Authlib, SQLite, Dash (pages), pytest.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `from src.auth import db`).
- Tests : `uv run pytest` (pas de `source .venv/bin/activate`).
- Provider unique : `linkedin`. Pas d'abstraction multi-provider.
- On ne stocke que l'email (pas de nom/photo).
- Liaison automatique par email (l'email LinkedIn est vérifié).
- Libellé du bouton : exactement « Connexion avec LinkedIn ».
- Couleur du bouton : fond `rgb(10, 102, 194)`, texte blanc.
- Discovery OIDC LinkedIn : `https://www.linkedin.com/oauth/.well-known/openid-configuration`.
- Scopes : `openid profile email`.
- URL de callback construite depuis `APP_BASE_URL` : `{APP_BASE_URL}/auth/linkedin/callback`.

---

### Task 1: Schéma DB — `password_hash` nullable + table `oauth_identities` + helpers

**Files:**

- Modify: `src/auth/db.py`
- Test: `tests/auth/test_oauth_db.py` (create)

**Interfaces:**

- Consumes: helpers existants `get_conn`, `init_schema`, `get_user_by_email`, `get_user_by_id`, `_now`.
- Produces:

  - `create_oauth_user(email: str) -> int` — crée un user `password_hash = NULL`, `email_verified = 1`, renvoie l'id.
  - `get_oauth_identity(provider: str, subject: str) -> sqlite3.Row | None`.
  - `link_oauth_identity(provider: str, subject: str, user_id: int) -> None`.
  - Schéma : `users.password_hash` nullable ; table `oauth_identities(provider, subject, user_id, created_at)` PK `(provider, subject)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/auth/test_oauth_db.py`:

```python
import sqlite3

import pytest

from src.auth import db


def test_oauth_identities_table_created(users_db_path):
    db.init_schema()
    tables = {
        r[0]
        for r in db.get_conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "oauth_identities" in tables


def test_password_hash_is_nullable_on_fresh_schema(users_db_path):
    db.init_schema()
    cols = {r["name"]: r for r in db.get_conn().execute("PRAGMA table_info(users)")}
    assert cols["password_hash"]["notnull"] == 0


def test_create_oauth_user(users_db_path):
    db.init_schema()
    uid = db.create_oauth_user("oauth@example.com")
    row = db.get_user_by_id(uid)
    assert row["email"] == "oauth@example.com"
    assert row["password_hash"] is None
    assert row["email_verified"] == 1


def test_link_and_get_oauth_identity(users_db_path):
    db.init_schema()
    uid = db.create_oauth_user("oauth@example.com")
    assert db.get_oauth_identity("linkedin", "sub-123") is None
    db.link_oauth_identity("linkedin", "sub-123", uid)
    row = db.get_oauth_identity("linkedin", "sub-123")
    assert row["user_id"] == uid


def test_oauth_identity_pk_prevents_duplicate(users_db_path):
    db.init_schema()
    uid = db.create_oauth_user("oauth@example.com")
    db.link_oauth_identity("linkedin", "sub-123", uid)
    with pytest.raises(sqlite3.IntegrityError):
        db.link_oauth_identity("linkedin", "sub-123", uid)


def test_migration_makes_legacy_password_hash_nullable(users_db_path):
    # Simule un schéma hérité où password_hash est NOT NULL.
    conn = db.get_conn()
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email_verified INTEGER NOT NULL DEFAULT 0,
            pending_email TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE email_verification_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    now = db._now()
    conn.execute(
        "INSERT INTO users (id, email, password_hash, email_verified, created_at, updated_at)"
        " VALUES (1, 'legacy@example.com', 'hash', 1, ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO email_verification_tokens (token_hash, user_id, expires_at, created_at)"
        " VALUES ('tok', 1, ?, ?)",
        (now, now),
    )

    db.init_schema()  # déclenche _migrate

    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(users)")}
    assert cols["password_hash"]["notnull"] == 0
    # Données préservées, pas de cascade-delete déclenchée pendant la reconstruction.
    assert db.get_user_by_id(1)["email"] == "legacy@example.com"
    assert conn.execute(
        "SELECT COUNT(*) FROM email_verification_tokens"
    ).fetchone()[0] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/auth/test_oauth_db.py -v`
Expected: FAIL (`oauth_identities` absent, `create_oauth_user` non défini, `password_hash` encore `notnull=1`).

- [ ] **Step 3: Update schema and add helpers in `src/auth/db.py`**

In `USERS_SCHEMA`, change the `password_hash` line to nullable and append the new table. The `users` CREATE becomes:

```python
USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    pending_email TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS oauth_identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (provider, subject),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""
```

Replace `_migrate` with a version that also drops the `NOT NULL` on legacy DBs, and add the rebuild helper:

```python
def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(users)")}
    if "pending_email" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN pending_email TEXT")
        cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(users)")}
    if cols.get("password_hash") and cols["password_hash"]["notnull"] == 1:
        _rebuild_users_password_nullable(conn)


def _rebuild_users_password_nullable(conn: sqlite3.Connection) -> None:
    # SQLite ne peut pas retirer un NOT NULL via ALTER : on reconstruit la table.
    # foreign_keys OFF pour éviter le cascade-delete pendant le DROP.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT,
                email_verified INTEGER NOT NULL DEFAULT 0,
                pending_email TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO users_new (id, email, password_hash, email_verified, "
            "pending_email, created_at, updated_at) "
            "SELECT id, email, password_hash, email_verified, pending_email, "
            "created_at, updated_at FROM users"
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_new RENAME TO users")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
```

Append the new helpers at the end of `src/auth/db.py`:

```python
def create_oauth_user(email: str) -> int:
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, email_verified, created_at, updated_at) "
        "VALUES (?, NULL, 1, ?, ?)",
        (email.lower(), now, now),
    )
    return cur.lastrowid


def get_oauth_identity(provider: str, subject: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM oauth_identities WHERE provider = ? AND subject = ?",
            (provider, subject),
        )
        .fetchone()
    )


def link_oauth_identity(provider: str, subject: str, user_id: int) -> None:
    get_conn().execute(
        "INSERT INTO oauth_identities (provider, subject, user_id, created_at) "
        "VALUES (?, ?, ?, ?)",
        (provider, subject, user_id, _now()),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_oauth_db.py tests/auth/test_db.py -v`
Expected: PASS (new tests + existing db tests still green).

- [ ] **Step 5: Commit**

```bash
git add src/auth/db.py tests/auth/test_oauth_db.py
git commit -m "feat(auth): oauth_identities table + password_hash nullable

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Résolution de compte `resolve_oauth_user`

**Files:**

- Modify: `src/auth/routes.py`
- Test: `tests/auth/test_oauth_resolve.py` (create)

**Interfaces:**

- Consumes (from Task 1): `db.get_oauth_identity`, `db.link_oauth_identity`, `db.create_oauth_user`, plus existants `db.get_user_by_email`, `db.get_user_by_id`, `db.set_email_verified`.
- Produces:
  - `resolve_oauth_user(provider: str, subject: str, email: str, email_verified: bool) -> User` — renvoie l'utilisateur (existant lié, lié par email, ou nouvellement créé).

Placée dans `routes.py` (et non `db.py`) car elle construit un `User`, ce qui éviterait un import circulaire `db` → `models`.

- [ ] **Step 1: Write the failing tests**

Create `tests/auth/test_oauth_resolve.py`:

```python
from werkzeug.security import generate_password_hash

from src.auth import db
from src.auth.models import User
from src.auth.routes import resolve_oauth_user


def test_creates_new_user_when_unknown(users_db_path):
    db.init_schema()
    user = resolve_oauth_user("linkedin", "sub-1", "new@example.com", True)
    assert isinstance(user, User)
    row = db.get_user_by_id(int(user.get_id()))
    assert row["email"] == "new@example.com"
    assert row["password_hash"] is None
    assert row["email_verified"] == 1
    assert db.get_oauth_identity("linkedin", "sub-1")["user_id"] == row["id"]


def test_links_to_existing_email_account(users_db_path):
    db.init_schema()
    uid = db.create_user("alice@example.com", generate_password_hash("password12"))
    db.set_email_verified(uid)

    user = resolve_oauth_user("linkedin", "sub-2", "alice@example.com", True)
    assert int(user.get_id()) == uid
    assert db.get_oauth_identity("linkedin", "sub-2")["user_id"] == uid
    # Le compte garde son mot de passe.
    assert db.get_user_by_id(uid)["password_hash"] is not None


def test_links_and_verifies_unverified_existing_account(users_db_path):
    db.init_schema()
    uid = db.create_user("bob@example.com", generate_password_hash("password12"))
    assert db.get_user_by_id(uid)["email_verified"] == 0

    resolve_oauth_user("linkedin", "sub-3", "bob@example.com", True)
    assert db.get_user_by_id(uid)["email_verified"] == 1


def test_returns_same_user_for_known_identity(users_db_path):
    db.init_schema()
    first = resolve_oauth_user("linkedin", "sub-4", "carol@example.com", True)
    second = resolve_oauth_user("linkedin", "sub-4", "carol@example.com", True)
    assert first.get_id() == second.get_id()
    # Pas de doublon d'identité.
    count = db.get_conn().execute(
        "SELECT COUNT(*) FROM oauth_identities WHERE provider='linkedin' AND subject='sub-4'"
    ).fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/auth/test_oauth_resolve.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_oauth_user'`.

- [ ] **Step 3: Implement `resolve_oauth_user` in `src/auth/routes.py`**

Add after the imports / `_DUMMY_HASH` definition:

```python
def resolve_oauth_user(
    provider: str, subject: str, email: str, email_verified: bool
) -> User:
    identity = db.get_oauth_identity(provider, subject)
    if identity is not None:
        return User(db.get_user_by_id(identity["user_id"]))

    row = db.get_user_by_email(email)
    if row is not None:
        db.link_oauth_identity(provider, subject, row["id"])
        if email_verified and not row["email_verified"]:
            db.set_email_verified(row["id"])
        return User(db.get_user_by_id(row["id"]))

    user_id = db.create_oauth_user(email)
    db.link_oauth_identity(provider, subject, user_id)
    return User(db.get_user_by_id(user_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_oauth_resolve.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/auth/routes.py tests/auth/test_oauth_resolve.py
git commit -m "feat(auth): resolve_oauth_user (liaison/création de compte OIDC)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Initialisation Authlib + dépendance + variables d'env

**Files:**

- Create: `src/auth/oauth.py`
- Modify: `src/auth/setup.py`
- Modify: `pyproject.toml`
- Modify: `.template.env`
- Modify: `tests/auth/conftest.py`

**Interfaces:**

- Produces:
  - `src.auth.oauth.oauth` — instance `authlib.integrations.flask_client.OAuth` (registre).
  - `src.auth.oauth.init_oauth(app: Flask) -> None` — init + register du provider `linkedin`.
  - `init_auth` appelle `init_oauth(app)`.
- Consumes: env `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add `"authlib"` to the `dependencies` list (alphabetical-ish, near `email-validator`):

```toml
  "email-validator",
  "authlib",
```

Then install it:

Run: `uv pip install authlib`
Expected: installs Authlib successfully.

- [ ] **Step 2: Create `src/auth/oauth.py`**

```python
import os

from authlib.integrations.flask_client import OAuth
from flask import Flask

LINKEDIN_DISCOVERY_URL = (
    "https://www.linkedin.com/oauth/.well-known/openid-configuration"
)

oauth = OAuth()


def init_oauth(app: Flask) -> None:
    oauth.init_app(app)
    oauth.register(
        name="linkedin",
        client_id=os.getenv("LINKEDIN_CLIENT_ID"),
        client_secret=os.getenv("LINKEDIN_CLIENT_SECRET"),
        server_metadata_url=LINKEDIN_DISCOVERY_URL,
        client_kwargs={"scope": "openid profile email"},
    )
```

- [ ] **Step 3: Wire it into `init_auth`**

In `src/auth/setup.py`, after `app.register_blueprint(auth_bp)` and before/after the CSRF init, add the import and call. Add near the other `from src.auth...` imports at top:

```python
from src.auth.oauth import init_oauth
```

And inside `init_auth`, after `app.register_blueprint(auth_bp)`:

```python
    init_oauth(app)
```

Also warn if LinkedIn isn't configured — append to the bottom of `init_auth`, next to the existing BREVO warning:

```python
    if not os.getenv("LINKEDIN_CLIENT_ID"):
        logger.warning(
            "LINKEDIN_CLIENT_ID non défini : la connexion LinkedIn échouera. "
            "Définissez LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET dans .env."
        )
```

- [ ] **Step 4: Add env template entries**

In `.template.env`, under the `# Comptes utilisateurs` section, add:

```bash
# Connexion LinkedIn (OpenID Connect) — créer une app sur le LinkedIn Developer Portal,
# activer "Sign In with LinkedIn using OpenID Connect", déclarer le redirect URI
# {APP_BASE_URL}/auth/linkedin/callback
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
```

- [ ] **Step 5: Set test env so `init_auth` can register the provider**

In `tests/auth/conftest.py`, in the `app` fixture, set dummy LinkedIn credentials before `init_auth(app)`:

```python
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    app = Flask(__name__)
```

- [ ] **Step 6: Verify the app still boots under tests**

Run: `uv run pytest tests/auth/test_app_integration.py -v`
Expected: PASS (registering the provider is lazy — no network call at init).

- [ ] **Step 7: Commit**

```bash
git add src/auth/oauth.py src/auth/setup.py pyproject.toml .template.env tests/auth/conftest.py
git commit -m "feat(auth): init Authlib + provider LinkedIn (config env)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Routes `/auth/linkedin` et `/auth/linkedin/callback`

**Files:**

- Modify: `src/auth/routes.py`
- Test: `tests/auth/test_oauth_routes.py` (create)

**Interfaces:**

- Consumes: `resolve_oauth_user` (Task 2), `oauth` (Task 3), `safe_next`, `login_user`, `session`.
- Produces: routes `GET /auth/linkedin`, `GET /auth/linkedin/callback`. Redirections d'erreur vers `/connexion?error=oauth_cancelled|oauth_failed`.

- [ ] **Step 1: Write the failing tests**

Create `tests/auth/test_oauth_routes.py`:

```python
import pytest

from src.auth import db
from src.auth import oauth as oauth_module


@pytest.fixture
def fake_userinfo(monkeypatch):
    """Patche authorize_access_token pour éviter tout appel réseau."""

    state = {"userinfo": None, "raise": False}

    def _authorize_access_token():
        if state["raise"]:
            raise RuntimeError("token exchange failed")
        return {"userinfo": state["userinfo"]}

    monkeypatch.setattr(
        oauth_module.oauth.linkedin,
        "authorize_access_token",
        _authorize_access_token,
        raising=False,
    )
    return state


def test_login_route_redirects_to_linkedin(client, monkeypatch):
    from flask import redirect

    monkeypatch.setattr(
        oauth_module.oauth.linkedin,
        "authorize_redirect",
        lambda redirect_uri, **kw: redirect("https://www.linkedin.com/oauth/authorize"),
        raising=False,
    )
    resp = client.get("/auth/linkedin")
    assert resp.status_code == 302
    assert "linkedin.com" in resp.headers["Location"]


def test_callback_creates_user_and_logs_in(client, fake_userinfo, users_db_path):
    db.init_schema()
    fake_userinfo["userinfo"] = {
        "sub": "sub-xyz",
        "email": "newbie@example.com",
        "email_verified": True,
    }
    resp = client.get("/auth/linkedin/callback")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/compte/admin")
    assert db.get_user_by_email("newbie@example.com") is not None


def test_callback_without_email_fails(client, fake_userinfo, users_db_path):
    db.init_schema()
    fake_userinfo["userinfo"] = {"sub": "sub-noemail", "email_verified": True}
    resp = client.get("/auth/linkedin/callback")
    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["Location"]


def test_callback_token_error_redirects(client, fake_userinfo, users_db_path):
    db.init_schema()
    fake_userinfo["raise"] = True
    resp = client.get("/auth/linkedin/callback")
    assert resp.status_code == 302
    assert "error=oauth_failed" in resp.headers["Location"]


def test_callback_user_cancelled_redirects(client, users_db_path):
    db.init_schema()
    resp = client.get("/auth/linkedin/callback?error=user_cancelled_login")
    assert resp.status_code == 302
    assert "error=oauth_cancelled" in resp.headers["Location"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/auth/test_oauth_routes.py -v`
Expected: FAIL (routes 404 / not defined).

- [ ] **Step 3: Implement the routes in `src/auth/routes.py`**

Add `session` to the flask import line:

```python
from flask import Blueprint, redirect, request, session
```

Add the import of the oauth registry near the top imports:

```python
from src.auth.oauth import oauth
```

Append the two routes at the end of the file:

```python
@auth_bp.route("/linkedin", methods=["GET"])
def linkedin_login():
    session["oauth_next"] = safe_next(
        request.args.get("next"), fallback="/compte/admin"
    )
    redirect_uri = f"{os.getenv('APP_BASE_URL', '')}/auth/linkedin/callback"
    return oauth.linkedin.authorize_redirect(redirect_uri)


@auth_bp.route("/linkedin/callback", methods=["GET"])
def linkedin_callback():
    next_url = safe_next(session.pop("oauth_next", None), fallback="/compte/admin")
    if request.args.get("error"):
        # L'utilisateur a refusé / annulé l'autorisation côté LinkedIn.
        return _redirect_with_error("/connexion", "oauth_cancelled")
    try:
        token = oauth.linkedin.authorize_access_token()
    except Exception:
        logger.exception("Échec de l'échange de token LinkedIn")
        return _redirect_with_error("/connexion", "oauth_failed")

    userinfo = token.get("userinfo") or {}
    subject = userinfo.get("sub")
    email = (userinfo.get("email") or "").strip().lower()
    if not subject or not email:
        logger.error("Réponse LinkedIn sans sub/email : %s", userinfo)
        return _redirect_with_error("/connexion", "oauth_failed")

    user = resolve_oauth_user(
        "linkedin", subject, email, bool(userinfo.get("email_verified"))
    )
    login_user(user, remember=True)
    return redirect(next_url)
```

Add the `os` import at the top of the file if absent:

```python
import os
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_oauth_routes.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full auth suite**

Run: `uv run pytest tests/auth -v`
Expected: PASS (all auth tests green).

- [ ] **Step 6: Commit**

```bash
git add src/auth/routes.py tests/auth/test_oauth_routes.py
git commit -m "feat(auth): routes /auth/linkedin et callback OIDC

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Bouton « Connexion avec LinkedIn » sur `/connexion` et `/inscription`

**Files:**

- Modify: `src/pages/connexion.py`
- Modify: `src/pages/inscription.py`
- Test: `tests/auth/test_oauth_routes.py` (extend — render assertions)

**Interfaces:**

- Consumes: route `/auth/linkedin` (Task 4).
- Produces: lien `<a href="/auth/linkedin">` stylé, libellé « Connexion avec LinkedIn », + messages d'erreur oauth.

- [ ] **Step 1: Write the failing tests**

Append to `tests/auth/test_oauth_routes.py`:

```python
def test_connexion_layout_has_linkedin_button():
    from src.pages.connexion import layout

    html_str = str(layout())
    assert "Connexion avec LinkedIn" in html_str
    assert "/auth/linkedin" in html_str


def test_connexion_layout_shows_oauth_error():
    from src.pages.connexion import layout

    assert "LinkedIn" in str(layout(error="oauth_failed"))


def test_inscription_layout_has_linkedin_button():
    from src.pages.inscription import layout

    html_str = str(layout())
    assert "Connexion avec LinkedIn" in html_str
    assert "/auth/linkedin" in html_str
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/auth/test_oauth_routes.py -k layout -v`
Expected: FAIL (button/text absent).

- [ ] **Step 3: Add a shared button helper and use it**

In `src/pages/connexion.py`, add the error messages and the button. Extend `ERROR_MESSAGES`:

```python
ERROR_MESSAGES = {
    "invalid_credentials": "Identifiants invalides.",
    "email_not_verified": "Vérifiez d'abord votre adresse email (consultez votre boîte de réception).",
    "oauth_cancelled": "Connexion LinkedIn annulée.",
    "oauth_failed": "Échec de la connexion via LinkedIn. Réessayez.",
}
```

Add this helper (above `layout`) in `connexion.py`:

```python
def linkedin_button():
    return html.A(
        "Connexion avec LinkedIn",
        href="/auth/linkedin",
        className="btn w-100 mb-2",
        style={"backgroundColor": "rgb(10, 102, 194)", "color": "white"},
    )
```

In `connexion.py` `layout`, insert a separator + button between the `html.Form(...)` and the `html.Hr()`:

```python
            html.Form(
                ...
            ),
            html.Div("ou", className="text-center text-muted my-2"),
            linkedin_button(),
            html.Hr(),
```

In `src/pages/inscription.py`, import the helper and place it likewise. At the top, after the existing imports:

```python
from src.pages.connexion import linkedin_button
```

In `inscription.py` `layout`, insert between the `html.Form(...)` and `html.Hr()`:

```python
            html.Form(
                ...
            ),
            html.Div("ou", className="text-center text-muted my-2"),
            linkedin_button(),
            html.Hr(),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_oauth_routes.py -k layout -v`
Expected: PASS (3 layout tests).

- [ ] **Step 5: Manual smoke check (no network)**

Run: `uv run python -c "from src.pages.connexion import layout; from src.pages.inscription import layout as l2; assert 'Connexion avec LinkedIn' in str(layout()) and 'Connexion avec LinkedIn' in str(l2()); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add src/pages/connexion.py src/pages/inscription.py tests/auth/test_oauth_routes.py
git commit -m "feat(auth): bouton Connexion avec LinkedIn sur connexion/inscription

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Vérification finale

- [ ] **Step 1: Run the whole test suite touched by this work**

Run: `uv run pytest tests/auth -v`
Expected: all green.

- [ ] **Step 2: Confirm the docs/spec prerequisites are accurate**

Re-read `docs/superpowers/specs/2026-06-24-linkedin-oauth-design.md` § Prérequis. Ensure the redirect URIs and env var names match what was implemented (`/auth/linkedin/callback`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`).

- [ ] **Step 3: No commit needed if nothing changed.** Otherwise commit doc fixes.

---

## Manual setup required before LinkedIn login works in production

(Not code — for the project admin.)

1. LinkedIn Developer Portal → create app → add product « Sign In with LinkedIn using OpenID Connect ».
2. Authorized redirect URLs:
   - `http://localhost:8050/auth/linkedin/callback`
   - `https://test.decp.info/auth/linkedin/callback`
   - `https://decp.info/auth/linkedin/callback`
3. Copy Client ID / Secret into each environment's `.env` (`LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`).
4. Ensure `APP_BASE_URL` matches the deployment origin in each `.env`.
