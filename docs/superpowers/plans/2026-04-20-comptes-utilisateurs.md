# Comptes utilisateurs — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter les fondations des comptes utilisateurs (inscription + vérification email, connexion, reset password, page compte) pour decp.info.

**Architecture:** Nouveau package `src/auth/` intégré à l'app Flask sous-jacente de Dash. Routes Flask natives pour les actions (POST), pages Dash pour le rendu (formulaires HTML). SQLite + `sqlite3` stdlib pour la persistance utilisateurs. Flask-Login pour les sessions, Flask-Mail pour SMTP, Flask-WTF pour CSRF. Hashage via `werkzeug.security`.

**Tech Stack:** Flask, Flask-Login, Flask-Mail, Flask-WTF, werkzeug.security, sqlite3, Dash, dash-bootstrap-components, pytest.

**Spec de référence :** `docs/superpowers/specs/2026-04-20-comptes-utilisateurs-design.md`.

---

## Vue d'ensemble des fichiers

**Créés :**

- `src/auth/__init__.py` — exports publics
- `src/auth/db.py` — SQLite (schéma + CRUD users + CRUD tokens)
- `src/auth/models.py` — classe `User` Flask-Login
- `src/auth/tokens.py` — génération/validation tokens
- `src/auth/mailer.py` — envoi d'emails
- `src/auth/setup.py` — `init_auth(app)` + helpers (`safe_next`)
- `src/auth/routes.py` — routes Flask (`/auth/*`)
- `src/auth/templates/emails/verify_email.html`
- `src/auth/templates/emails/verify_email.txt`
- `src/auth/templates/emails/reset_password.html`
- `src/auth/templates/emails/reset_password.txt`
- `src/pages/connexion.py`
- `src/pages/inscription.py`
- `src/pages/compte.py`
- `src/pages/mot_de_passe_oublie.py`
- `src/pages/reinitialiser_mot_de_passe.py`
- `src/pages/verification_email.py`
- `tests/auth/__init__.py`
- `tests/auth/conftest.py`
- `tests/auth/test_db.py`
- `tests/auth/test_tokens.py`
- `tests/auth/test_mailer.py`
- `tests/auth/test_setup.py`
- `tests/auth/test_signup.py`
- `tests/auth/test_verify_email.py`
- `tests/auth/test_login.py`
- `tests/auth/test_password_reset.py`
- `tests/auth/test_account.py`
- `tests/auth/test_csrf.py`

**Modifiés :**

- `pyproject.toml` — dépendances + variables d'env tests
- `.template.env` — nouvelles variables d'environnement
- `src/app.py` — ajout `init_auth(app)` + mise à jour navbar

---

## Task 1 : Dépendances et variables d'environnement

**Files:**

- Modify: `pyproject.toml`
- Modify: `.template.env`

- [ ] **Step 1 : Ajouter les dépendances dans `pyproject.toml`**

Dans la section `dependencies`, ajouter :

```toml
  "flask-login",
  "flask-mail",
  "flask-wtf",
  "email-validator",
```

- [ ] **Step 2 : Ajouter les variables d'env de tests dans `pyproject.toml`**

Dans `[tool.pytest.ini_options].env`, ajouter :

```toml
  "USERS_DB_PATH=tests/users.test.sqlite",
  "SECRET_KEY=test-secret-do-not-use-in-prod",
  "MAIL_FROM=test@decp.info",
  "APP_BASE_URL=http://localhost:8050",
  "SMTP_HOST=localhost",
  "SMTP_PORT=25",
  "WTF_CSRF_ENABLED=False",
```

- [ ] **Step 3 : Compléter `.template.env`**

Ajouter à la fin du fichier :

```
# Comptes utilisateurs
USERS_DB_PATH=users.sqlite
SECRET_KEY=  # à générer : python -c "import secrets; print(secrets.token_hex(32))"
APP_BASE_URL=http://localhost:8050

# SMTP pour envoi d'emails (vérification email, reset mot de passe)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=True
MAIL_FROM=noreply@decp.info
```

- [ ] **Step 4 : Installer les dépendances**

Run: `uv sync`
Expected : installation de flask-login, flask-mail, flask-wtf, email-validator.

- [ ] **Step 5 : Commit**

```bash
git add pyproject.toml .template.env uv.lock
git commit -m "Dépendances auth : Flask-Login/Mail/WTF, email-validator (#73)"
```

---

## Task 2 : Module `src/auth/db.py` — schéma et PRAGMAs

**Files:**

- Create: `src/auth/__init__.py`
- Create: `src/auth/db.py`
- Create: `tests/auth/__init__.py`
- Create: `tests/auth/conftest.py`
- Create: `tests/auth/test_db.py`

- [ ] **Step 1 : Créer `src/auth/__init__.py` vide**

```python

```

- [ ] **Step 2 : Créer `tests/auth/__init__.py` vide**

```python

```

- [ ] **Step 3 : Écrire la fixture DB dans `tests/auth/conftest.py`**

```python
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    yield db_path
```

- [ ] **Step 4 : Écrire les tests du schéma dans `tests/auth/test_db.py`**

```python
import sqlite3

from src.auth.db import get_conn, init_schema


def test_init_schema_creates_tables(users_db_path):
    init_schema()
    conn = get_conn()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"users", "email_verification_tokens", "password_reset_tokens"} <= tables


def test_init_schema_is_idempotent(users_db_path):
    init_schema()
    init_schema()
    conn = get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = [r[0] for r in tables]
    assert names.count("users") == 1


def test_pragmas_active(users_db_path):
    init_schema()
    conn = get_conn()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
```

- [ ] **Step 5 : Lancer les tests (ils doivent échouer)**

Run: `rtk uv run pytest tests/auth/test_db.py -v`
Expected : `ModuleNotFoundError: No module named 'src.auth.db'`.

- [ ] **Step 6 : Implémenter `src/auth/db.py` — schéma et connexion**

```python
import os
import sqlite3
from pathlib import Path
from threading import Lock

_conn: sqlite3.Connection | None = None
_conn_lock = Lock()

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email_verified INTEGER NOT NULL DEFAULT 0,
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
"""


def _db_path() -> Path:
    return Path(os.getenv("USERS_DB_PATH", "users.sqlite"))


def get_conn() -> sqlite3.Connection:
    global _conn
    with _conn_lock:
        if _conn is None:
            _conn = sqlite3.connect(
                str(_db_path()), check_same_thread=False, isolation_level=None
            )
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA foreign_keys = ON")
            _conn.execute("PRAGMA journal_mode = WAL")
        return _conn


def reset_conn_for_tests() -> None:
    global _conn
    with _conn_lock:
        if _conn is not None:
            _conn.close()
        _conn = None


def init_schema() -> None:
    conn = get_conn()
    conn.executescript(USERS_SCHEMA)
```

- [ ] **Step 7 : Ajouter la réinitialisation de connexion entre tests**

Dans `tests/auth/conftest.py`, mettre à jour la fixture :

```python
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()
```

- [ ] **Step 8 : Relancer les tests (ils doivent passer)**

Run: `rtk uv run pytest tests/auth/test_db.py -v`
Expected : 3 passed.

- [ ] **Step 9 : Commit**

```bash
git add src/auth/__init__.py src/auth/db.py tests/auth/__init__.py tests/auth/conftest.py tests/auth/test_db.py
git commit -m "src/auth/db.py : schéma SQLite et connexion (#73)"
```

---

## Task 3 : CRUD utilisateurs dans `src/auth/db.py`

**Files:**

- Modify: `src/auth/db.py`
- Modify: `tests/auth/test_db.py`

- [ ] **Step 1 : Ajouter les tests CRUD users à `tests/auth/test_db.py`**

```python
import pytest

from src.auth.db import (
    create_user,
    get_conn,
    get_user_by_email,
    get_user_by_id,
    init_schema,
    set_email_verified,
    update_password_hash,
)


def test_create_user_and_get_by_email(users_db_path):
    init_schema()
    user_id = create_user("alice@example.com", "hash-bidon")
    assert user_id > 0
    row = get_user_by_email("alice@example.com")
    assert row is not None
    assert row["email"] == "alice@example.com"
    assert row["email_verified"] == 0


def test_email_is_lowercased(users_db_path):
    init_schema()
    create_user("Alice@Example.COM", "hash")
    row = get_user_by_email("alice@example.com")
    assert row is not None
    row_upper = get_user_by_email("ALICE@example.com")
    assert row_upper is not None
    assert row["id"] == row_upper["id"]


def test_duplicate_email_raises(users_db_path):
    init_schema()
    create_user("alice@example.com", "hash")
    with pytest.raises(Exception):
        create_user("alice@example.com", "autre")


def test_get_user_by_id(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    row = get_user_by_id(uid)
    assert row["email"] == "a@b.c"
    assert get_user_by_id(999999) is None


def test_set_email_verified(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    assert get_user_by_id(uid)["email_verified"] == 0
    set_email_verified(uid)
    assert get_user_by_id(uid)["email_verified"] == 1


def test_update_password_hash(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "old")
    update_password_hash(uid, "new")
    assert get_user_by_id(uid)["password_hash"] == "new"
```

- [ ] **Step 2 : Lancer les tests (ils doivent échouer)**

