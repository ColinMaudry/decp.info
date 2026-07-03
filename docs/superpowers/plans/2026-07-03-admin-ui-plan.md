# Panneau admin interne (`/admin`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal admin panel at `/admin` for support/debugging — list users, view a user's full subscription history, correct a subscription status manually, all restricted to a single `ADMIN_EMAIL` and logged to an `admin_actions` audit table also viewable at `/admin/journal`.

**Architecture:** Dash pages (`register_page`) for reads, one Flask blueprint (`src/admin/routes.py`) for the single write action, both guarded by a shared `is_admin()` check. Mirrors the existing `/compte/*` (Dash) + `/auth/*` (Flask blueprint) split.

**Tech Stack:** Dash 3.4, dash-bootstrap-components, Flask, flask-login, flask-wtf (CSRFProtect, already global), sqlite3 (raw, no ORM).

**Spec:** `docs/superpowers/specs/2026-07-03-admin-ui-design.md`

## Global Constraints

- Valid subscription statuses (from `src/subscriptions/webhooks.py:map_subscription`): `active`, `trial`, `cancelled`, `expired`, `pending`.
- `ADMIN_EMAIL` is a single email, compared case-insensitively. No multi-admin support in this lot.
- Access guard (`is_admin()` false) always returns/aborts **404**, never a redirect — applies uniformly to anonymous and authenticated-non-admin.
- CSRF protection is already global (`CSRFProtect(app)`, `src/auth/setup.py:53`) — no custom CSRF code, just the existing hidden `csrf_token` input pattern.
- `dash_table.DataTable` uses `filter_action="native"`, `sort_action="native"`, `page_action="native"`, `page_size=20` everywhere in this feature (no custom/server-side filtering).
- Run tests with `uv run pytest` (venv activation via the Bash tool doesn't reliably update `PATH` in this environment).
- `sqlite3` connections here are autocommit (`isolation_level=None`, see `src/auth/db.py:56`) — new DB functions must NOT call `conn.commit()`, matching every existing function in `src/auth/db.py` and `src/subscriptions/db.py`.

---

### Task 1: `list_users()` in the auth DB layer

**Files:**

- Modify: `src/auth/db.py` (add after `get_user_by_id`, around line 148)
- Test: `tests/auth/test_db.py`

**Interfaces:**

- Produces: `list_users(limit: int = 1000) -> list[sqlite3.Row]` — all users, most recently created first, capped at `limit`.

- [ ] **Step 1: Write the failing test**

Add to `tests/auth/test_db.py`:

```python
def test_list_users_orders_by_created_at_desc(users_db_path):
    from src.auth import db

    db.init_schema()
    db.create_user("first@ex.fr", "hash")
    db.create_user("second@ex.fr", "hash")

    rows = db.list_users()

    assert [r["email"] for r in rows] == ["second@ex.fr", "first@ex.fr"]


def test_list_users_respects_limit(users_db_path):
    from src.auth import db

    db.init_schema()
    for i in range(3):
        db.create_user(f"user{i}@ex.fr", "hash")

    rows = db.list_users(limit=2)

    assert len(rows) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/auth/test_db.py -k list_users -v`
Expected: FAIL with `AttributeError: module 'src.auth.db' has no attribute 'list_users'`

- [ ] **Step 3: Implement `list_users`**

In `src/auth/db.py`, immediately after `get_user_by_id` (line 148):

```python
def list_users(limit: int = 1000) -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute("SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
        .fetchall()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_db.py -k list_users -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/auth/db.py tests/auth/test_db.py
git commit -m "feat(admin): add list_users() to auth DB layer"
```

---

### Task 2: Subscription DB additions — history, status override, statuses constant

**Files:**

- Modify: `src/subscriptions/db.py` (add after `get_current`, around line 124, and after `_get_state`, around line 210)
- Test: `tests/subscriptions/test_db.py`

**Interfaces:**

- Produces: `SUBSCRIPTION_STATUSES: tuple[str, ...]` = `("active", "trial", "cancelled", "expired", "pending")`
- Produces: `list_by_user(user_id: int) -> list[sqlite3.Row]` — all subscriptions for a user, most recent (`id DESC`) first.
- Produces: `set_status(subscription_id: int, status: str) -> None` — overwrites `status` and `updated_at`.
- Produces: `get_subscriber_state(user_id: int) -> sqlite3.Row | None` — public wrapper around the existing private `_get_state`.
- Consumes: `get_conn()` from `src.auth.db` (already imported), `_now()` (already defined in this module), `create_pending(user_id, customer_handle, plan, prix_ht=None) -> (handle, subscription_id)` (already exists, used by the test).

- [ ] **Step 1: Write the failing tests**

Add to `tests/subscriptions/test_db.py`:

```python
def test_list_by_user_returns_most_recent_first(users_db_path):
    uid = _make_user()
    db.init_schema()
    _handle1, sub_id1 = db.create_pending(uid, "cust-1", "simple")
    _handle2, sub_id2 = db.create_pending(uid, "cust-1", "soutien")

    rows = db.list_by_user(uid)

    assert [r["id"] for r in rows] == [sub_id2, sub_id1]


def test_set_status_updates_status(users_db_path):
    uid = _make_user()
    db.init_schema()
    _handle, sub_id = db.create_pending(uid, "cust-1", "simple")

    db.set_status(sub_id, "active")

    row = db.get_current(uid)
    assert row["status"] == "active"


def test_get_subscriber_state_returns_row_after_create_pending(users_db_path):
    uid = _make_user()
    db.init_schema()
    db.create_pending(uid, "cust-1", "simple")

    state = db.get_subscriber_state(uid)

    assert state is not None
    assert state["user_id"] == uid


def test_get_subscriber_state_returns_none_for_unknown_user(users_db_path):
    db.init_schema()
    assert db.get_subscriber_state(999999) is None


def test_subscription_statuses_constant():
    assert db.SUBSCRIPTION_STATUSES == (
        "active",
        "trial",
        "cancelled",
        "expired",
        "pending",
    )
```

(`_make_user` and the `users_db_path` fixture already exist in this file/its `conftest.py` — see `tests/subscriptions/test_db.py:16`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/subscriptions/test_db.py -k "list_by_user or set_status or get_subscriber_state or subscription_statuses" -v`
Expected: FAIL with `AttributeError` for each missing symbol

- [ ] **Step 3: Implement the additions**

In `src/subscriptions/db.py`, immediately after `get_current` (after line 123, before `get_by_handle`):

```python
SUBSCRIPTION_STATUSES = ("active", "trial", "cancelled", "expired", "pending")


def list_by_user(user_id: int) -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        .fetchall()
    )


def set_status(subscription_id: int, status: str) -> None:
    get_conn().execute(
        "UPDATE subscriptions SET status = ?, updated_at = ? WHERE id = ?",
        (status, _now(), subscription_id),
    )
```

Then, immediately after `_get_state` (after line 210, before `freeze_votes_cursor`):

```python
def get_subscriber_state(user_id: int) -> sqlite3.Row | None:
    return _get_state(user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/subscriptions/test_db.py -k "list_by_user or set_status or get_subscriber_state or subscription_statuses" -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/db.py tests/subscriptions/test_db.py
git commit -m "feat(admin): add subscription history, status override, and statuses constant"
```

---

### Task 3: Audit log table + `src/admin/db.py`

**Files:**

- Modify: `src/migrations.py` (append to `_MIGRATIONS`)
- Create: `src/admin/__init__.py` (empty)
- Create: `src/admin/db.py`
- Create: `tests/admin/__init__.py` (empty)
- Create: `tests/admin/conftest.py`
- Create: `tests/admin/test_db.py`

**Interfaces:**

- Produces: table `admin_actions(id, admin_email, action, target_user_id, details, created_at)`.
- Produces: `log_action(admin_email: str, action: str, target_user_id: int | None, details: str | None) -> None`
- Produces: `list_actions(limit: int = 200) -> list[sqlite3.Row]` — most recent (`id DESC`) first.
- Consumes: `get_conn()` from `src.auth.db`, `apply_pending()` from `src.migrations`.

- [ ] **Step 1: Add the migration**

In `src/migrations.py`, append to `_MIGRATIONS` (after the `0005_...` entry):

```python
    (
        "0006_create_admin_actions",
        "CREATE TABLE IF NOT EXISTS admin_actions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "admin_email TEXT NOT NULL, "
        "action TEXT NOT NULL, "
        "target_user_id INTEGER, "
        "details TEXT, "
        "created_at TEXT NOT NULL)",
    ),
```

- [ ] **Step 2: Create the test conftest**

Create `tests/admin/__init__.py` (empty file).

Create `tests/admin/conftest.py`:

```python
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

- [ ] **Step 3: Write the failing test**

Create `tests/admin/test_db.py`:

```python
from src.admin import db as admin_db
from src.auth.db import init_schema
from src.migrations import apply_pending


def _setup():
    init_schema()
    apply_pending()


def test_log_action_then_list_actions_returns_it(users_db_path):
    _setup()

    admin_db.log_action("admin@ex.fr", "subscription_status_change", 42, "active → cancelled")

    rows = admin_db.list_actions()
    assert len(rows) == 1
    assert rows[0]["admin_email"] == "admin@ex.fr"
    assert rows[0]["action"] == "subscription_status_change"
    assert rows[0]["target_user_id"] == 42
    assert rows[0]["details"] == "active → cancelled"


def test_list_actions_most_recent_first(users_db_path):
    _setup()

    admin_db.log_action("admin@ex.fr", "action_one", None, None)
    admin_db.log_action("admin@ex.fr", "action_two", None, None)

    rows = admin_db.list_actions()
    assert [r["action"] for r in rows] == ["action_two", "action_one"]


def test_list_actions_respects_limit(users_db_path):
    _setup()

    for i in range(3):
        admin_db.log_action("admin@ex.fr", f"action_{i}", None, None)

    rows = admin_db.list_actions(limit=2)
    assert len(rows) == 2
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/admin/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.admin'`

- [ ] **Step 5: Implement `src/admin/db.py`**

Create `src/admin/__init__.py` (empty file).

Create `src/admin/db.py`:

```python
import sqlite3
from datetime import datetime, timezone

from src.auth.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_action(
    admin_email: str, action: str, target_user_id: int | None, details: str | None
) -> None:
    get_conn().execute(
        "INSERT INTO admin_actions (admin_email, action, target_user_id, details, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (admin_email, action, target_user_id, details, _now()),
    )


def list_actions(limit: int = 200) -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute("SELECT * FROM admin_actions ORDER BY id DESC LIMIT ?", (limit,))
        .fetchall()
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/admin/test_db.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add src/migrations.py src/admin/__init__.py src/admin/db.py tests/admin/__init__.py tests/admin/conftest.py tests/admin/test_db.py
git commit -m "feat(admin): add admin_actions audit table and log/list functions"
```

---

### Task 4: Access guard — `is_admin()`

**Files:**

- Create: `src/admin/guard.py`
- Create: `tests/admin/test_guard.py`

**Interfaces:**

- Produces: `is_admin() -> bool` — `True` only if `ADMIN_EMAIL` is set, `current_user.is_authenticated`, and `current_user.email` matches case-insensitively.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_guard.py`:

```python
from unittest.mock import patch

from src.admin import guard


def _fake_user(email: str, authenticated: bool = True):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    user.email = email
    return user


def test_is_admin_true_for_matching_email(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.fr")
    with patch("src.admin.guard.current_user", _fake_user("admin@ex.fr")):
        assert guard.is_admin() is True


def test_is_admin_true_case_insensitive(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "Admin@Ex.fr")
    with patch("src.admin.guard.current_user", _fake_user("admin@ex.fr")):
        assert guard.is_admin() is True


def test_is_admin_false_for_different_email(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.fr")
    with patch("src.admin.guard.current_user", _fake_user("someone@ex.fr")):
        assert guard.is_admin() is False


def test_is_admin_false_for_anonymous(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.fr")
    with patch(
        "src.admin.guard.current_user", _fake_user("admin@ex.fr", authenticated=False)
    ):
        assert guard.is_admin() is False


def test_is_admin_false_when_admin_email_unset(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    with patch("src.admin.guard.current_user", _fake_user("admin@ex.fr")):
        assert guard.is_admin() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/admin/test_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.admin.guard'`

- [ ] **Step 3: Implement `src/admin/guard.py`**

```python
import os

from flask_login import current_user


def is_admin() -> bool:
    admin_email = os.getenv("ADMIN_EMAIL")
    return bool(
        admin_email
        and current_user.is_authenticated
        and current_user.email.lower() == admin_email.lower()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/admin/test_guard.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/admin/guard.py tests/admin/test_guard.py
git commit -m "feat(admin): add is_admin() access guard"
```

---

### Task 5: Mutation route — `POST /admin/actions/subscription-status`

**Files:**

- Create: `src/admin/routes.py`
- Modify: `src/auth/setup.py` (register blueprint)
- Modify: `.template.env` (add `ADMIN_EMAIL`)
- Modify: `tests/admin/conftest.py` (add Flask app/client fixtures)
- Create: `tests/admin/test_routes.py`

**Interfaces:**

- Produces: Flask blueprint `admin_bp` (`url_prefix="/admin/actions"`), route `POST /subscription-status`.
- Consumes: `is_admin()` (Task 4), `SUBSCRIPTION_STATUSES`, `get_current`, `set_status` (Task 2), `log_action` (Task 3).

- [ ] **Step 1: Extend the test conftest**

In `tests/admin/conftest.py`, add (after the existing `users_db_path` fixture):

```python
@pytest.fixture
def admin_app(users_db_path, monkeypatch):
    from flask import Flask

    from src.auth.setup import init_auth
    from src.subscriptions.setup import init_subscriptions

    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    monkeypatch.setenv("FRISBII_WEBHOOK_SECRET", "s3cr3t")
    flask_app = Flask(__name__)
    flask_app.config["WTF_CSRF_ENABLED"] = False
    init_auth(flask_app)
    init_subscriptions(flask_app)
    return flask_app


@pytest.fixture
def admin_client(admin_app):
    return admin_app.test_client()


@pytest.fixture
def logged_in_admin_client(admin_app, monkeypatch):
    from src.auth import db as auth_db

    monkeypatch.setenv("ADMIN_EMAIL", "admin@ex.fr")
    uid = auth_db.create_user("admin@ex.fr", "hash")
    auth_db.set_email_verified(uid)
    client = admin_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True
    return client, uid
```

This mirrors `tests/subscriptions/conftest.py:62-106` (`sub_app`/`logged_in_client`).

- [ ] **Step 2: Write the failing tests**

Create `tests/admin/test_routes.py`:

```python
from src.auth import db as auth_db
from src.subscriptions import db as sub_db


def _make_target_with_subscription():
    uid = auth_db.create_user("target@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")
    return uid, sub_id


def test_subscription_status_requires_admin(admin_client):
    resp = admin_client.post(
        "/admin/actions/subscription-status",
        data={"user_id": "1", "subscription_id": "1", "status": "active"},
    )
    assert resp.status_code == 404


def test_subscription_status_rejects_invalid_status(logged_in_admin_client):
    client, _admin_uid = logged_in_admin_client
    uid, sub_id = _make_target_with_subscription()

    resp = client.post(
        "/admin/actions/subscription-status",
        data={"user_id": str(uid), "subscription_id": str(sub_id), "status": "bogus"},
    )

    assert resp.status_code == 302
    assert resp.headers["Location"] == f"/admin/user/{uid}?error=invalid_status"
    assert sub_db.get_current(uid)["status"] == "pending"


def test_subscription_status_rejects_mismatched_subscription(logged_in_admin_client):
    client, _admin_uid = logged_in_admin_client
    uid, _sub_id = _make_target_with_subscription()
    other_uid, other_sub_id = _make_target_with_subscription()

    resp = client.post(
        "/admin/actions/subscription-status",
        data={
            "user_id": str(uid),
            "subscription_id": str(other_sub_id),
            "status": "active",
        },
    )

    assert resp.status_code == 302
    assert resp.headers["Location"] == f"/admin/user/{uid}?error=invalid_status"
    assert sub_db.get_current(other_uid)["status"] == "pending"


def test_subscription_status_success_updates_and_logs(logged_in_admin_client):
    from src.admin.db import list_actions

    client, _admin_uid = logged_in_admin_client
    uid, sub_id = _make_target_with_subscription()

    resp = client.post(
        "/admin/actions/subscription-status",
        data={"user_id": str(uid), "subscription_id": str(sub_id), "status": "active"},
    )

    assert resp.status_code == 302
    assert resp.headers["Location"] == f"/admin/user/{uid}?status_changed=1"
    assert sub_db.get_current(uid)["status"] == "active"

    actions = list_actions()
    assert len(actions) == 1
    assert actions[0]["action"] == "subscription_status_change"
    assert actions[0]["target_user_id"] == uid
    assert actions[0]["details"] == "pending → active"
    assert actions[0]["admin_email"] == "admin@ex.fr"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/admin/test_routes.py -v`
Expected: FAIL — `admin_client`/`logged_in_admin_client` fixtures raise `ModuleNotFoundError: No module named 'src.admin.routes'` (via `init_auth` once it tries to import it in Step 5) or `404`/`ImportError` depending on order; before Step 5, `test_subscription_status_requires_admin` will fail with a connection/404-mismatch since the blueprint doesn't exist yet (real 404 from Flask's default routing, not from `is_admin()` — acceptable coincidence, but the other three tests will fail).

- [ ] **Step 4: Implement `src/admin/routes.py`**

```python
from flask import Blueprint, abort, redirect, request
from flask_login import current_user

from src.admin.db import log_action
from src.admin.guard import is_admin
from src.subscriptions.db import SUBSCRIPTION_STATUSES, get_current, set_status

admin_bp = Blueprint("admin", __name__, url_prefix="/admin/actions")


@admin_bp.before_request
def _require_admin():
    if not is_admin():
        abort(404)


@admin_bp.route("/subscription-status", methods=["POST"])
def subscription_status():
    user_id = request.form.get("user_id", type=int)
    subscription_id = request.form.get("subscription_id", type=int)
    status = request.form.get("status", "")

    if user_id is None or subscription_id is None:
        abort(400)

    current = get_current(user_id)
    if (
        status not in SUBSCRIPTION_STATUSES
        or current is None
        or current["id"] != subscription_id
    ):
        return redirect(f"/admin/user/{user_id}?error=invalid_status")

    old_status = current["status"]
    set_status(subscription_id, status)
    log_action(
        current_user.email,
        "subscription_status_change",
        user_id,
        f"{old_status} → {status}",
    )
    return redirect(f"/admin/user/{user_id}?status_changed=1")
```

- [ ] **Step 5: Register the blueprint**

In `src/auth/setup.py`, immediately after `app.register_blueprint(auth_bp)` (currently the line right after the `from src.auth.routes import auth_bp` block):

```python
    from src.auth.routes import auth_bp

    app.register_blueprint(auth_bp)

    from src.admin.routes import admin_bp

    app.register_blueprint(admin_bp)
```

- [ ] **Step 6: Add `ADMIN_EMAIL` to `.template.env`**

In `.template.env`, add a new section after the "Comptes utilisateurs" block (after `APP_BASE_URL=http://localhost:8050`):

```
# Panneau admin interne (accès à /admin, protégé par cette adresse)
ADMIN_EMAIL=
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/admin/test_routes.py -v`
Expected: 4 passed

- [ ] **Step 8: Commit**

```bash
git add src/admin/routes.py src/auth/setup.py .template.env tests/admin/conftest.py tests/admin/test_routes.py
git commit -m "feat(admin): add subscription-status mutation route"
```

---

### Task 6: Shared page chrome + `/admin` list page

**Files:**

- Create: `src/pages/admin/__init__.py` (empty)
- Create: `src/pages/admin/_shell.py`
- Create: `src/pages/admin/liste.py`

**Interfaces:**

- Produces: `not_admin() -> Component`, `admin_nav(active: str) -> Component` (in `_shell.py`), reused by Tasks 7 and 8.
- Consumes: `is_admin()` (Task 4), `list_users()` (Task 1), `get_current()` (existing).

- [ ] **Step 1: Create the package and shared shell**

Create `src/pages/admin/__init__.py` (empty file).

Create `src/pages/admin/_shell.py`:

```python
import dash_bootstrap_components as dbc
from dash import html


def not_admin():
    return html.Div(
        html.H2("404", id="admin-404-heading"), className="py-5 text-center"
    )


def admin_nav(active: str):
    return dbc.Nav(
        [
            dbc.NavLink("Utilisateurs", href="/admin", active=(active == "liste")),
            dbc.NavLink(
                "Journal", href="/admin/journal", active=(active == "journal")
            ),
        ],
        pills=True,
        class_name="mb-4",
    )
```

(`html.H2` here, not `H1` — the navbar already renders a global `<h1>colibre</h1>` logo on every page, see `src/app.py:221`; a second `<h1>` would make text-based Selenium assertions ambiguous.)

- [ ] **Step 2: Create the list page**

Create `src/pages/admin/liste.py`:

```python
import dash_bootstrap_components as dbc
from dash import dash_table, html, register_page

from src.admin.guard import is_admin
from src.auth.db import list_users
from src.pages.admin._shell import admin_nav, not_admin
from src.subscriptions.db import get_current

register_page(
    __name__,
    path="/admin",
    title="Panneau admin | colibre",
    name="Admin",
    description="Panneau d'administration interne.",
)


def _rows():
    rows = []
    for user in list_users():
        sub = get_current(user["id"])
        rows.append(
            {
                "email": user["email"],
                "vérifié": "oui" if user["email_verified"] else "non",
                "plan": sub["plan"] if sub else "",
                "statut": sub["status"] if sub else "",
                "créé le": user["created_at"],
                "voir": f"[Voir](/admin/user/{user['id']})",
            }
        )
    return rows


def layout(**_):
    if not is_admin():
        return not_admin()
    return dbc.Container(
        [
            html.H2("Panneau admin"),
            admin_nav("liste"),
            dash_table.DataTable(
                id="admin-users-table",
                columns=[
                    {"name": "Email", "id": "email"},
                    {"name": "Vérifié", "id": "vérifié"},
                    {"name": "Plan", "id": "plan"},
                    {"name": "Statut", "id": "statut"},
                    {"name": "Créé le", "id": "créé le"},
                    {"name": "", "id": "voir", "presentation": "markdown"},
                ],
                data=_rows(),
                filter_action="native",
                sort_action="native",
                page_action="native",
                page_size=20,
                markdown_options={"link_target": "_self"},
            ),
        ],
        fluid=True,
        className="py-4",
    )
```

- [ ] **Step 3: Sanity-check the layout renders without a browser**

Run:

```bash
uv run python -c "
import os
os.environ.setdefault('USERS_DB_PATH', 'tests/users.test.sqlite')
os.environ.setdefault('SECRET_KEY', 'x')
os.environ['ADMIN_EMAIL'] = 'admin@ex.fr'
from unittest.mock import patch
from flask import Flask
from src.auth.setup import init_auth
app = Flask(__name__)
app.config['WTF_CSRF_ENABLED'] = False
init_auth(app)
with app.test_request_context():
    import src.pages.admin.liste as liste
    admin = type('U', (), {'is_authenticated': True, 'email': 'admin@ex.fr'})()
    with patch('src.admin.guard.current_user', admin):
        component = liste.layout()
    print(type(component))
"
```

Expected: prints `<class 'dash_bootstrap_components._components.Container.Container'>` with no traceback. (This does not assert content — that's covered by Task 9's Selenium test — it just proves the module imports and `layout()` executes without error, catching typos/import errors before the browser test.)

- [ ] **Step 4: Commit**

```bash
git add src/pages/admin/__init__.py src/pages/admin/_shell.py src/pages/admin/liste.py
git commit -m "feat(admin): add /admin user list page"
```

---

### Task 7: `/admin/user/<user_id>` detail page

**Files:**

- Create: `src/pages/admin/detail.py`

**Interfaces:**

- Consumes: `not_admin`, `admin_nav` (Task 6), `is_admin` (Task 4), `get_user_by_id` (existing), `get_current`, `list_by_user`, `get_subscriber_state`, `SUBSCRIPTION_STATUSES` (Task 2).

- [ ] **Step 1: Create the detail page**

Create `src/pages/admin/detail.py`:

```python
import dash_bootstrap_components as dbc
from dash import dcc, html, register_page

from src.admin.guard import is_admin
from src.auth.db import get_user_by_id
from src.pages.admin._shell import admin_nav, not_admin
from src.subscriptions.db import (
    SUBSCRIPTION_STATUSES,
    get_current,
    get_subscriber_state,
    list_by_user,
)

register_page(
    __name__,
    path_template="/admin/user/<user_id>",
    title="Détail utilisateur | colibre",
    name="Détail utilisateur",
    description="Panneau d'administration interne.",
)

ERROR_MESSAGES = {"invalid_status": "Statut invalide ou abonnement introuvable."}
SUCCESS_MESSAGES = {"status_changed": "Statut de l'abonnement mis à jour."}


def _parse_user_id(user_id):
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def _not_found():
    return dbc.Container(
        [
            html.H2("Panneau admin"),
            admin_nav("liste"),
            dbc.Alert("Utilisateur introuvable.", color="warning"),
        ],
        fluid=True,
        className="py-4",
    )


def _csrf():
    return dcc.Input(
        type="hidden",
        id={"type": "csrf-input", "index": "admin-status"},
        name="csrf_token",
    )


def _account_section(user):
    return html.Div(
        [
            html.H4("Compte"),
            html.P([html.Strong("Email : "), user["email"]]),
            html.P(
                [
                    html.Strong("Vérifié : "),
                    "oui" if user["email_verified"] else "non",
                ]
            ),
            html.P([html.Strong("SIRET : "), user["siret"] or "—"]),
            html.P([html.Strong("Créé le : "), user["created_at"]]),
        ]
    )


def _state_section(user_id):
    state = get_subscriber_state(user_id)
    return html.Div(
        [
            html.H4("État abonné", className="mt-4"),
            html.P(
                [
                    html.Strong("Solde de votes : "),
                    str(state["votes_balance"] if state else 0),
                ]
            ),
            html.P(
                [
                    html.Strong("Essai utilisé : "),
                    "oui" if state and state["trial_used"] else "non",
                ]
            ),
        ]
    )


def _history_section(user_id, current_id):
    rows = []
    for sub in list_by_user(user_id):
        badge = (
            dbc.Badge("actuel", color="primary", className="ms-2")
            if sub["id"] == current_id
            else None
        )
        rows.append(
            html.Tr(
                [
                    html.Td([sub["plan"] or "—", badge]),
                    html.Td(sub["status"] or "—"),
                    html.Td(sub["prix_ht"] if sub["prix_ht"] is not None else "—"),
                    html.Td(sub["current_period_end"] or "—"),
                    html.Td(sub["created_at"]),
                ]
            )
        )
    return html.Div(
        [
            html.H4("Historique des abonnements", className="mt-4"),
            dbc.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th(h)
                                for h in (
                                    "Plan",
                                    "Statut",
                                    "Prix HT",
                                    "Fin de période",
                                    "Créé le",
                                )
                            ]
                        )
                    ),
                    html.Tbody(rows),
                ],
                bordered=True,
                size="sm",
            ),
        ]
    )


def _status_form(user_id, current):
    if current is None:
        return html.Div()
    return html.Div(
        [
            html.H4("Changer le statut de l'abonnement courant", className="mt-4"),
            html.Form(
                method="POST",
                action="/admin/actions/subscription-status",
                children=[
                    _csrf(),
                    dcc.Input(type="hidden", name="user_id", value=str(user_id)),
                    dcc.Input(
                        type="hidden", name="subscription_id", value=str(current["id"])
                    ),
                    dbc.Select(
                        id="admin-status-select",
                        name="status",
                        options=[
                            {"label": s, "value": s} for s in SUBSCRIPTION_STATUSES
                        ],
                        value=current["status"],
                        className="mb-3",
                        style={"maxWidth": "300px"},
                    ),
                    dbc.Button("Mettre à jour le statut", type="submit", color="primary"),
                ],
            ),
        ]
    )


def layout(user_id=None, error=None, status_changed=None, **_):
    if not is_admin():
        return not_admin()

    uid = _parse_user_id(user_id)
    user = get_user_by_id(uid) if uid is not None else None
    if user is None:
        return _not_found()

    alerts = []
    if error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    if status_changed == "1":
        alerts.append(dbc.Alert(SUCCESS_MESSAGES["status_changed"], color="success"))

    current = get_current(user["id"])

    return dbc.Container(
        [
            html.H2("Panneau admin"),
            admin_nav("liste"),
            *alerts,
            _account_section(user),
            _state_section(user["id"]),
            _history_section(user["id"], current["id"] if current else None),
            _status_form(user["id"], current),
        ],
        fluid=True,
        className="py-4",
    )
```

- [ ] **Step 2: Sanity-check the layout renders without a browser**

Run:

```bash
uv run python -c "
import os
os.environ.setdefault('USERS_DB_PATH', 'tests/users.test.sqlite')
os.environ.setdefault('SECRET_KEY', 'x')
os.environ['ADMIN_EMAIL'] = 'admin@ex.fr'
from unittest.mock import patch
from flask import Flask
from src.auth.setup import init_auth
app = Flask(__name__)
app.config['WTF_CSRF_ENABLED'] = False
init_auth(app)
with app.test_request_context():
    import src.pages.admin.detail as detail
    admin = type('U', (), {'is_authenticated': True, 'email': 'admin@ex.fr'})()
    with patch('src.admin.guard.current_user', admin):
        print(type(detail.layout(user_id='999999')))
"
```

Expected: prints the `Container` type for the not-found branch, no traceback.

- [ ] **Step 3: Commit**

```bash
git add src/pages/admin/detail.py
git commit -m "feat(admin): add /admin/user/<user_id> detail page"
```

---

### Task 8: `/admin/journal` audit log page

**Files:**

- Create: `src/pages/admin/journal.py`

**Interfaces:**

- Consumes: `not_admin`, `admin_nav` (Task 6), `is_admin` (Task 4), `list_actions` (Task 3).

- [ ] **Step 1: Create the journal page**

Create `src/pages/admin/journal.py`:

```python
import dash_bootstrap_components as dbc
from dash import dash_table, html, register_page

from src.admin.db import list_actions
from src.admin.guard import is_admin
from src.pages.admin._shell import admin_nav, not_admin

register_page(
    __name__,
    path="/admin/journal",
    title="Journal admin | colibre",
    name="Journal admin",
    description="Panneau d'administration interne.",
)


def _rows():
    rows = []
    for action in list_actions():
        target = action["target_user_id"]
        rows.append(
            {
                "date": action["created_at"],
                "admin": action["admin_email"],
                "action": action["action"],
                "user": f"[{target}](/admin/user/{target})" if target else "",
                "détails": action["details"] or "",
            }
        )
    return rows


def layout(**_):
    if not is_admin():
        return not_admin()
    return dbc.Container(
        [
            html.H2("Journal des actions admin"),
            admin_nav("journal"),
            dash_table.DataTable(
                id="admin-journal-table",
                columns=[
                    {"name": "Date", "id": "date"},
                    {"name": "Admin", "id": "admin"},
                    {"name": "Action", "id": "action"},
                    {"name": "User", "id": "user", "presentation": "markdown"},
                    {"name": "Détails", "id": "détails"},
                ],
                data=_rows(),
                sort_action="native",
                page_action="native",
                page_size=20,
                markdown_options={"link_target": "_self"},
            ),
        ],
        fluid=True,
        className="py-4",
    )
```

- [ ] **Step 2: Sanity-check the layout renders without a browser**

Run:

```bash
uv run python -c "
import os
os.environ.setdefault('USERS_DB_PATH', 'tests/users.test.sqlite')
os.environ.setdefault('SECRET_KEY', 'x')
os.environ['ADMIN_EMAIL'] = 'admin@ex.fr'
from unittest.mock import patch
from flask import Flask
from src.auth.setup import init_auth
app = Flask(__name__)
app.config['WTF_CSRF_ENABLED'] = False
init_auth(app)
with app.test_request_context():
    import src.pages.admin.journal as journal
    admin = type('U', (), {'is_authenticated': True, 'email': 'admin@ex.fr'})()
    with patch('src.admin.guard.current_user', admin):
        print(type(journal.layout()))
"
```

Expected: prints the `Container` type, no traceback.

- [ ] **Step 3: Commit**

```bash
git add src/pages/admin/journal.py
git commit -m "feat(admin): add /admin/journal audit log page"
```

---

### Task 9: End-to-end Selenium coverage

**Files:**

- Create: `tests/admin/test_pages.py`

**Interfaces:**

- Consumes: `src.app.app` (the full Dash/Flask app), `src.auth.db`, `src.subscriptions.db`.

**Note on `tests/users.test.sqlite`:** this file is committed to git and shared by the whole Selenium test session (`USERS_DB_PATH=tests/users.test.sqlite` is set globally in `pyproject.toml`'s `[tool.pytest.ini_options] env`, unlike the per-test-isolated `users_db_path` fixture used in Tasks 1-8). Every row this test creates **must** be deleted in a `finally` block so the committed file is left unchanged (`git status` clean) after a test run. Emails are also uuid-suffixed so repeated runs never collide even if cleanup is skipped due to a crash.

- [ ] **Step 1: Write the test file**

Create `tests/admin/test_pages.py`:

```python
import uuid

from dash.testing.composite import DashComposite
from selenium.webdriver.support.ui import Select
from werkzeug.security import generate_password_hash

from src.auth import db as auth_db
from src.subscriptions import db as sub_db

PASSWORD = "s3cretpass!"


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@ex.fr"


def _make_verified_user(email: str) -> int:
    auth_db.init_schema()
    uid = auth_db.create_user(email, generate_password_hash(PASSWORD))
    auth_db.set_email_verified(uid)
    return uid


def _cleanup_user(user_id: int) -> None:
    conn = auth_db.get_conn()
    conn.execute("DELETE FROM admin_actions WHERE target_user_id = ?", (user_id,))
    conn.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM subscriber_state WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def _login(dash_duo: DashComposite, email: str):
    dash_duo.driver.get(dash_duo.server_url + "/connexion")
    dash_duo.wait_for_element("input[name=email]", timeout=8).send_keys(email)
    dash_duo.driver.find_element("css selector", "input[name=password]").send_keys(
        PASSWORD
    )
    dash_duo.driver.find_element("css selector", "button[type=submit]").click()


def test_admin_anonymous_gets_404(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/admin")
    dash_duo.wait_for_text_to_equal("#admin-404-heading", "404", timeout=8)


def test_admin_non_admin_gets_404(dash_duo: DashComposite, monkeypatch):
    from src.app import app

    monkeypatch.setenv("ADMIN_EMAIL", "admin-only@ex.fr")
    email = _unique_email("regular")
    uid = _make_verified_user(email)
    try:
        dash_duo.start_server(app)
        _login(dash_duo, email)
        dash_duo.driver.get(dash_duo.server_url + "/admin")
        dash_duo.wait_for_text_to_equal("#admin-404-heading", "404", timeout=8)
    finally:
        _cleanup_user(uid)


def test_admin_full_flow(dash_duo: DashComposite, monkeypatch):
    from src.app import app

    admin_email = _unique_email("admin")
    monkeypatch.setenv("ADMIN_EMAIL", admin_email)
    admin_uid = _make_verified_user(admin_email)

    target_email = _unique_email("target")
    target_uid = _make_verified_user(target_email)
    sub_db.init_schema()
    _handle, sub_id = sub_db.create_pending(target_uid, "cust-e2e", "simple", 20.0)
    sub_db.set_status(sub_id, "active")

    try:
        dash_duo.start_server(app)
        _login(dash_duo, admin_email)

        dash_duo.driver.get(dash_duo.server_url + "/admin")
        dash_duo.wait_for_text_to_equal("h2", "Panneau admin", timeout=8)
        assert target_email in dash_duo.driver.page_source

        dash_duo.driver.get(f"{dash_duo.server_url}/admin/user/{target_uid}")
        dash_duo.wait_for_text_to_equal("h2", "Panneau admin", timeout=8)
        assert target_email in dash_duo.driver.page_source

        select = Select(
            dash_duo.driver.find_element("css selector", "select[name=status]")
        )
        select.select_by_value("cancelled")
        dash_duo.driver.find_element("css selector", "button[type=submit]").click()

        dash_duo.wait_for_text_to_equal(
            ".alert-success", "Statut de l'abonnement mis à jour.", timeout=8
        )
        assert "cancelled" in dash_duo.driver.page_source

        dash_duo.driver.get(dash_duo.server_url + "/admin/journal")
        dash_duo.wait_for_text_to_equal("h2", "Journal des actions admin", timeout=8)
        assert "subscription_status_change" in dash_duo.driver.page_source
        assert "active → cancelled" in dash_duo.driver.page_source
    finally:
        _cleanup_user(target_uid)
        _cleanup_user(admin_uid)
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/admin/test_pages.py -v`
Expected: 3 passed

- [ ] **Step 3: Verify `tests/users.test.sqlite` is unchanged**

Run: `git status --short tests/users.test.sqlite`
Expected: no output (empty — file unchanged)

If it shows as modified, the cleanup in Step 1 missed a row (check `admin_actions`, `subscriptions`, `subscriber_state`, `users` in that order — foreign keys cascade `ON DELETE CASCADE` from `users`, but `admin_actions.target_user_id` has no FK constraint so it needs the explicit `DELETE` shown above). Fix and re-run before committing.

- [ ] **Step 4: Commit**

```bash
git add tests/admin/test_pages.py
git commit -m "test(admin): add end-to-end Selenium coverage for the admin panel"
```

---

## Self-Review Notes

- **Spec coverage:** Contexte/architecture → Tasks 4-5; couche données (`list_users`, `list_by_user`, `set_status`, `get_subscriber_state`, `SUBSCRIPTION_STATUSES`, `admin_actions`) → Tasks 1-3; pages (`/admin`, `/admin/user/<id>`, `/admin/journal`) → Tasks 6-8; route de mutation → Task 5; tests (unitaires, route, pages) → Tasks 1-9 respectively; pagination native 20/page → Task 6 and 8. Hors périmètre items (reset mot de passe, suppression de compte, édition subscriber_state, multi-admin, pagination SQL) are intentionally not implemented anywhere in this plan.
- **Type consistency checked:** `is_admin()` (Task 4) used identically in `admin_bp.before_request` (Task 5) and in every page's `layout()` (Tasks 6-8). `SUBSCRIPTION_STATUSES` (Task 2) used identically in the route's validation (Task 5) and the detail page's dropdown (Task 7). `list_actions()` / `log_action()` signatures (Task 3) match their use in the route (Task 5) and journal page (Task 8).
- **`_not_admin` naming:** unified as `not_admin()` (no leading underscore) in `_shell.py` since it's imported across three page modules — an underscore-prefixed name would be misleading as a cross-module import.
