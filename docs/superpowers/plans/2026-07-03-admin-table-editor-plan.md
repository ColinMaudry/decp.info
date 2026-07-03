# Panneau admin — éditeur générique de tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer les pages admin dédiées (`/admin/user/<id>`, `/admin/journal` + formulaire de changement de statut) par une unique page `/admin` : un sélecteur de table SQLite + une `dash_table.DataTable` filtrable/triable/paginée en natif dont les cellules sont éditables directement.

**Architecture:** Un registre statique de tables autorisées (`src/admin/tables.py`) porte toute la logique de validation/écriture, testable sans Dash. La page (`src/pages/admin/liste.py`) ne fait que du câblage : un callback unique, déclenché soit par le changement de table (recharge les données), soit par une édition de cellule (diff `data`/`data_previous`, valide, écrit, logue).

**Tech Stack:** Dash 3.4 (`dash_table.DataTable`, `editable`, `dropdown`), dash-bootstrap-components, sqlite3 brut (pas d'ORM).

**Spec:** `docs/superpowers/specs/2026-07-03-admin-table-editor-design.md`

## Global Constraints

- Tables éditables : `users` (jamais `password_hash` — colonne totalement exclue de `SELECT`/affichage), `subscriptions`, `subscriber_state`. `admin_actions` est consultable dans le même sélecteur mais en lecture seule (aucune colonne éditable).
- Colonnes jamais éditables, quelle que soit la table : la clé primaire, `created_at`, `updated_at`. Colonnes explicitement exclues de l'édition même si elles ne sont ni PK ni timestamp : `frisbii_customer_handle`, `frisbii_subscription_handle`, `user_id` (FK).
- Nom de table et de colonne **toujours** validés contre le registre `TABLES` avant toute requête SQL — jamais de nom interpolé directement depuis une valeur venant du client sans passer par ce registre.
- Chaque colonne éditable a un type attendu (`int`, `float`, `str`) ; une valeur qui ne convertit pas proprement est rejetée avant écriture (rien n'est écrit, une alerte s'affiche).
- `dash_table.DataTable` : `filter_action="native"`, `sort_action="native"`, `page_action="native"`, `page_size=20` partout dans cette page.
- `is_admin()` (déjà en place, `src/admin/guard.py`) garde la page : non-admin → composant 404 (`not_admin()`), jamais de redirection.
- Chaque édition de cellule réussie est loguée via `log_action()` (déjà en place, `src/admin/db.py`) avec `action=f"edit_{table}"`, `target_user_id` dérivé par table, `details=f"{column}: {old!r} → {new!r}"`.
- Run tests with `uv run pytest` (venv activation via le Bash tool ne met pas PATH à jour de façon fiable ici).
- `sqlite3` : connexions autocommit (`isolation_level=None`) — aucun `conn.commit()` dans les nouvelles fonctions DB, comme partout ailleurs dans le projet.
- `tests/users.test.sqlite` est committé dans git et partagé pour toute la session de tests Selenium (`USERS_DB_PATH` fixé globalement dans `pyproject.toml`) — toute ligne créée par un test Selenium doit être supprimée en `finally`, avec vérification `git status --short tests/users.test.sqlite` vide après un run complet.

---

### Task 1: Registre des tables (`src/admin/tables.py`)

**Files:**

- Create: `src/admin/tables.py`
- Test: `tests/admin/test_tables.py`

**Interfaces:**

- Produces: `TableConfig` (dataclass), `TABLES: dict[str, TableConfig]`
- Produces: `get_rows(table: str) -> list[dict]`
- Produces: `set_cell(table: str, pk_value, column: str, value) -> None` (lève `ValueError` si table/colonne/valeur invalide)
- Produces: `find_changed_cell(data: list[dict], data_previous: list[dict] | None) -> tuple[int, str, object, object] | None` — `(row_index, column, old_value, new_value)` de la première cellule modifiée, ou `None`.
- Consumes: `get_conn()` de `src.auth.db` (déjà existant), `SUBSCRIPTION_STATUSES` de `src.subscriptions.db` (déjà existant, valeurs `("active", "trial", "cancelled", "expired", "pending")`), `PLANS` de `src.subscriptions.plans` (déjà existant, dict avec les clés `"simple"`, `"soutien"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_tables.py`:

```python
import pytest

from src.admin import tables


def test_get_rows_users_excludes_password_hash(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    auth_db.create_user("a@ex.fr", "secret-hash")

    rows = tables.get_rows("users")

    assert rows[0]["email"] == "a@ex.fr"
    assert "password_hash" not in rows[0]


def test_set_cell_rejects_unknown_table(users_db_path):
    with pytest.raises(ValueError):
        tables.set_cell("not_a_table", 1, "email", "x@ex.fr")


def test_set_cell_rejects_non_editable_column(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")

    with pytest.raises(ValueError):
        tables.set_cell("users", uid, "id", "999")


def test_set_cell_rejects_invalid_dropdown_value(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    with pytest.raises(ValueError):
        tables.set_cell("subscriptions", sub_id, "status", "not_a_status")


def test_set_cell_rejects_bad_type(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    with pytest.raises(ValueError):
        tables.set_cell("subscriptions", sub_id, "prix_ht", "not-a-number")


def test_set_cell_writes_valid_value(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")

    tables.set_cell("users", uid, "siret", "12345678900011")

    rows = tables.get_rows("users")
    assert rows[0]["siret"] == "12345678900011"


def test_set_cell_coerces_numeric_type(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    tables.set_cell("subscriptions", sub_id, "prix_ht", "30")

    rows = tables.get_rows("subscriptions")
    assert rows[0]["prix_ht"] == 30.0


def test_find_changed_cell_detects_single_diff():
    data = [{"id": 1, "email": "new@ex.fr"}]
    data_previous = [{"id": 1, "email": "old@ex.fr"}]

    result = tables.find_changed_cell(data, data_previous)

    assert result == (0, "email", "old@ex.fr", "new@ex.fr")


def test_find_changed_cell_returns_none_when_identical():
    data = [{"id": 1, "email": "a@ex.fr"}]
    data_previous = [{"id": 1, "email": "a@ex.fr"}]

    assert tables.find_changed_cell(data, data_previous) is None


def test_find_changed_cell_returns_none_when_previous_is_none():
    assert tables.find_changed_cell([{"id": 1}], None) is None


def test_target_user_id_per_table():
    assert tables.TABLES["users"].target_user_id({"id": 7}) == 7
    assert tables.TABLES["subscriptions"].target_user_id({"user_id": 9}) == 9
    assert tables.TABLES["subscriber_state"].target_user_id({"user_id": 3}) == 3
    assert tables.TABLES["admin_actions"].target_user_id({"id": 1}) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/admin/test_tables.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.admin.tables'`

- [ ] **Step 3: Implement `src/admin/tables.py`**

```python
from dataclasses import dataclass
from typing import Callable

from src.auth.db import get_conn
from src.subscriptions.db import SUBSCRIPTION_STATUSES
from src.subscriptions.plans import PLANS


@dataclass(frozen=True)
class TableConfig:
    columns: list[str]
    editable_columns: frozenset[str]
    pk: str
    column_types: dict[str, type]
    dropdowns: dict[str, list[str]]
    target_user_id: Callable[[dict], int | None]


TABLES: dict[str, TableConfig] = {
    "users": TableConfig(
        columns=[
            "id",
            "email",
            "email_verified",
            "siret",
            "pending_email",
            "created_at",
            "updated_at",
        ],
        editable_columns=frozenset(
            {"email", "email_verified", "siret", "pending_email"}
        ),
        pk="id",
        column_types={
            "email": str,
            "email_verified": int,
            "siret": str,
            "pending_email": str,
        },
        dropdowns={"email_verified": ["0", "1"]},
        target_user_id=lambda row: row["id"],
    ),
    "subscriptions": TableConfig(
        columns=[
            "id",
            "user_id",
            "frisbii_customer_handle",
            "frisbii_subscription_handle",
            "plan",
            "prix_ht",
            "status",
            "current_period_end",
            "created_at",
            "updated_at",
        ],
        editable_columns=frozenset(
            {"plan", "prix_ht", "status", "current_period_end"}
        ),
        pk="id",
        column_types={
            "plan": str,
            "prix_ht": float,
            "status": str,
            "current_period_end": str,
        },
        dropdowns={
            "status": list(SUBSCRIPTION_STATUSES),
            "plan": list(PLANS.keys()),
        },
        target_user_id=lambda row: row["user_id"],
    ),
    "subscriber_state": TableConfig(
        columns=[
            "user_id",
            "trial_used",
            "votes_balance",
            "votes_last_credited_at",
            "updated_at",
        ],
        editable_columns=frozenset(
            {"trial_used", "votes_balance", "votes_last_credited_at"}
        ),
        pk="user_id",
        column_types={
            "trial_used": int,
            "votes_balance": int,
            "votes_last_credited_at": str,
        },
        dropdowns={"trial_used": ["0", "1"]},
        target_user_id=lambda row: row["user_id"],
    ),
    "admin_actions": TableConfig(
        columns=["id", "admin_email", "action", "target_user_id", "details", "created_at"],
        editable_columns=frozenset(),
        pk="id",
        column_types={},
        dropdowns={},
        target_user_id=lambda row: None,
    ),
}


def get_rows(table: str) -> list[dict]:
    cfg = TABLES[table]
    cols_sql = ", ".join(cfg.columns)
    rows = get_conn().execute(f"SELECT {cols_sql} FROM {table}").fetchall()
    return [dict(row) for row in rows]


def _coerce_value(table: str, column: str, value):
    cfg = TABLES[table]
    if column not in cfg.editable_columns:
        raise ValueError(f"Colonne non éditable : {column}")
    if column in cfg.dropdowns and str(value) not in cfg.dropdowns[column]:
        raise ValueError(f"Valeur non autorisée pour {column} : {value!r}")
    expected_type = cfg.column_types[column]
    try:
        if expected_type is int:
            return int(value)
        if expected_type is float:
            return float(value)
        return str(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valeur invalide pour {column} : {value!r}") from exc


def set_cell(table: str, pk_value, column: str, value) -> None:
    if table not in TABLES:
        raise ValueError(f"Table inconnue : {table}")
    cfg = TABLES[table]
    coerced = _coerce_value(table, column, value)
    get_conn().execute(
        f"UPDATE {table} SET {column} = ? WHERE {cfg.pk} = ?", (coerced, pk_value)
    )


def find_changed_cell(
    data: list[dict], data_previous: list[dict] | None
) -> tuple[int, str, object, object] | None:
    if data_previous is None or len(data) != len(data_previous):
        return None
    for i, (new_row, old_row) in enumerate(zip(data, data_previous)):
        for col, new_val in new_row.items():
            old_val = old_row.get(col)
            if new_val != old_val:
                return i, col, old_val, new_val
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/admin/test_tables.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/admin/tables.py tests/admin/test_tables.py
git commit -m "feat(admin): add whitelisted table registry and cell validation/write logic"
```

---

### Task 2: Page éditeur générique + suppression du code obsolète

**Files:**

- Modify: `src/pages/admin/liste.py` (réécrit entièrement)
- Modify: `src/pages/admin/_shell.py` (retire `admin_nav`)
- Modify: `src/auth/setup.py:47-53` (retire l'enregistrement du blueprint `admin_bp`)
- Modify: `tests/admin/conftest.py` (retire les fixtures Flask-app devenues inutiles, garde `users_db_path`)
- Delete: `src/pages/admin/detail.py`
- Delete: `src/pages/admin/journal.py`
- Delete: `src/admin/routes.py`
- Delete: `tests/admin/test_routes.py`
- Delete: `tests/admin/test_pages.py` (recréé dans la Task 3 avec le nouveau flux — le contenu actuel teste des routes qui n'existent plus)

**Interfaces:**

- Consumes : `TABLES`, `get_rows`, `set_cell`, `find_changed_cell` (Task 1) ; `is_admin()` (`src/admin/guard.py`, inchangé) ; `log_action()` (`src/admin/db.py`, inchangé) ; `not_admin()` (`src/pages/admin/_shell.py`).

- [ ] **Step 1: Simplifier `src/pages/admin/_shell.py`**

Remplacer tout le contenu par :

```python
from dash import html


def not_admin():
    return html.Div(
        html.H2("404", id="admin-404-heading"), className="py-5 text-center"
    )
```

(`admin_nav` disparaît : il n'y a plus qu'une seule page, plus de navigation entre sous-pages.)

- [ ] **Step 2: Réécrire `src/pages/admin/liste.py`**

Remplacer tout le contenu par :

```python
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, ctx, dash_table, html, no_update, register_page
from flask_login import current_user

from src.admin.db import log_action
from src.admin.guard import is_admin
from src.admin.tables import TABLES, find_changed_cell, get_rows, set_cell
from src.pages.admin._shell import not_admin

register_page(
    __name__,
    path="/admin",
    title="Panneau admin | colibre",
    name="Admin",
    description="Panneau d'administration interne.",
)

DEFAULT_TABLE = "users"


def _columns_for(table: str):
    cfg = TABLES[table]
    return [
        {
            "name": col,
            "id": col,
            "editable": col in cfg.editable_columns,
            **({"presentation": "dropdown"} if col in cfg.dropdowns else {}),
        }
        for col in cfg.columns
    ]


def _dropdown_for(table: str):
    cfg = TABLES[table]
    return {
        col: {"options": [{"label": v, "value": v} for v in values]}
        for col, values in cfg.dropdowns.items()
    }


def layout(**_):
    if not is_admin():
        return not_admin()
    return dbc.Container(
        [
            html.H2("Panneau admin"),
            html.Div(id="admin-alerts"),
            dbc.Select(
                id="admin-table-select",
                options=[{"label": name, "value": name} for name in TABLES],
                value=DEFAULT_TABLE,
                className="mb-3",
                style={"maxWidth": "300px"},
            ),
            dash_table.DataTable(
                id="admin-table",
                columns=_columns_for(DEFAULT_TABLE),
                data=get_rows(DEFAULT_TABLE),
                dropdown=_dropdown_for(DEFAULT_TABLE),
                editable=True,
                filter_action="native",
                sort_action="native",
                page_action="native",
                page_size=20,
            ),
        ],
        fluid=True,
        className="py-4",
    )


@callback(
    Output("admin-table", "data"),
    Output("admin-table", "columns"),
    Output("admin-table", "dropdown"),
    Output("admin-alerts", "children"),
    Input("admin-table-select", "value"),
    Input("admin-table", "data"),
    State("admin-table", "data_previous"),
    prevent_initial_call=True,
)
def _update_table(selected_table, data, data_previous):
    if ctx.triggered_id == "admin-table-select":
        return (
            get_rows(selected_table),
            _columns_for(selected_table),
            _dropdown_for(selected_table),
            None,
        )

    change = find_changed_cell(data, data_previous)
    if change is None:
        return no_update, no_update, no_update, None

    row_index, column, old_value, new_value = change
    pk_value = data[row_index][TABLES[selected_table].pk]
    try:
        set_cell(selected_table, pk_value, column, new_value)
    except ValueError as exc:
        return (
            no_update,
            no_update,
            no_update,
            dbc.Alert(str(exc), color="danger", dismissable=True),
        )

    target_user_id = TABLES[selected_table].target_user_id(data[row_index])
    log_action(
        current_user.email,
        f"edit_{selected_table}",
        target_user_id,
        f"{column}: {old_value!r} → {new_value!r}",
    )
    return (
        no_update,
        no_update,
        no_update,
        dbc.Alert("Modification enregistrée.", color="success", dismissable=True),
    )
```

Note d'implémentation : quand une écriture échoue (type invalide, colonne non éditable, valeur hors liste), le callback renvoie `no_update` pour `data` plutôt que de réécrire activement l'ancienne valeur — cela évite tout risque de boucle de déclenchement (le callback a `data` à la fois en `Input` et `Output`). La cellule affichée côté navigateur garde alors la valeur tapée (invalide) jusqu'à ce que l'admin resélectionne la table (ce qui recharge tout depuis la base) ; l'alerte rouge signale explicitement que rien n'a été écrit.

- [ ] **Step 3: Supprimer le code obsolète**

```bash
git rm src/pages/admin/detail.py src/pages/admin/journal.py src/admin/routes.py tests/admin/test_routes.py tests/admin/test_pages.py
```

- [ ] **Step 4: Retirer l'enregistrement du blueprint dans `src/auth/setup.py`**

Supprimer ces lignes (actuellement `src/auth/setup.py:51-53`, juste après l'enregistrement de `auth_bp`) :

```python
    from src.admin.routes import admin_bp

    app.register_blueprint(admin_bp)
```

- [ ] **Step 5: Nettoyer `tests/admin/conftest.py`**

Remplacer tout le contenu par (seule la fixture encore utilisée — par `tests/admin/test_tables.py` et `tests/admin/test_guard.py` — est conservée) :

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

- [ ] **Step 6: Vérifier que le reste de la suite passe toujours**

Run: `uv run pytest tests/admin/ -v`
Expected: tous les tests de `test_tables.py` et `test_guard.py` passent (pas de `test_pages.py`/`test_routes.py` à ce stade, supprimés à l'étape 3 — recréés Task 3)

- [ ] **Step 7: Vérification manuelle du rendu (sans navigateur)**

Run:

```bash
uv run python -c "
import os
os.environ.setdefault('USERS_DB_PATH', 'tests/users.test.sqlite')
os.environ.setdefault('SECRET_KEY', 'x')
os.environ['ADMIN_EMAIL'] = 'admin@ex.fr'
import src.app
from unittest.mock import patch
with src.app.app.server.test_request_context():
    import src.pages.admin.liste as liste
    admin = type('U', (), {'is_authenticated': True, 'email': 'admin@ex.fr'})()
    with patch('src.admin.guard.current_user', admin):
        print(type(liste.layout()))
    non_admin = type('U', (), {'is_authenticated': True, 'email': 'autre@ex.fr'})()
    with patch('src.admin.guard.current_user', non_admin):
        print(type(liste.layout()))
"
git status --short tests/users.test.sqlite
```

Expected : deux lignes `<class '...Container.Container'>` puis `<class '...Div'>`, aucune trace d'erreur ; `git status --short tests/users.test.sqlite` ne renvoie rien (fichier inchangé).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(admin): replace dedicated pages with a generic table editor at /admin"
```

---

### Task 3: Couverture Selenium bout-en-bout

**Files:**

- Create: `tests/admin/test_pages.py`

**Interfaces:**

- Consumes : `src.app.app`, `src.auth.db`, `src.subscriptions.db` (inchangés).

**Note sur le mécanisme d'édition testé :** la colonne `subscriptions.status` est une cellule "dropdown" (`presentation: "dropdown"`), dont l'interaction Selenium est plus fragile à automatiser de façon fiable qu'une cellule texte standard (widget de sélection non natif, rendu par dash_table). Ce test exerce donc l'édition sur `subscriptions.prix_ht` (cellule texte standard, éditable en cliquant/tapant/tabulant) pour prouver que tout le pipeline fonctionne (clic → édition → callback → écriture DB → audit). La logique de validation spécifique aux colonnes "dropdown" (`status`, `plan`, `email_verified`, `trial_used`) est déjà couverte sans navigateur par `test_set_cell_rejects_invalid_dropdown_value` (Task 1).

**Note sur les sélecteurs CSS de cellule :** `dash_table.DataTable` rend chaque cellule avec les attributs `data-dash-row` et `data-dash-column` (documentés, stables). Si le rendu réel diverge de ce qui est écrit ci-dessous (versions de Dash), inspecter le DOM réellement produit et ajuster les sélecteurs — l'important est : cliquer précisément dans la cellule ciblée, remplacer sa valeur, puis tabuler/cliquer ailleurs pour déclencher la mise à jour de la prop `data`.

- [ ] **Step 1: Écrire le fichier de test**

Create `tests/admin/test_pages.py`:

```python
import uuid

from dash.testing.composite import DashComposite
from selenium.webdriver.common.keys import Keys
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
    # tests/users.test.sqlite est committé dans git et partagé pour toute la
    # session Selenium (USERS_DB_PATH fixé globalement dans pyproject.toml).
    # Les DELETE seuls laissent le fichier byte-diffé : sqlite_sequence
    # (compteur AUTOINCREMENT) n'est jamais remis à zéro par un DELETE.
    conn.execute(
        "UPDATE sqlite_sequence SET seq = 0 "
        "WHERE name IN ('users', 'subscriptions', 'admin_actions')"
    )


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
        # Cet utilisateur n'a pas d'abonnement : une connexion réussie
        # redirige vers /compte/abonnement (voir _post_login_url dans
        # src/auth/routes.py). Ça confirme que le login a bien réussi avant
        # de vérifier /admin (sinon ce test serait indiscernable de
        # test_admin_anonymous_gets_404 en cas de régression du login).
        dash_duo.wait_for_text_to_equal("h2", "Abonnement", timeout=8)
        assert "/connexion" not in dash_duo.driver.current_url

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
        assert target_email in dash_duo.driver.page_source  # table users, par défaut

        select = Select(dash_duo.wait_for_element("#admin-table-select", timeout=8))
        select.select_by_value("subscriptions")
        dash_duo.wait_for_element(
            "td[data-dash-column='prix_ht'][data-dash-row='0']", timeout=8
        )

        cell = dash_duo.driver.find_element(
            "css selector", "td[data-dash-column='prix_ht'][data-dash-row='0']"
        )
        cell.click()
        active_input = dash_duo.driver.switch_to.active_element
        active_input.send_keys(Keys.CONTROL, "a")
        active_input.send_keys("30")
        active_input.send_keys(Keys.TAB)

        dash_duo.wait_for_text_to_equal(
            "#admin-alerts .alert-success", "Modification enregistrée.", timeout=8
        )

        row = sub_db.get_current(target_uid)
        assert row["prix_ht"] == 30.0

        select = Select(
            dash_duo.driver.find_element("css selector", "#admin-table-select")
        )
        select.select_by_value("admin_actions")
        dash_duo.wait_for_text_to_equal("h2", "Panneau admin", timeout=8)
        assert "edit_subscriptions" in dash_duo.driver.page_source
        assert "prix_ht" in dash_duo.driver.page_source
    finally:
        _cleanup_user(target_uid)
        _cleanup_user(admin_uid)
```

- [ ] **Step 2: Lancer les tests**

Run: `uv run pytest tests/admin/test_pages.py -v`
Expected: 3 passed. Si le clic/édition de cellule ne déclenche pas la mise à jour attendue, inspecter le DOM réel (`dash_duo.driver.page_source` ou les outils de dev du navigateur en mode non-headless) et ajuster les sélecteurs de `test_admin_full_flow` en conséquence — la structure ci-dessus est le point de départ, pas une garantie absolue selon la version exacte de `dash_table`.

- [ ] **Step 3: Vérifier `tests/users.test.sqlite` inchangé**

Run: `git status --short tests/users.test.sqlite`
Expected: aucune sortie.

- [ ] **Step 4: Lancer la suite admin complète + suite globale**

Run: `uv run pytest tests/admin/ -v`
Expected: tous les tests passent (test_tables.py, test_guard.py, test_pages.py).

Run: `uv run pytest`
Expected: aucune régression sur le reste de la suite.

- [ ] **Step 5: Commit**

```bash
git add tests/admin/test_pages.py
git commit -m "test(admin): add end-to-end Selenium coverage for the generic table editor"
```

---

## Self-Review Notes

- **Spec coverage :** registre de tables + validation/coercition + audit → Task 1 ; page unique, callback de sélection/édition, suppression des pages/route obsolètes, nettoyage `setup.py`/`conftest.py` → Task 2 ; couverture Selenium (accès anonyme/non-admin, flux d'édition complet, audit consultable) → Task 3. `password_hash` jamais sélectionnée (Task 1, `get_rows`/`columns` du registre `users`). Colonnes jamais éditables (PK, timestamps, handles Frisbii, `user_id`) → absentes de `editable_columns` dans le registre (Task 1), revalidées côté serveur dans le callback (Task 2). Pas de tâche pour l'ajout/suppression de lignes ni pour d'autres tables — explicitement hors périmètre du spec.
- **Cohérence des types :** `TableConfig`, `TABLES`, `get_rows`, `set_cell`, `find_changed_cell` (Task 1) sont importés tels quels dans `liste.py` (Task 2) sans renommage. `TableConfig.target_user_id` est un `Callable[[dict], int | None]` dans les deux tâches.
- **Écart noté par rapport au libellé du spec** ("la cellule revient à son ancienne valeur" en cas d'échec) : le callback renvoie `no_update` plutôt que de réécrire activement l'ancienne valeur, pour éviter tout risque de boucle de déclenchement sur une prop qui est à la fois `Input` et `Output` du même callback. L'intégrité des données est préservée de façon identique (rien n'est écrit en base en cas d'échec) ; seul le retour visuel immédiat diffère (l'alerte rouge est explicite, la cellule garde la saisie invalide jusqu'au rechargement de la table). Documenté dans Task 2, Step 2.