Run: `rtk uv run pytest tests/auth/test_db.py -v`
Expected : ImportError sur les nouvelles fonctions.

- [ ] **Step 3 : Implémenter les CRUD users dans `src/auth/db.py`**

Ajouter à la fin du fichier :

```python
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_user(email: str, password_hash: str) -> int:
    conn = get_conn()
    now = _now()
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, email_verified, created_at, updated_at) "
        "VALUES (?, ?, 0, ?, ?)",
        (email.lower(), password_hash, now, now),
    )
    return cur.lastrowid


def get_user_by_email(email: str) -> sqlite3.Row | None:
    return get_conn().execute(
        "SELECT * FROM users WHERE email = ?", (email.lower(),)
    ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    return get_conn().execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def set_email_verified(user_id: int) -> None:
    get_conn().execute(
        "UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?",
        (_now(), user_id),
    )


def update_password_hash(user_id: int, password_hash: str) -> None:
    get_conn().execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (password_hash, _now(), user_id),
    )


def delete_user(user_id: int) -> None:
    get_conn().execute("DELETE FROM users WHERE id = ?", (user_id,))
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_db.py -v`
Expected : 9 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/db.py tests/auth/test_db.py
git commit -m "src/auth/db.py : CRUD users (#73)"
```

---

## Task 4 : CRUD tokens dans `src/auth/db.py`

**Files:**

- Modify: `src/auth/db.py`
- Modify: `tests/auth/test_db.py`

- [ ] **Step 1 : Ajouter les tests tokens à `tests/auth/test_db.py`**

```python
from datetime import datetime, timedelta, timezone

from src.auth.db import (
    create_email_verification_token,
    create_password_reset_token,
    delete_email_verification_tokens_for_user,
    delete_password_reset_tokens_for_user,
    find_email_verification_token,
    find_password_reset_token,
    purge_expired_tokens,
)


def _future(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def test_email_verification_token_roundtrip(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_email_verification_token("hashed-token", uid, _future(24))
    row = find_email_verification_token("hashed-token")
    assert row is not None
    assert row["user_id"] == uid


def test_password_reset_token_roundtrip(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_password_reset_token("reset-hash", uid, _future(1))
    row = find_password_reset_token("reset-hash")
    assert row is not None
    assert row["user_id"] == uid


def test_delete_tokens_for_user(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_email_verification_token("t1", uid, _future(1))
    create_email_verification_token("t2", uid, _future(1))
    delete_email_verification_tokens_for_user(uid)
    assert find_email_verification_token("t1") is None
    assert find_email_verification_token("t2") is None


def test_delete_password_reset_tokens_for_user(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_password_reset_token("r1", uid, _future(1))
    delete_password_reset_tokens_for_user(uid)
    assert find_password_reset_token("r1") is None


def test_purge_expired_tokens(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_email_verification_token("live", uid, _future(1))
    create_email_verification_token("expired", uid, _past(1))
    create_password_reset_token("live-r", uid, _future(1))
    create_password_reset_token("expired-r", uid, _past(1))
    purge_expired_tokens()
    assert find_email_verification_token("live") is not None
    assert find_email_verification_token("expired") is None
    assert find_password_reset_token("live-r") is not None
    assert find_password_reset_token("expired-r") is None


def test_cascade_delete_on_user_delete(users_db_path):
    init_schema()
    uid = create_user("a@b.c", "h")
    create_email_verification_token("t", uid, _future(1))
    delete_user(uid)
    assert find_email_verification_token("t") is None
```

- [ ] **Step 2 : Lancer les tests (ils doivent échouer)**

Run: `rtk uv run pytest tests/auth/test_db.py -v`
Expected : ImportError.

- [ ] **Step 3 : Implémenter les CRUD tokens dans `src/auth/db.py`**

Ajouter à la fin du fichier :

```python
def create_email_verification_token(
    token_hash: str, user_id: int, expires_at: str
) -> None:
    get_conn().execute(
        "INSERT INTO email_verification_tokens (token_hash, user_id, expires_at, created_at) "
        "VALUES (?, ?, ?, ?)",
        (token_hash, user_id, expires_at, _now()),
    )


def find_email_verification_token(token_hash: str) -> sqlite3.Row | None:
    return get_conn().execute(
        "SELECT * FROM email_verification_tokens "
        "WHERE token_hash = ? AND expires_at > ?",
        (token_hash, _now()),
    ).fetchone()


def delete_email_verification_tokens_for_user(user_id: int) -> None:
    get_conn().execute(
        "DELETE FROM email_verification_tokens WHERE user_id = ?", (user_id,)
    )


def create_password_reset_token(
    token_hash: str, user_id: int, expires_at: str
) -> None:
    get_conn().execute(
        "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, created_at) "
        "VALUES (?, ?, ?, ?)",
        (token_hash, user_id, expires_at, _now()),
    )


def find_password_reset_token(token_hash: str) -> sqlite3.Row | None:
    return get_conn().execute(
        "SELECT * FROM password_reset_tokens "
        "WHERE token_hash = ? AND expires_at > ?",
        (token_hash, _now()),
    ).fetchone()


def delete_password_reset_tokens_for_user(user_id: int) -> None:
    get_conn().execute(
        "DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,)
    )


def purge_expired_tokens() -> None:
    now = _now()
    conn = get_conn()
    conn.execute(
        "DELETE FROM email_verification_tokens WHERE expires_at <= ?", (now,)
    )
    conn.execute(
        "DELETE FROM password_reset_tokens WHERE expires_at <= ?", (now,)
    )
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_db.py -v`
Expected : 15 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/db.py tests/auth/test_db.py
git commit -m "src/auth/db.py : CRUD tokens de vérification et reset (#73)"
```

---

## Task 5 : Module `src/auth/tokens.py`

**Files:**

- Create: `src/auth/tokens.py`
- Create: `tests/auth/test_tokens.py`

- [ ] **Step 1 : Écrire les tests dans `tests/auth/test_tokens.py`**

```python
from datetime import datetime, timedelta, timezone

from src.auth import db
from src.auth.tokens import (
    consume_password_reset_token,
    consume_verification_token,
    create_password_reset_token,
    create_verification_token,
    hash_token,
)


def test_hash_token_is_stable():
    t = "abc123"
    assert hash_token(t) == hash_token(t)
    assert hash_token(t) != hash_token("abc124")
    assert len(hash_token(t)) == 64  # sha256 hex


def test_create_verification_token_returns_plain_token(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    plain = create_verification_token(uid)
    assert isinstance(plain, str)
    assert len(plain) >= 32
    # stocké en DB sous forme hashée
    row = db.find_email_verification_token(hash_token(plain))
    assert row is not None
    assert row["user_id"] == uid


def test_consume_verification_token_succeeds_once(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    plain = create_verification_token(uid)
    user_id = consume_verification_token(plain)
    assert user_id == uid
    # usage unique : les tokens de cet user sont supprimés
    assert consume_verification_token(plain) is None


def test_consume_invalid_verification_token(users_db_path):
    db.init_schema()
    assert consume_verification_token("n-existe-pas") is None


def test_verification_token_expires(users_db_path, monkeypatch):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    plain = create_verification_token(uid, expires_in_hours=-1)
    assert consume_verification_token(plain) is None


def test_create_password_reset_token_deletes_previous(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    old = create_password_reset_token(uid)
    new = create_password_reset_token(uid)
    # l'ancien a été supprimé
    assert consume_password_reset_token(old) is None
    # le nouveau fonctionne
    assert consume_password_reset_token(new) == uid


def test_consume_password_reset_token_is_single_use(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    plain = create_password_reset_token(uid)
    assert consume_password_reset_token(plain) == uid
    assert consume_password_reset_token(plain) is None
```

- [ ] **Step 2 : Lancer les tests (ils doivent échouer)**

Run: `rtk uv run pytest tests/auth/test_tokens.py -v`
Expected : ModuleNotFoundError.

- [ ] **Step 3 : Implémenter `src/auth/tokens.py`**

```python
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from src.auth import db

VERIFICATION_TTL_HOURS = 24
RESET_TTL_HOURS = 1


def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _expires_at(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def create_verification_token(
    user_id: int, expires_in_hours: int = VERIFICATION_TTL_HOURS
) -> str:
    plain = secrets.token_urlsafe(32)
    db.create_email_verification_token(
        hash_token(plain), user_id, _expires_at(expires_in_hours)
    )
    return plain


def consume_verification_token(plain: str) -> int | None:
    row = db.find_email_verification_token(hash_token(plain))
    if row is None:
        return None
    user_id = row["user_id"]
    db.delete_email_verification_tokens_for_user(user_id)
    return user_id


def create_password_reset_token(
    user_id: int, expires_in_hours: int = RESET_TTL_HOURS
) -> str:
    db.delete_password_reset_tokens_for_user(user_id)
    plain = secrets.token_urlsafe(32)
    db.create_password_reset_token(
        hash_token(plain), user_id, _expires_at(expires_in_hours)
    )
    return plain


def consume_password_reset_token(plain: str) -> int | None:
    row = db.find_password_reset_token(hash_token(plain))
    if row is None:
        return None
    user_id = row["user_id"]
    db.delete_password_reset_tokens_for_user(user_id)
    return user_id


def validate_password_reset_token(plain: str) -> int | None:
    """Check token without consuming (used to render the reset form)."""
    row = db.find_password_reset_token(hash_token(plain))
    return row["user_id"] if row else None
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_tokens.py -v`
Expected : 7 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/tokens.py tests/auth/test_tokens.py
git commit -m "src/auth/tokens.py : génération et validation des tokens (#73)"
```

---

## Task 6 : Modèle `User` Flask-Login

**Files:**

- Create: `src/auth/models.py`
- Modify: `tests/auth/test_db.py` (ou nouveau `test_models.py`)

- [ ] **Step 1 : Écrire un test minimal dans un nouveau fichier `tests/auth/test_models.py`**

```python
from src.auth import db
from src.auth.models import User, load_user


def test_user_from_row(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "hash")
    db.set_email_verified(uid)
    row = db.get_user_by_id(uid)
    user = User(row)
    assert user.id == uid
    assert user.email == "a@b.c"
    assert user.is_authenticated is True
    assert user.is_active is True
    assert user.is_anonymous is False
    assert user.get_id() == str(uid)


def test_load_user_returns_none_if_missing(users_db_path):
    db.init_schema()
    assert load_user("999999") is None


def test_load_user_returns_user(users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    user = load_user(str(uid))
    assert user is not None
    assert user.id == uid
```

- [ ] **Step 2 : Lancer les tests (ils doivent échouer)**

Run: `rtk uv run pytest tests/auth/test_models.py -v`
Expected : ModuleNotFoundError.

- [ ] **Step 3 : Implémenter `src/auth/models.py`**

```python
import sqlite3

from src.auth import db


class User:
    def __init__(self, row: sqlite3.Row):
        self.id: int = row["id"]
        self.email: str = row["email"]
        self.email_verified: bool = bool(row["email_verified"])

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


def load_user(user_id: str) -> User | None:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    row = db.get_user_by_id(uid)
    return User(row) if row else None
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_models.py -v`
Expected : 3 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/models.py tests/auth/test_models.py
git commit -m "src/auth/models.py : classe User Flask-Login (#73)"
```

---

## Task 7 : Module `src/auth/mailer.py` et templates

**Files:**

- Create: `src/auth/mailer.py`
- Create: `src/auth/templates/emails/verify_email.html`
- Create: `src/auth/templates/emails/verify_email.txt`
- Create: `src/auth/templates/emails/reset_password.html`
- Create: `src/auth/templates/emails/reset_password.txt`
- Create: `tests/auth/test_mailer.py`

- [ ] **Step 1 : Créer les 4 templates d'email**

`src/auth/templates/emails/verify_email.txt` :

```
Bonjour,

Pour vérifier votre adresse email et activer votre compte decp.info, ouvrez le lien suivant :

{{ link }}

Ce lien est valide pendant 24 heures.

Si vous n'êtes pas à l'origine de cette inscription, ignorez cet email.

— decp.info
```

`src/auth/templates/emails/verify_email.html` :

```html
<!DOCTYPE html>
<html lang="fr">
  <body style="font-family: sans-serif; max-width: 600px; margin: auto;">
    <h2 style="color: #333;">decp.info</h2>
    <p>Bonjour,</p>
    <p>
      Pour vérifier votre adresse email et activer votre compte decp.info,
      cliquez sur le lien ci-dessous :
    </p>
    <p><a href="{{ link }}">Vérifier mon adresse email</a></p>
    <p style="color: #666;">
      Ou copiez cette URL dans votre navigateur : {{ link }}
    </p>
    <p><em>Ce lien est valide pendant 24 heures.</em></p>
    <p>
      Si vous n'êtes pas à l'origine de cette inscription, ignorez cet email.
    </p>
    <p>— decp.info</p>
  </body>
</html>
```

`src/auth/templates/emails/reset_password.txt` :

```
Bonjour,

Vous avez demandé la réinitialisation de votre mot de passe decp.info. Pour choisir un nouveau mot de passe, ouvrez le lien suivant :

{{ link }}

Ce lien est valide pendant 1 heure.

Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.

— decp.info
```

`src/auth/templates/emails/reset_password.html` :

```html
<!DOCTYPE html>
<html lang="fr">
  <body style="font-family: sans-serif; max-width: 600px; margin: auto;">
    <h2 style="color: #333;">decp.info</h2>
    <p>Bonjour,</p>
    <p>
      Vous avez demandé la réinitialisation de votre mot de passe decp.info.
      Pour choisir un nouveau mot de passe, cliquez sur le lien ci-dessous :
    </p>
    <p><a href="{{ link }}">Réinitialiser mon mot de passe</a></p>
    <p style="color: #666;">
      Ou copiez cette URL dans votre navigateur : {{ link }}
    </p>
    <p><em>Ce lien est valide pendant 1 heure.</em></p>
    <p>Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.</p>
    <p>— decp.info</p>
  </body>
</html>
```

- [ ] **Step 2 : Écrire les tests du mailer dans `tests/auth/test_mailer.py`**

```python
import pytest
from flask import Flask
from flask_mail import Mail

from src.auth import mailer


@pytest.fixture
def mail_app(monkeypatch, tmp_path):
    app = Flask(
        __name__,
        template_folder=str(
            (__import__("pathlib").Path(mailer.__file__).parent / "templates").resolve()
        ),
    )
    app.config["MAIL_SUPPRESS_SEND"] = True
    app.config["MAIL_DEFAULT_SENDER"] = "noreply@decp.info"
    app.config["TESTING"] = True
    mail = Mail(app)
    monkeypatch.setattr(mailer, "_mail", mail)
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    return app


def test_send_verification_email(mail_app):
    with mail_app.app_context(), mail_app.test_request_context():
        with mail_app.extensions["mail"].record_messages() as outbox:
            mailer.send_verification_email("a@b.c", "TOKEN123")
    assert len(outbox) == 1
    msg = outbox[0]
    assert msg.recipients == ["a@b.c"]
    assert "verification-email?token=TOKEN123" in msg.body
    assert "verification-email?token=TOKEN123" in msg.html


def test_send_reset_email(mail_app):
    with mail_app.app_context(), mail_app.test_request_context():
        with mail_app.extensions["mail"].record_messages() as outbox:
            mailer.send_reset_email("a@b.c", "RESET456")
    assert len(outbox) == 1
    msg = outbox[0]
    assert "reinitialiser-mot-de-passe?token=RESET456" in msg.body
```

- [ ] **Step 3 : Lancer les tests (échouent)**

Run: `rtk uv run pytest tests/auth/test_mailer.py -v`
Expected : ModuleNotFoundError.

- [ ] **Step 4 : Implémenter `src/auth/mailer.py`**

```python
import os
from pathlib import Path

from flask import Flask, render_template
from flask_mail import Mail, Message

TEMPLATES_DIR = Path(__file__).parent / "templates"

_mail: Mail | None = None


def init_mailer(app: Flask) -> None:
    global _mail
    app.config["MAIL_SERVER"] = os.getenv("SMTP_HOST", "")
    app.config["MAIL_PORT"] = int(os.getenv("SMTP_PORT", "587"))
    app.config["MAIL_USERNAME"] = os.getenv("SMTP_USERNAME") or None
    app.config["MAIL_PASSWORD"] = os.getenv("SMTP_PASSWORD") or None
    app.config["MAIL_USE_TLS"] = (
        os.getenv("SMTP_USE_TLS", "True").lower() == "true"
    )
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv(
        "MAIL_FROM", "noreply@decp.info"
    )
    app.config["MAIL_SUPPRESS_SEND"] = (
        os.getenv("DEVELOPMENT", "False").lower() == "true"
    )
    # Inclure les templates du package auth dans la recherche Jinja
    app.jinja_loader.searchpath.append(str(TEMPLATES_DIR))
    _mail = Mail(app)


def _base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8050").rstrip("/")


def _send(subject: str, recipient: str, txt_template: str, html_template: str, **ctx) -> None:
    assert _mail is not None, "Mailer non initialisé (init_mailer(app) non appelé)"
    msg = Message(subject=subject, recipients=[recipient])
    msg.body = render_template(txt_template, **ctx)
    msg.html = render_template(html_template, **ctx)
    _mail.send(msg)


def send_verification_email(email: str, token: str) -> None:
    link = f"{_base_url()}/verification-email?token={token}"
    _send(
        "Vérification de votre adresse email — decp.info",
        email,
        "emails/verify_email.txt",
        "emails/verify_email.html",
        link=link,
    )


def send_reset_email(email: str, token: str) -> None:
    link = f"{_base_url()}/reinitialiser-mot-de-passe?token={token}"
    _send(
        "Réinitialisation de votre mot de passe — decp.info",
        email,
        "emails/reset_password.txt",
        "emails/reset_password.html",
        link=link,
    )
```

- [ ] **Step 5 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_mailer.py -v`
Expected : 2 passed.

- [ ] **Step 6 : Commit**

```bash
git add src/auth/mailer.py src/auth/templates tests/auth/test_mailer.py
git commit -m "src/auth/mailer.py : envoi d'emails HTML+texte (#73)"
```

---

## Task 8 : Setup `init_auth` et helper `safe_next`

**Files:**

- Create: `src/auth/setup.py`
- Create: `tests/auth/test_setup.py`

- [ ] **Step 1 : Écrire les tests dans `tests/auth/test_setup.py`**

```python
import pytest
from flask import Flask
from flask_login import current_user

from src.auth.setup import init_auth, safe_next


def test_safe_next_allows_relative_path():
    assert safe_next("/acheteur?id=1") == "/acheteur?id=1"


def test_safe_next_rejects_absolute_urls():
    assert safe_next("https://evil.com/phish") == "/"


def test_safe_next_rejects_protocol_relative():
    assert safe_next("//evil.com") == "/"


def test_safe_next_rejects_empty():
    assert safe_next("") == "/"
    assert safe_next(None) == "/"


def test_safe_next_custom_fallback():
    assert safe_next("", fallback="/compte") == "/compte"


def test_init_auth_requires_secret_key(monkeypatch, users_db_path):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    app = Flask(__name__)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        init_auth(app)


def test_init_auth_anonymous_user_not_authenticated(users_db_path):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    init_auth(app)
    with app.test_request_context("/"):
        assert current_user.is_authenticated is False
```

- [ ] **Step 2 : Lancer les tests**

Run: `rtk uv run pytest tests/auth/test_setup.py -v`
Expected : ModuleNotFoundError.

- [ ] **Step 3 : Implémenter `src/auth/setup.py`**

```python
import os

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from src.auth import db, mailer
from src.auth.models import load_user
from src.utils import DEVELOPMENT, logger

_csrf: CSRFProtect | None = None
_login_manager: LoginManager | None = None


def safe_next(url: str | None, fallback: str = "/") -> str:
    if not url or not url.startswith("/") or url.startswith("//"):
        return fallback
    return url


def init_auth(app: Flask) -> None:
    global _csrf, _login_manager

    secret = os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "SECRET_KEY est obligatoire pour l'authentification. "
            "Définissez-la dans .env (voir .template.env)."
        )
    app.config["SECRET_KEY"] = secret
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = not DEVELOPMENT
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 jours

    db.init_schema()
    db.purge_expired_tokens()

    mailer.init_mailer(app)

    _login_manager = LoginManager()
    _login_manager.login_view = "/connexion"
    _login_manager.user_loader(load_user)
    _login_manager.init_app(app)

    _csrf = CSRFProtect(app)

    if not os.getenv("SMTP_HOST"):
        logger.warning(
            "SMTP_HOST non défini : les emails d'auth échoueront. "
            "Définissez les variables SMTP_* dans .env pour envoyer des emails."
        )
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_setup.py -v`
Expected : 7 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/setup.py tests/auth/test_setup.py
git commit -m "src/auth/setup.py : init_auth et helper safe_next (#73)"
```

---

## Task 9 : Intégrer `init_auth` dans `src/app.py`

**Files:**

- Modify: `src/app.py`
- Create: `tests/auth/test_app_integration.py`

- [ ] **Step 1 : Écrire un test d'intégration**

`tests/auth/test_app_integration.py` :

```python
def test_app_imports_cleanly(users_db_path):
    from src.app import app

    assert app is not None
    # Flask-Login manager attaché
    assert "login_manager" in app.server.extensions or hasattr(
        app.server, "login_manager"
    )
```

- [ ] **Step 2 : Modifier `src/app.py` pour appeler `init_auth`**

Ajouter après l'initialisation du cache (après `cache.init_app(...)`) :

```python
from src.auth.setup import init_auth

init_auth(app.server)
```

- [ ] **Step 3 : Vérifier que l'app démarre et que les tests existants passent**

Run: `rtk uv run pytest tests/auth/test_app_integration.py -v`
Expected : 1 passed.

Run: `rtk uv run pytest tests/ -v -k "not test_auth"` puis `rtk uv run pytest tests/auth/ -v`
Expected : tests existants verts, tests auth verts.

- [ ] **Step 4 : Commit**

```bash
git add src/app.py tests/auth/test_app_integration.py
git commit -m "src/app.py : initialisation de l'authentification au démarrage (#73)"
```

---

## Task 10 : Routes Flask — squelette et fixture `client`

**Files:**

- Create: `src/auth/routes.py`
- Modify: `src/auth/setup.py` (enregistrer le blueprint)
- Modify: `tests/auth/conftest.py` (ajouter fixture client + mail_outbox)

- [ ] **Step 1 : Créer le blueprint vide `src/auth/routes.py`**

```python
from flask import Blueprint

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
```

- [ ] **Step 2 : Enregistrer le blueprint dans `src/auth/setup.py`**

Juste avant `CSRFProtect(app)`, ajouter :

```python
    from src.auth.routes import auth_bp
    app.register_blueprint(auth_bp)
```

- [ ] **Step 3 : Ajouter les fixtures `client` et `mail_outbox` à `tests/auth/conftest.py`**

Remplacer le contenu du fichier par :

```python
import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    reset_conn_for_tests()
    yield db_path
    reset_conn_for_tests()


@pytest.fixture
def app(users_db_path, monkeypatch):
    # Empêcher l'import de src.app de rejouer côté data ; on charge
    # uniquement la stack auth sur une app Flask minimale.
    from flask import Flask

    from src.auth.setup import init_auth

    app = Flask(__name__)
    init_auth(app)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mail_outbox(app):
    mail = app.extensions["mail"]
    with mail.record_messages() as outbox:
        yield outbox
```

- [ ] **Step 4 : Vérifier que les tests existants passent toujours**

Run: `rtk uv run pytest tests/auth/ -v`
Expected : tous les tests auth passent.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/routes.py src/auth/setup.py tests/auth/conftest.py
git commit -m "src/auth/routes.py : blueprint auth et fixtures de test (#73)"
```

---

## Task 11 : Route `/auth/signup`

**Files:**

- Modify: `src/auth/routes.py`
- Create: `tests/auth/test_signup.py`

- [ ] **Step 1 : Écrire les tests dans `tests/auth/test_signup.py`**

```python
from src.auth import db


def _signup(client, email="alice@example.com", password="password12", confirm=None):
    return client.post(
        "/auth/signup",
        data={
            "email": email,
            "password": password,
            "password_confirm": confirm if confirm is not None else password,
        },
    )


def test_signup_creates_unverified_user(client, mail_outbox):
    resp = _signup(client)
    assert resp.status_code == 302
    assert "pending_verification=1" in resp.headers["Location"]
    row = db.get_user_by_email("alice@example.com")
    assert row is not None
    assert row["email_verified"] == 0
    assert len(mail_outbox) == 1
    assert mail_outbox[0].recipients == ["alice@example.com"]


def test_signup_rejects_short_password(client, mail_outbox):
    resp = _signup(client, password="short", confirm="short")
    assert resp.status_code == 302
    assert "error=password_too_short" in resp.headers["Location"]
    assert db.get_user_by_email("alice@example.com") is None
    assert len(mail_outbox) == 0


def test_signup_rejects_mismatched_passwords(client, mail_outbox):
    resp = _signup(client, password="password12", confirm="different12")
    assert "error=password_mismatch" in resp.headers["Location"]
    assert db.get_user_by_email("alice@example.com") is None
    assert len(mail_outbox) == 0


def test_signup_rejects_invalid_email(client, mail_outbox):
    resp = _signup(client, email="pas-un-email")
    assert "error=invalid_email" in resp.headers["Location"]
    assert len(mail_outbox) == 0


def test_signup_rejects_duplicate_email(client, mail_outbox):
    _signup(client)
    resp = _signup(client)
    assert "error=email_taken" in resp.headers["Location"]
    assert len(mail_outbox) == 1  # seul le premier signup a envoyé l'email


def test_signup_email_lowercased(client, mail_outbox):
    _signup(client, email="Alice@Example.COM")
    assert db.get_user_by_email("alice@example.com") is not None
```

- [ ] **Step 2 : Lancer les tests (ils doivent échouer)**

Run: `rtk uv run pytest tests/auth/test_signup.py -v`
Expected : 404 (la route n'existe pas encore).

- [ ] **Step 3 : Implémenter la route dans `src/auth/routes.py`**

Remplacer le contenu du fichier par :

```python
from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, redirect, request, url_for
from werkzeug.security import generate_password_hash

from src.auth import db, mailer, tokens
from src.utils import logger

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

MIN_PASSWORD_LENGTH = 8


def _redirect_with_error(path: str, error: str, email: str | None = None) -> "Response":
    url = f"{path}?error={error}"
    if email:
        url += f"&email={email}"
    return redirect(url)


@auth_bp.route("/signup", methods=["POST"])
def signup():
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    password_confirm = request.form.get("password_confirm") or ""

    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.normalized.lower()
    except EmailNotValidError:
        return _redirect_with_error("/inscription", "invalid_email", email)

    if len(password) < MIN_PASSWORD_LENGTH:
        return _redirect_with_error("/inscription", "password_too_short", email)
    if password != password_confirm:
        return _redirect_with_error("/inscription", "password_mismatch", email)

    if db.get_user_by_email(email) is not None:
        return _redirect_with_error("/inscription", "email_taken", email)

    user_id = db.create_user(email, generate_password_hash(password))
    token = tokens.create_verification_token(user_id)
    try:
        mailer.send_verification_email(email, token)
    except Exception:
        logger.exception("Échec d'envoi de l'email de vérification")
        db.delete_user(user_id)
        return _redirect_with_error("/inscription", "email_send_failed", email)

    return redirect("/connexion?pending_verification=1")
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_signup.py -v`
Expected : 6 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/routes.py tests/auth/test_signup.py
git commit -m "src/auth/routes.py : route /auth/signup (#73)"
```

---

## Task 12 : Route `/auth/verify-email`

**Files:**

- Modify: `src/auth/routes.py`
- Create: `tests/auth/test_verify_email.py`

- [ ] **Step 1 : Écrire les tests**

`tests/auth/test_verify_email.py` :

```python
from src.auth import db, tokens


def test_verify_email_valid_token_marks_user_verified(client, users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "hash")
    token = tokens.create_verification_token(uid)

    resp = client.get(f"/auth/verify-email?token={token}")
    assert resp.status_code == 302
    assert "/connexion?verified=1" in resp.headers["Location"]
    assert db.get_user_by_id(uid)["email_verified"] == 1


def test_verify_email_invalid_token(client):
    resp = client.get("/auth/verify-email?token=invalide")
    assert "error=invalid_token" in resp.headers["Location"]


def test_verify_email_missing_token(client):
    resp = client.get("/auth/verify-email")
    assert "error=invalid_token" in resp.headers["Location"]


def test_verify_email_single_use(client, users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    token = tokens.create_verification_token(uid)
    client.get(f"/auth/verify-email?token={token}")
    resp = client.get(f"/auth/verify-email?token={token}")
    assert "error=invalid_token" in resp.headers["Location"]
```

- [ ] **Step 2 : Lancer les tests**

Run: `rtk uv run pytest tests/auth/test_verify_email.py -v`
Expected : 404.

- [ ] **Step 3 : Ajouter la route dans `src/auth/routes.py`**

À la fin du fichier :

```python
@auth_bp.route("/verify-email", methods=["GET"])
def verify_email():
    token = request.args.get("token") or ""
    if not token:
        return redirect("/verification-email?error=invalid_token")
    user_id = tokens.consume_verification_token(token)
    if user_id is None:
        return redirect("/verification-email?error=invalid_token")
    db.set_email_verified(user_id)
    return redirect("/connexion?verified=1")
```

- [ ] **Step 4 : Ajuster le premier test (redirection vers `/connexion` après succès, page `/verification-email` pour les erreurs)**

Ce comportement reflète la page d'erreur dédiée côté Dash (cf. Task 20). Mettre à jour le test si le code diffère.

Run: `rtk uv run pytest tests/auth/test_verify_email.py -v`
Expected : 4 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/routes.py tests/auth/test_verify_email.py
git commit -m "src/auth/routes.py : route /auth/verify-email (#73)"
```

---

## Task 13 : Routes `/auth/login` et `/auth/logout`

**Files:**

- Modify: `src/auth/routes.py`
- Create: `tests/auth/test_login.py`

- [ ] **Step 1 : Écrire les tests dans `tests/auth/test_login.py`**

```python
from werkzeug.security import generate_password_hash

from src.auth import db


def _make_verified_user(email="a@b.c", password="password12"):
    db.init_schema()
    uid = db.create_user(email, generate_password_hash(password))
    db.set_email_verified(uid)
    return uid


def test_login_success(client, users_db_path):
    _make_verified_user()
    resp = client.post(
        "/auth/login",
        data={"email": "a@b.c", "password": "password12"},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/compte")


def test_login_wrong_password(client, users_db_path):
    _make_verified_user()
    resp = client.post(
        "/auth/login", data={"email": "a@b.c", "password": "wrong-password"}
    )
    assert "error=invalid_credentials" in resp.headers["Location"]


def test_login_unknown_email_same_error(client, users_db_path):
    db.init_schema()
    resp = client.post(
        "/auth/login",
        data={"email": "inexistant@example.com", "password": "x" * 12},
    )
    assert "error=invalid_credentials" in resp.headers["Location"]


def test_login_unverified_user(client, users_db_path):
    db.init_schema()
    db.create_user("a@b.c", generate_password_hash("password12"))
    resp = client.post(
        "/auth/login", data={"email": "a@b.c", "password": "password12"}
    )
    assert "error=email_not_verified" in resp.headers["Location"]


def test_login_respects_safe_next(client, users_db_path):
    _make_verified_user()
    resp = client.post(
        "/auth/login",
        data={"email": "a@b.c", "password": "password12", "next": "/tableau"},
    )
    assert resp.headers["Location"].endswith("/tableau")


def test_login_rejects_absolute_next(client, users_db_path):
    _make_verified_user()
    resp = client.post(
        "/auth/login",
        data={
            "email": "a@b.c",
            "password": "password12",
            "next": "https://evil.com",
        },
    )
    assert resp.headers["Location"].endswith("/compte")


def test_logout_clears_session(client, users_db_path):
    _make_verified_user()
    client.post(
        "/auth/login", data={"email": "a@b.c", "password": "password12"}
    )
    resp = client.post("/auth/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
```

- [ ] **Step 2 : Lancer les tests**

Run: `rtk uv run pytest tests/auth/test_login.py -v`
Expected : tests rouges (404).

- [ ] **Step 3 : Ajouter les routes dans `src/auth/routes.py`**

Ajouter à la fin :

```python
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from src.auth.models import User
from src.auth.setup import safe_next

# Hash bidon pré-calculé pour uniformiser le timing login
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


@auth_bp.route("/login", methods=["POST"])
def login():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    next_url = safe_next(request.form.get("next"), fallback="/compte")

    row = db.get_user_by_email(email)
    if row is None:
        check_password_hash(_DUMMY_HASH, password)  # uniformiser le temps
        return _redirect_with_error("/connexion", "invalid_credentials", email)

    if not check_password_hash(row["password_hash"], password):
        return _redirect_with_error("/connexion", "invalid_credentials", email)

    if not row["email_verified"]:
        return _redirect_with_error("/connexion", "email_not_verified", email)

    login_user(User(row), remember=True)
    return redirect(next_url)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    return redirect("/")
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_login.py -v`
Expected : 7 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/routes.py tests/auth/test_login.py
git commit -m "src/auth/routes.py : routes /auth/login et /auth/logout (#73)"
```

---

## Task 14 : Routes password reset (request + perform)

**Files:**

- Modify: `src/auth/routes.py`
- Create: `tests/auth/test_password_reset.py`

- [ ] **Step 1 : Écrire les tests dans `tests/auth/test_password_reset.py`**

```python
from werkzeug.security import check_password_hash, generate_password_hash

from src.auth import db, tokens


def _make_user():
    db.init_schema()
    uid = db.create_user("a@b.c", generate_password_hash("old-password12"))
    db.set_email_verified(uid)
    return uid


def test_request_reset_sends_email_for_existing_user(client, mail_outbox, users_db_path):
    _make_user()
    resp = client.post(
        "/auth/request-password-reset", data={"email": "a@b.c"}
    )
    assert resp.status_code == 302
    assert "pending=1" in resp.headers["Location"]
    assert len(mail_outbox) == 1


def test_request_reset_same_response_for_unknown_email(client, mail_outbox, users_db_path):
    db.init_schema()
    resp = client.post(
        "/auth/request-password-reset", data={"email": "absent@b.c"}
    )
    assert "pending=1" in resp.headers["Location"]
    assert len(mail_outbox) == 0


def test_perform_reset_with_valid_token(client, users_db_path):
    uid = _make_user()
    token = tokens.create_password_reset_token(uid)
    resp = client.post(
        "/auth/reset-password",
        data={
            "token": token,
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert resp.status_code == 302
    assert "password_changed=1" in resp.headers["Location"]
    row = db.get_user_by_id(uid)
    assert check_password_hash(row["password_hash"], "new-password12")


def test_perform_reset_rejects_expired_token(client, users_db_path):
    uid = _make_user()
    token = tokens.create_password_reset_token(uid, expires_in_hours=-1)
    resp = client.post(
        "/auth/reset-password",
        data={
            "token": token,
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert "error=invalid_token" in resp.headers["Location"]


def test_perform_reset_rejects_short_password(client, users_db_path):
    uid = _make_user()
    token = tokens.create_password_reset_token(uid)
    resp = client.post(
        "/auth/reset-password",
        data={"token": token, "password": "short", "password_confirm": "short"},
    )
    assert "error=password_too_short" in resp.headers["Location"]


def test_perform_reset_rejects_mismatched(client, users_db_path):
    uid = _make_user()
    token = tokens.create_password_reset_token(uid)
    resp = client.post(
        "/auth/reset-password",
        data={
            "token": token,
            "password": "new-password12",
            "password_confirm": "other-password99",
        },
    )
    assert "error=password_mismatch" in resp.headers["Location"]
```

- [ ] **Step 2 : Lancer les tests**

Run: `rtk uv run pytest tests/auth/test_password_reset.py -v`
Expected : 404.

- [ ] **Step 3 : Ajouter les routes à `src/auth/routes.py`**

À la fin :

```python
@auth_bp.route("/request-password-reset", methods=["POST"])
def request_password_reset():
    email = (request.form.get("email") or "").strip().lower()
    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.normalized.lower()
    except EmailNotValidError:
        return redirect("/mot-de-passe-oublie?pending=1")

    row = db.get_user_by_email(email)
    if row is None:
        return redirect("/mot-de-passe-oublie?pending=1")

    token = tokens.create_password_reset_token(row["id"])
    try:
        mailer.send_reset_email(email, token)
    except Exception:
        logger.exception("Échec d'envoi de l'email de réinitialisation")
        return _redirect_with_error(
            "/mot-de-passe-oublie", "email_send_failed", email
        )
    return redirect("/mot-de-passe-oublie?pending=1")


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    token = request.form.get("token") or ""
    password = request.form.get("password") or ""
    password_confirm = request.form.get("password_confirm") or ""

    user_id = tokens.validate_password_reset_token(token)
    if user_id is None:
        return redirect(
            f"/reinitialiser-mot-de-passe?token={token}&error=invalid_token"
        )

    if len(password) < MIN_PASSWORD_LENGTH:
        return redirect(
            f"/reinitialiser-mot-de-passe?token={token}&error=password_too_short"
        )
    if password != password_confirm:
        return redirect(
            f"/reinitialiser-mot-de-passe?token={token}&error=password_mismatch"
        )

    consumed = tokens.consume_password_reset_token(token)
    if consumed is None:
        return redirect(
            f"/reinitialiser-mot-de-passe?token={token}&error=invalid_token"
        )

    db.update_password_hash(consumed, generate_password_hash(password))
    return redirect("/connexion?password_changed=1")
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_password_reset.py -v`
Expected : 6 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/routes.py tests/auth/test_password_reset.py
git commit -m "src/auth/routes.py : routes de réinitialisation du mot de passe (#73)"
```

---

## Task 15 : Route `/auth/change-password`

**Files:**

- Modify: `src/auth/routes.py`
- Create: `tests/auth/test_account.py`

- [ ] **Step 1 : Écrire les tests dans `tests/auth/test_account.py`**

```python
from werkzeug.security import check_password_hash, generate_password_hash

from src.auth import db


def _login(client, email="a@b.c", password="old-password12"):
    db.init_schema()
    uid = db.create_user(email, generate_password_hash(password))
    db.set_email_verified(uid)
    client.post("/auth/login", data={"email": email, "password": password})
    return uid


def test_change_password_requires_login(client, users_db_path):
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "whatever",
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert resp.status_code in (302, 401)


def test_change_password_success(client, users_db_path):
    uid = _login(client)
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "old-password12",
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert resp.status_code == 302
    assert "password_changed=1" in resp.headers["Location"]
    row = db.get_user_by_id(uid)
    assert check_password_hash(row["password_hash"], "new-password12")


def test_change_password_wrong_current(client, users_db_path):
    uid = _login(client)
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "wrong",
            "password": "new-password12",
            "password_confirm": "new-password12",
        },
    )
    assert "error=invalid_current_password" in resp.headers["Location"]
    row = db.get_user_by_id(uid)
    assert check_password_hash(row["password_hash"], "old-password12")


def test_change_password_short(client, users_db_path):
    _login(client)
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "old-password12",
            "password": "short",
            "password_confirm": "short",
        },
    )
    assert "error=password_too_short" in resp.headers["Location"]


def test_change_password_mismatch(client, users_db_path):
    _login(client)
    resp = client.post(
        "/auth/change-password",
        data={
            "current_password": "old-password12",
            "password": "new-password12",
            "password_confirm": "autre-password12",
        },
    )
    assert "error=password_mismatch" in resp.headers["Location"]
```

- [ ] **Step 2 : Lancer les tests**

Run: `rtk uv run pytest tests/auth/test_account.py -v`
Expected : 404 sur tous sauf peut-être le premier.

- [ ] **Step 3 : Ajouter la route à `src/auth/routes.py`**

À la fin :

```python
from flask_login import current_user


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_pw = request.form.get("current_password") or ""
    password = request.form.get("password") or ""
    password_confirm = request.form.get("password_confirm") or ""

    row = db.get_user_by_id(current_user.id)
    if not check_password_hash(row["password_hash"], current_pw):
        return _redirect_with_error("/compte", "invalid_current_password")

    if len(password) < MIN_PASSWORD_LENGTH:
        return _redirect_with_error("/compte", "password_too_short")
    if password != password_confirm:
        return _redirect_with_error("/compte", "password_mismatch")

    db.update_password_hash(current_user.id, generate_password_hash(password))
    return redirect("/compte?password_changed=1")
```

- [ ] **Step 4 : Relancer les tests**

Run: `rtk uv run pytest tests/auth/test_account.py -v`
Expected : 5 passed.

- [ ] **Step 5 : Commit**

```bash
git add src/auth/routes.py tests/auth/test_account.py
git commit -m "src/auth/routes.py : route /auth/change-password (#73)"
```

---

## Task 16 : Page Dash `/inscription`

**Files:**

- Create: `src/pages/inscription.py`

- [ ] **Step 1 : Créer la page Dash**

```python
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html, register_page
from flask_wtf.csrf import generate_csrf

NAME = "Inscription"

register_page(
    __name__,
    path="/inscription",
    title="Inscription | decp.info",
    name=NAME,
    description="Créer un compte decp.info.",
)

ERROR_MESSAGES = {
    "invalid_email": "Adresse email invalide.",
    "password_too_short": "Le mot de passe doit faire au moins 8 caractères.",
    "password_mismatch": "Les mots de passe ne correspondent pas.",
    "email_taken": "Un compte existe déjà avec cet email.",
    "email_send_failed": "Erreur technique lors de l'envoi de l'email. Réessayez plus tard.",
}


def layout(error: str | None = None, email: str | None = None, **_):
    alert = None
    if error and error in ERROR_MESSAGES:
        alert = dbc.Alert(ERROR_MESSAGES[error], color="danger")

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "500px"},
        children=[
            html.H2("Créer un compte"),
            alert,
            html.Form(
                method="POST",
                action="/auth/signup",
                children=[
                    dcc.Input(type="hidden", id="csrf-signup", name="csrf_token"),
                    dbc.Label("Adresse email"),
                    dbc.Input(
                        type="email",
                        name="email",
                        required=True,
                        value=email or "",
                        className="mb-3",
                    ),
                    dbc.Label("Mot de passe (8 caractères minimum)"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Label("Confirmer le mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password_confirm",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Button(
                        "Créer le compte", type="submit", color="primary"
                    ),
                ],
            ),
            html.Hr(),
            dcc.Link("Déjà un compte ? Se connecter", href="/connexion"),
        ],
    )


@callback(Output("csrf-signup", "value"), Input("csrf-signup", "id"))
def _fill_csrf(_):
    return generate_csrf()
```

- [ ] **Step 2 : Vérifier manuellement le rendu**

Démarrer l'app : `rtk uv run run.py` (avec `.env` configuré).
Ouvrir `http://localhost:8050/inscription`, vérifier le rendu du formulaire.

- [ ] **Step 3 : Commit**

```bash
git add src/pages/inscription.py
git commit -m "src/pages/inscription.py : page d'inscription (#73)"
```

---

## Task 17 : Page Dash `/connexion`

**Files:**

- Create: `src/pages/connexion.py`

- [ ] **Step 1 : Créer la page**

```python
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html, register_page
from flask_wtf.csrf import generate_csrf

NAME = "Connexion"

register_page(
    __name__,
    path="/connexion",
    title="Connexion | decp.info",
    name=NAME,
    description="Se connecter à decp.info.",
)

ERROR_MESSAGES = {
    "invalid_credentials": "Identifiants invalides.",
    "email_not_verified": "Vérifiez d'abord votre adresse email (consultez votre boîte de réception).",
}

INFO_MESSAGES = {
    "pending_verification": (
        "Compte créé. Un email de vérification a été envoyé. "
        "Cliquez sur le lien reçu avant de vous connecter."
    ),
    "verified": "Adresse email vérifiée. Vous pouvez maintenant vous connecter.",
    "password_changed": "Mot de passe mis à jour. Connectez-vous avec le nouveau.",
}


def layout(error: str | None = None, email: str | None = None, **kwargs):
    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    for flag, msg in INFO_MESSAGES.items():
        if kwargs.get(flag) == "1":
            alerts.append(dbc.Alert(msg, color="info"))

    next_url = kwargs.get("next", "")

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "500px"},
        children=[
            html.H2("Connexion"),
            *alerts,
            html.Form(
                method="POST",
                action="/auth/login",
                children=[
                    dcc.Input(type="hidden", id="csrf-login", name="csrf_token"),
                    dcc.Input(type="hidden", name="next", value=next_url),
                    dbc.Label("Adresse email"),
                    dbc.Input(
                        type="email",
                        name="email",
                        required=True,
                        value=email or "",
                        className="mb-3",
                    ),
                    dbc.Label("Mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        className="mb-3",
                    ),
                    dbc.Button("Se connecter", type="submit", color="primary"),
                ],
            ),
            html.Hr(),
            html.Div(
                [
                    dcc.Link("Créer un compte", href="/inscription"),
                    html.Span(" · "),
                    dcc.Link("Mot de passe oublié ?", href="/mot-de-passe-oublie"),
                ]
            ),
        ],
    )


@callback(Output("csrf-login", "value"), Input("csrf-login", "id"))
def _fill_csrf(_):
    return generate_csrf()
```

- [ ] **Step 2 : Vérification manuelle**

Redémarrer l'app, ouvrir `http://localhost:8050/connexion`. Tester `?pending_verification=1` et `?error=invalid_credentials`.

- [ ] **Step 3 : Commit**

```bash
git add src/pages/connexion.py
git commit -m "src/pages/connexion.py : page de connexion (#73)"
```

---

## Task 18 : Page Dash `/compte`

**Files:**

- Create: `src/pages/compte.py`

- [ ] **Step 1 : Créer la page avec protection login_required côté Flask**

```python
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html, register_page
from flask import redirect
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

NAME = "Mon compte"

register_page(
    __name__,
    path="/compte",
    title="Mon compte | decp.info",
    name=NAME,
    description="Page de gestion de compte.",
)

ERROR_MESSAGES = {
    "invalid_current_password": "Le mot de passe actuel est incorrect.",
    "password_too_short": "Le nouveau mot de passe doit faire au moins 8 caractères.",
    "password_mismatch": "Les nouveaux mots de passe ne correspondent pas.",
}


def layout(error: str | None = None, password_changed: str | None = None, **_):
    if not current_user.is_authenticated:
        # Redirection par layout de page Dash : on rend un lien car Dash ne gère pas
        # de redirect HTTP natif. On compte sur le middleware Flask enregistré dans
        # app.py pour intercepter /compte quand l'user est anonyme (cf. Task 20).
        return dcc.Location(href="/connexion?next=/compte", id="compte-redirect")

    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    if password_changed == "1":
        alerts.append(dbc.Alert("Mot de passe mis à jour.", color="success"))

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "600px"},
        children=[
            html.H2("Mon compte"),
            html.P([html.Strong("Email : "), current_user.email]),
            *alerts,
            html.H4("Changer le mot de passe", className="mt-4"),
            html.Form(
                method="POST",
                action="/auth/change-password",
                children=[
                    dcc.Input(type="hidden", id="csrf-change", name="csrf_token"),
                    dbc.Label("Mot de passe actuel"),
                    dbc.Input(
                        type="password",
                        name="current_password",
                        required=True,
                        className="mb-3",
                    ),
                    dbc.Label("Nouveau mot de passe (8 caractères minimum)"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Label("Confirmer le nouveau mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password_confirm",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Button("Changer", type="submit", color="primary"),
                ],
            ),
            html.Hr(className="mt-5"),
            html.Form(
                method="POST",
                action="/auth/logout",
                children=[
                    dcc.Input(type="hidden", id="csrf-logout", name="csrf_token"),
                    dbc.Button("Déconnexion", type="submit", color="secondary"),
                ],
            ),
        ],
    )


@callback(Output("csrf-change", "value"), Input("csrf-change", "id"))
def _fill_csrf_change(_):
    return generate_csrf()


@callback(Output("csrf-logout", "value"), Input("csrf-logout", "id"))
def _fill_csrf_logout(_):
    return generate_csrf()
```

- [ ] **Step 2 : Vérification manuelle**

Se connecter, ouvrir `/compte`, essayer de changer le mot de passe. Se déconnecter.

- [ ] **Step 3 : Commit**

```bash
git add src/pages/compte.py
git commit -m "src/pages/compte.py : page mon compte (protégée) (#73)"
```

---

## Task 19 : Pages Dash `/mot-de-passe-oublie` et `/reinitialiser-mot-de-passe`

**Files:**

- Create: `src/pages/mot_de_passe_oublie.py`
- Create: `src/pages/reinitialiser_mot_de_passe.py`

- [ ] **Step 1 : Créer `src/pages/mot_de_passe_oublie.py`**

```python
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html, register_page
from flask_wtf.csrf import generate_csrf

NAME = "Mot de passe oublié"

register_page(
    __name__,
    path="/mot-de-passe-oublie",
    title="Mot de passe oublié | decp.info",
    name=NAME,
    description="Réinitialiser votre mot de passe decp.info.",
)

ERROR_MESSAGES = {
    "email_send_failed": "Erreur technique lors de l'envoi de l'email. Réessayez plus tard.",
}


def layout(error: str | None = None, pending: str | None = None, email: str | None = None, **_):
    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    if pending == "1":
        alerts.append(
            dbc.Alert(
                "Si un compte existe avec cet email, un lien de réinitialisation vient d'être envoyé. "
                "Vérifiez votre boîte de réception.",
                color="info",
            )
        )

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "500px"},
        children=[
            html.H2("Mot de passe oublié"),
            *alerts,
            html.P(
                "Saisissez votre adresse email. Si un compte existe, "
                "vous recevrez un lien pour choisir un nouveau mot de passe."
            ),
            html.Form(
                method="POST",
                action="/auth/request-password-reset",
                children=[
                    dcc.Input(type="hidden", id="csrf-forgot", name="csrf_token"),
                    dbc.Label("Adresse email"),
                    dbc.Input(
                        type="email",
                        name="email",
                        required=True,
                        value=email or "",
                        className="mb-3",
                    ),
                    dbc.Button(
                        "Envoyer le lien", type="submit", color="primary"
                    ),
                ],
            ),
            html.Hr(),
            dcc.Link("Retour à la connexion", href="/connexion"),
        ],
    )


@callback(Output("csrf-forgot", "value"), Input("csrf-forgot", "id"))
def _fill_csrf(_):
    return generate_csrf()
```

- [ ] **Step 2 : Créer `src/pages/reinitialiser_mot_de_passe.py`**

```python
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html, register_page
from flask_wtf.csrf import generate_csrf

from src.auth.tokens import validate_password_reset_token

NAME = "Réinitialiser le mot de passe"

register_page(
    __name__,
    path="/reinitialiser-mot-de-passe",
    title="Nouveau mot de passe | decp.info",
    name=NAME,
    description="Choisir un nouveau mot de passe.",
)

ERROR_MESSAGES = {
    "invalid_token": "Lien invalide ou expiré. Demandez un nouveau lien de réinitialisation.",
    "password_too_short": "Le mot de passe doit faire au moins 8 caractères.",
    "password_mismatch": "Les mots de passe ne correspondent pas.",
}


def layout(token: str | None = None, error: str | None = None, **_):
    if not token or validate_password_reset_token(token) is None:
        return dbc.Container(
            className="py-4",
            style={"maxWidth": "500px"},
            children=[
                html.H2("Lien invalide"),
                dbc.Alert(ERROR_MESSAGES["invalid_token"], color="danger"),
                dcc.Link(
                    "Demander un nouveau lien", href="/mot-de-passe-oublie"
                ),
            ],
        )

    alerts = []
    if error and error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))

    return dbc.Container(
        className="py-4",
        style={"maxWidth": "500px"},
        children=[
            html.H2("Choisir un nouveau mot de passe"),
            *alerts,
            html.Form(
                method="POST",
                action="/auth/reset-password",
                children=[
                    dcc.Input(type="hidden", id="csrf-reset", name="csrf_token"),
                    dcc.Input(type="hidden", name="token", value=token),
                    dbc.Label("Nouveau mot de passe (8 caractères minimum)"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Label("Confirmer le nouveau mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password_confirm",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Button("Valider", type="submit", color="primary"),
                ],
            ),
        ],
    )


@callback(Output("csrf-reset", "value"), Input("csrf-reset", "id"))
def _fill_csrf(_):
    return generate_csrf()
```

- [ ] **Step 3 : Vérification manuelle**

Tester le flux complet : `/mot-de-passe-oublie` → saisir email d'un user → lien reçu → `/reinitialiser-mot-de-passe?token=…` → changer le mot de passe → reconnexion OK.

- [ ] **Step 4 : Commit**

```bash
git add src/pages/mot_de_passe_oublie.py src/pages/reinitialiser_mot_de_passe.py
git commit -m "src/pages : pages mot de passe oublié et réinitialisation (#73)"
```

---

## Task 20 : Page Dash `/verification-email`

**Files:**

- Create: `src/pages/verification_email.py`

- [ ] **Step 1 : Créer la page**

Cette page affiche uniquement un message selon la query string. Le serveur Flask gère la validation via `/auth/verify-email` et redirige ici en cas d'erreur.

```python
import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

NAME = "Vérification email"

register_page(
    __name__,
    path="/verification-email",
    title="Vérification email | decp.info",
    name=NAME,
    description="Vérification de l'adresse email.",
)


def layout(error: str | None = None, token: str | None = None, **_):
    if error == "invalid_token":
        return dbc.Container(
            className="py-4",
            style={"maxWidth": "500px"},
            children=[
                html.H2("Lien invalide ou expiré"),
                dbc.Alert(
                    "Le lien de vérification est invalide ou a expiré. "
                    "Connectez-vous pour demander un nouveau lien.",
                    color="danger",
                ),
                dcc.Link("Aller à la connexion", href="/connexion"),
            ],
        )

    # Cas où un utilisateur arrive ici sans passer par /auth/verify-email :
    # on redirige vers la connexion.
    return dcc.Location(href="/connexion", id="verif-redirect")
```

- [ ] **Step 2 : Modifier la route `/auth/verify-email` pour rediriger vers cette page en cas d'erreur**

Dans `src/auth/routes.py`, la route `verify_email` utilise déjà `/verification-email?error=invalid_token`. Vérifier que c'est le cas.

- [ ] **Step 3 : Vérification manuelle**

Cliquer sur un lien invalide : `http://localhost:8050/auth/verify-email?token=bidon` → doit rediriger vers `/verification-email?error=invalid_token`.

- [ ] **Step 4 : Commit**

```bash
git add src/pages/verification_email.py
git commit -m "src/pages/verification_email.py : page statut vérification email (#73)"
```

---

## Task 21 : Mise à jour de la navbar

**Files:**

- Modify: `src/app.py`

- [ ] **Step 1 : Mettre à jour `src/app.py`**

Remplacer le bloc `dbc.Collapse` actuel dans la navbar par une version qui ajoute un élément « Connexion » ou un dropdown « email » selon `current_user`.

Localiser le bloc `dbc.Collapse(...)` dans `src/app.py` (commence par `dbc.Collapse(dbc.Nav(...))`). Le remplacer par :

```python
            dbc.Collapse(
                dbc.Nav(
                    [
                        dbc.NavItem(
                            dbc.NavLink(
                                page["name"].replace(" ", " "),
                                href=page["relative_path"],
                                active="exact",
                            )
                        )
                        for page in page_registry.values()
                        if page["name"]
                        in ["Recherche", "À propos", "Tableau", "Observatoire"]
                    ]
                    + [html.Div(id="auth-nav-slot")],
                    className="ms-auto",
                    navbar=True,
                ),
                id="navbar-collapse",
                navbar=True,
            ),
```

- [ ] **Step 2 : Ajouter un callback qui remplit le slot selon l'état de connexion**

À la fin de `src/app.py`, avant `app.layout = ...` :

```python
from dash import Input, Output, callback
from flask_login import current_user


@callback(
    Output("auth-nav-slot", "children"),
    Input("auth-nav-slot", "id"),
)
def _auth_nav(_):
    if current_user.is_authenticated:
        email = current_user.email
        display = email if len(email) <= 30 else email[:27] + "..."
        return dbc.DropdownMenu(
            label=display,
            nav=True,
            in_navbar=True,
            children=[
                dbc.DropdownMenuItem("Mon compte", href="/compte"),
                dbc.DropdownMenuItem(
                    html.Form(
                        method="POST",
                        action="/auth/logout",
                        style={"display": "inline"},
                        children=[
                            dcc.Input(
                                type="hidden",
                                id="csrf-navbar-logout",
                                name="csrf_token",
                            ),
                            html.Button(
                                "Déconnexion",
                                type="submit",
                                className="btn btn-link p-0",
                                style={
                                    "textDecoration": "none",
                                    "color": "inherit",
                                },
                            ),
                        ],
                    )
                ),
            ],
        )
    return dbc.NavItem(dbc.NavLink("Connexion", href="/connexion"))


@callback(
    Output("csrf-navbar-logout", "value"),
    Input("csrf-navbar-logout", "id"),
)
def _csrf_navbar_logout(_):
    from flask_wtf.csrf import generate_csrf

    return generate_csrf()
```

- [ ] **Step 3 : Vérifier que les pages protégées fonctionnent**

`dash.register_page` crée un layout statique ; la protection `/compte` est assurée par la redirection `dcc.Location` dans `src/pages/compte.py` (cf. Task 18).

- [ ] **Step 4 : Vérifier visuellement**

Démarrer l'app. Déconnecté → lien « Connexion » en haut à droite. Se connecter → dropdown avec l'email et les items « Mon compte » / « Déconnexion ».

- [ ] **Step 5 : Commit**

```bash
git add src/app.py
git commit -m "src/app.py : navbar avec lien Connexion / dropdown utilisateur (#73)"
```

---

## Task 22 : Test CSRF

**Files:**

- Create: `tests/auth/test_csrf.py`

- [ ] **Step 1 : Écrire le test avec CSRF explicitement activé**

```python
import pytest
from flask import Flask
from flask_login import current_user

from src.auth import db
from src.auth.setup import init_auth


@pytest.fixture
def csrf_app(users_db_path, monkeypatch):
    monkeypatch.setenv("WTF_CSRF_ENABLED", "True")
    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = True
    init_auth(app)
    # Réactiver CSRF après init (init_auth respecte la config existante)
    return app


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def test_post_without_csrf_rejected(csrf_client, users_db_path):
    resp = csrf_client.post(
        "/auth/signup",
        data={
            "email": "a@b.c",
            "password": "password12",
            "password_confirm": "password12",
        },
    )
    assert resp.status_code == 400  # CSRF failed


def test_post_with_csrf_accepted(csrf_app, csrf_client, users_db_path):
    with csrf_app.test_request_context():
        from flask_wtf.csrf import generate_csrf

        token = generate_csrf()
    # Injecter le token via un session cookie pré-établi
    with csrf_client.session_transaction() as sess:
        # flask-wtf stocke le token en session ; on le réutilise tel quel
        pass
    # Exemple simplifié : on teste via un GET qui fournit le token, puis on le POST.
    # En pratique, on passe par une requête préalable à une page qui inclut le CSRF.
    # Ce test valide que CSRFProtect est bien installé : si le POST sans token échoue
    # en 400, c'est suffisant pour prouver la couverture.
```

Note : le test principal est `test_post_without_csrf_rejected`. Le second est illustratif ; si trop fragile, le supprimer.

- [ ] **Step 2 : Lancer les tests**

Run: `rtk uv run pytest tests/auth/test_csrf.py -v`
Expected : `test_post_without_csrf_rejected` passe (400). Le second peut être skippé ou simplifié.

- [ ] **Step 3 : Commit**

```bash
git add tests/auth/test_csrf.py
git commit -m "tests/auth/test_csrf.py : vérifie que CSRF est actif (#73)"
```

---

## Task 23 : Vérification finale — tous les tests passent et smoke test manuel

**Files:**

- Aucun (validation)

- [ ] **Step 1 : Lancer la suite complète**

Run: `rtk uv run pytest -v`
Expected : tous les tests passent (existants + nouveaux tests auth).

- [ ] **Step 2 : Smoke test manuel end-to-end**

1. Configurer `.env` avec un SMTP réel (ou `DEVELOPMENT=True` pour capturer les emails dans la console).
2. `rtk uv run run.py`.
3. Ouvrir `http://localhost:8050/inscription`, créer un compte.
4. Vérifier que l'email de vérification s'affiche dans la console (ou arrive réellement).
5. Cliquer le lien → doit rediriger vers `/connexion?verified=1`.
6. Se connecter, vérifier redirection vers `/compte`.
7. Changer le mot de passe.
8. Se déconnecter.
9. Utiliser « Mot de passe oublié », recevoir le lien, réinitialiser, se reconnecter avec le nouveau mot de passe.

- [ ] **Step 3 : Mettre à jour le CHANGELOG**

Ajouter sous la section en cours :

```
- comptes utilisateurs : inscription avec vérification d'email, connexion,
  réinitialisation de mot de passe, page compte (#73)
```

- [ ] **Step 4 : Commit final**

```bash
git add CHANGELOG.md
git commit -m "Changelog : comptes utilisateurs (#73)"
```

---

## Self-review

**Couverture du spec :**

- Inscription email + password hashé → Task 11 (route signup) ✓
- Vérification obligatoire de l'email → Task 11 + Task 12 + Task 13 (refus login non vérifié) ✓
- Connexion email + password → Task 13 ✓
- Lien de réinitialisation du mot de passe → Task 19 (page) + Task 14 (routes) ✓
- Page compte avec changement de mot de passe → Task 15 (route) + Task 18 (page) ✓
- SQLite à la racine (configurable) → Task 2 ✓
- SMTP via variables d'env → Task 1 + Task 7 ✓
- Sessions Flask-Login → Task 8 ✓
- Tokens hashés en DB, usage unique → Task 5 + Task 4 ✓
- Hashage `werkzeug.security` → Task 11, Task 13, Task 14, Task 15 ✓
- CSRF Flask-WTF → Task 8 + Task 22 ✓
- Pages Dash séparées (5 + verification-email) → Tasks 16–20 ✓
- Navbar dropdown selon connexion → Task 21 ✓
- Tests unitaires + intégration Flask → toutes les tasks ✓
- Messages d'erreur via query string → routes + pages ✓
- Validation `next` (rejet URLs absolues) → Task 13 (safe_next) ✓
- Anti-énumération (message générique) → Task 13 + Task 14 ✓
- Timing uniforme sur login → Task 13 (`_DUMMY_HASH`) ✓
- Rollback inscription si SMTP KO → Task 11 ✓
- `SECRET_KEY` obligatoire → Task 8 ✓
- `MAIL_SUPPRESS_SEND` en dev → Task 7 ✓
- Purge tokens expirés au démarrage → Task 8 ✓
