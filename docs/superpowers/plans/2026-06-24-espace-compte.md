# Espace « Mon compte » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformer `/compte` en un espace multi-sections avec navigation latérale, contrôle d'accès à 3 niveaux, et implémenter intégralement la section Compte (changement d'email avec re-vérification, changement de mot de passe, suppression de compte).

**Architecture:** Une page Dash `register_page` par section sous `/compte/*`, enveloppée par une coquille commune `account_shell` (sidebar desktop + `dbc.Offcanvas` mobile). Les nouvelles actions de compte passent par des routes Flask `/auth/*` (formulaires HTML POST), comme l'existant. Le changement d'email stocke une adresse en attente confirmée par lien email.

**Tech Stack:** Dash 3.4, Dash Bootstrap Components, Flask Blueprint, SQLite (`users.sqlite`), flask-login, flask-wtf (CSRF), Brevo (emails).

## Global Constraints

- Importer les modules avec le préfixe `src.` (`src.auth.db`, `src.pages._compte_shell`, …).
- UI en français.
- Les formulaires POSTent vers `/auth/*` ; chaque `<form>` contient un input caché CSRF `dcc.Input(type="hidden", id={"type": "csrf-input", "index": "<unique>"}, name="csrf_token")` rempli par le callback global de `src/app.py`. Chaque `index` doit être unique dans la page.
- `MIN_PASSWORD_LENGTH = 8` (déjà défini dans `src/auth/routes.py`).
- Composants Dash Bootstrap Components autant que possible.
- Lancer les tests avec `uv run pytest` (ne pas `source .venv/bin/activate`).
- Routes auth protégées par `@login_required`.

---

### Task 1: Couche DB — email en attente + migration

**Files:**

- Modify: `src/auth/db.py` (schéma `USERS_SCHEMA`, `init_schema`, nouvelles fonctions)
- Test: `tests/auth/test_db.py`

**Interfaces:**

- Consumes: `get_conn()`, `_now()`, `init_schema()` existants.
- Produces:

  - `set_pending_email(user_id: int, email: str) -> None`
  - `promote_pending_email(user_id: int) -> str | None` (promeut `pending_email` en `email`, met `email_verified=1`, efface `pending_email`, renvoie le nouvel email ou `None` si aucun en attente)
  - colonne `users.pending_email TEXT` (nullable), ajoutée par migration idempotente.

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `tests/auth/test_db.py` :

```python
def test_pending_email_column_exists(users_db_path):
    from src.auth import db

    db.init_schema()
    cols = {r["name"] for r in db.get_conn().execute("PRAGMA table_info(users)")}
    assert "pending_email" in cols


def test_set_and_promote_pending_email(users_db_path):
    from werkzeug.security import generate_password_hash

    from src.auth import db

    db.init_schema()
    uid = db.create_user("old@example.fr", generate_password_hash("password12"))
    db.set_pending_email(uid, "new@example.fr")
    assert db.get_user_by_id(uid)["pending_email"] == "new@example.fr"

    promoted = db.promote_pending_email(uid)
    assert promoted == "new@example.fr"
    row = db.get_user_by_id(uid)
    assert row["email"] == "new@example.fr"
    assert row["pending_email"] is None
    assert row["email_verified"] == 1


def test_promote_pending_email_noop_when_empty(users_db_path):
    from werkzeug.security import generate_password_hash

    from src.auth import db

    db.init_schema()
    uid = db.create_user("a@b.c", generate_password_hash("password12"))
    assert db.promote_pending_email(uid) is None
    assert db.get_user_by_id(uid)["email"] == "a@b.c"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/auth/test_db.py::test_pending_email_column_exists tests/auth/test_db.py::test_set_and_promote_pending_email tests/auth/test_db.py::test_promote_pending_email_noop_when_empty -v`
Expected: FAIL (`pending_email` colonne absente / `AttributeError: module 'src.auth.db' has no attribute 'set_pending_email'`).

- [ ] **Step 3: Add the column to the schema**

Dans `src/auth/db.py`, ajouter la colonne `pending_email` à la table `users` du `USERS_SCHEMA` (après la ligne `email_verified ...`) :

```python
    email_verified INTEGER NOT NULL DEFAULT 0,
    pending_email TEXT,
    created_at TEXT NOT NULL,
```

- [ ] **Step 4: Add an idempotent migration for existing databases**

`CREATE TABLE IF NOT EXISTS` ne modifie pas une table déjà créée : ajouter une migration. Remplacer la fonction `init_schema` par :

```python
def init_schema() -> None:
    conn = get_conn()
    conn.executescript(USERS_SCHEMA)
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "pending_email" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN pending_email TEXT")
```

- [ ] **Step 5: Add the data-access functions**

Ajouter dans `src/auth/db.py` après `update_password_hash` :

```python
def set_pending_email(user_id: int, email: str) -> None:
    get_conn().execute(
        "UPDATE users SET pending_email = ?, updated_at = ? WHERE id = ?",
        (email.lower(), _now(), user_id),
    )


def promote_pending_email(user_id: int) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT pending_email FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None or not row["pending_email"]:
        return None
    new_email = row["pending_email"]
    conn.execute(
        "UPDATE users SET email = ?, pending_email = NULL, "
        "email_verified = 1, updated_at = ? WHERE id = ?",
        (new_email, _now(), user_id),
    )
    return new_email
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_db.py -v`
Expected: PASS (tous les tests du module).

- [ ] **Step 7: Commit**

```bash
git add src/auth/db.py tests/auth/test_db.py
git commit -m "feat(auth): email en attente (pending_email) + migration (#73)"
```

---

### Task 2: Mailer — email de confirmation de changement d'adresse

**Files:**

- Modify: `src/auth/mailer.py`
- Test: `tests/auth/test_mailer.py`

**Interfaces:**

- Consumes: `_base_url()`, `_template_id()`, `_send_template()` existants ; fixture `mail_outbox`.
- Produces: `send_email_change_email(email: str, token: str) -> None` (lien vers `/auth/confirm-email-change?token=...`, réutilise le template `BREVO_TEMPLATE_VERIFY_ID`).

- [ ] **Step 1: Write the failing test**

Ajouter à `tests/auth/test_mailer.py` :

```python
def test_send_email_change_email(mail_outbox, monkeypatch):
    from src.auth import mailer

    monkeypatch.setenv("APP_BASE_URL", "https://decp.info")
    mailer.send_email_change_email("new@example.fr", "tok123")

    assert len(mail_outbox) == 1
    assert mail_outbox[0].recipients == ["new@example.fr"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/auth/test_mailer.py::test_send_email_change_email -v`
Expected: FAIL (`AttributeError: module 'src.auth.mailer' has no attribute 'send_email_change_email'`).

- [ ] **Step 3: Implement the mailer function**

Ajouter à la fin de `src/auth/mailer.py` :

```python
def send_email_change_email(email: str, token: str) -> None:
    link = f"{_base_url()}/auth/confirm-email-change?token={token}"
    _send_template(_template_id("BREVO_TEMPLATE_VERIFY_ID"), email, {"link": link})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/auth/test_mailer.py::test_send_email_change_email -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/auth/mailer.py tests/auth/test_mailer.py
git commit -m "feat(auth): email de confirmation de changement d'adresse (#73)"
```

---

### Task 3: Routes — changement d'email avec re-vérification

**Files:**

- Modify: `src/auth/routes.py`
- Test: `tests/auth/test_email_change.py` (créer)

**Interfaces:**

- Consumes: `db.get_user_by_email`, `db.set_pending_email`, `db.promote_pending_email`, `tokens.create_verification_token`, `tokens.consume_verification_token`, `mailer.send_email_change_email`, `validate_email`, `_redirect_with_error`.
- Produces : routes Flask `POST /auth/change-email` et `GET /auth/confirm-email-change`.
  Redirections : `/compte/admin?email_pending=1`, `/compte/admin?email_changed=1`, `/compte/admin?error=<invalid_email|email_taken|email_send_failed>`.

- [ ] **Step 1: Write the failing tests**

Créer `tests/auth/test_email_change.py` :

```python
from werkzeug.security import generate_password_hash

from src.auth import db


def _login(client, email="old@example.fr", password="password12"):
    db.init_schema()
    uid = db.create_user(email, generate_password_hash(password))
    db.set_email_verified(uid)
    client.post("/auth/login", data={"email": email, "password": password})
    return uid


def test_change_email_requires_login(client, users_db_path):
    resp = client.post("/auth/change-email", data={"email": "x@y.z"})
    assert resp.status_code in (302, 401)


def test_change_email_sets_pending_and_sends_mail(client, users_db_path, mail_outbox):
    uid = _login(client)
    resp = client.post("/auth/change-email", data={"email": "new@example.fr"})
    assert resp.status_code == 302
    assert "email_pending=1" in resp.headers["Location"]
    assert db.get_user_by_id(uid)["pending_email"] == "new@example.fr"
    assert db.get_user_by_id(uid)["email"] == "old@example.fr"  # pas encore changé
    assert mail_outbox[0].recipients == ["new@example.fr"]


def test_change_email_invalid(client, users_db_path, mail_outbox):
    _login(client)
    resp = client.post("/auth/change-email", data={"email": "pas-un-email"})
    assert "error=invalid_email" in resp.headers["Location"]
    assert mail_outbox == []


def test_change_email_already_taken(client, users_db_path, mail_outbox):
    _login(client)
    db.create_user("taken@example.fr", generate_password_hash("password12"))
    resp = client.post("/auth/change-email", data={"email": "taken@example.fr"})
    assert "error=email_taken" in resp.headers["Location"]
    assert mail_outbox == []


def test_confirm_email_change_promotes(client, users_db_path, mail_outbox):
    from src.auth import tokens

    uid = _login(client)
    client.post("/auth/change-email", data={"email": "new@example.fr"})
    token = tokens.create_verification_token(uid)
    resp = client.get(f"/auth/confirm-email-change?token={token}")
    assert resp.status_code == 302
    assert "email_changed=1" in resp.headers["Location"]
    assert db.get_user_by_id(uid)["email"] == "new@example.fr"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/auth/test_email_change.py -v`
Expected: FAIL (404 sur `/auth/change-email`).

- [ ] **Step 3: Implement the change-email route**

Ajouter à la fin de `src/auth/routes.py` (les imports `validate_email`, `EmailNotValidError`, `current_user`, `login_required`, `mailer`, `tokens` sont déjà présents en tête de fichier) :

```python
@auth_bp.route("/change-email", methods=["POST"])
@login_required
def change_email():
    email = (request.form.get("email") or "").strip()
    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.normalized.lower()
    except EmailNotValidError:
        return _redirect_with_error("/compte/admin", "invalid_email")

    if db.get_user_by_email(email) is not None:
        return _redirect_with_error("/compte/admin", "email_taken")

    db.set_pending_email(current_user.id, email)
    token = tokens.create_verification_token(current_user.id)
    try:
        mailer.send_email_change_email(email, token)
    except Exception:
        logger.exception("Échec d'envoi de l'email de changement d'adresse")
        return _redirect_with_error("/compte/admin", "email_send_failed")

    return redirect("/compte/admin?email_pending=1")
```

- [ ] **Step 4: Implement the confirm-email-change route**

Ajouter à la suite dans `src/auth/routes.py` :

```python
@auth_bp.route("/confirm-email-change", methods=["GET"])
def confirm_email_change():
    token = request.args.get("token") or ""
    user_id = tokens.consume_verification_token(token)
    if user_id is None:
        return redirect("/compte/admin?error=invalid_token")
    db.promote_pending_email(user_id)
    return redirect("/compte/admin?email_changed=1")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_email_change.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/auth/routes.py tests/auth/test_email_change.py
git commit -m "feat(auth): routes change-email + confirm-email-change (#73)"
```

---

### Task 4: Route — suppression de compte

**Files:**

- Modify: `src/auth/routes.py`
- Test: `tests/auth/test_account.py`

**Interfaces:**

- Consumes: `db.get_user_by_id`, `db.delete_user`, `db.delete_email_verification_tokens_for_user`, `db.delete_password_reset_tokens_for_user`, `check_password_hash`, `logout_user`.
- Produces: route Flask `POST /auth/delete-account`. Succès → `redirect("/?account_deleted=1")` ; mauvais mot de passe → `/compte/admin?error=invalid_current_password`.

- [ ] **Step 1: Write the failing tests**

Ajouter à `tests/auth/test_account.py` :

```python
def test_delete_account_requires_login(client, users_db_path):
    resp = client.post("/auth/delete-account", data={"current_password": "x"})
    assert resp.status_code in (302, 401)


def test_delete_account_wrong_password(client, users_db_path):
    uid = _login(client)
    resp = client.post("/auth/delete-account", data={"current_password": "wrong"})
    assert "error=invalid_current_password" in resp.headers["Location"]
    assert db.get_user_by_id(uid) is not None


def test_delete_account_success(client, users_db_path):
    uid = _login(client)
    resp = client.post(
        "/auth/delete-account", data={"current_password": "old-password12"}
    )
    assert resp.status_code == 302
    assert "account_deleted=1" in resp.headers["Location"]
    assert db.get_user_by_id(uid) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/auth/test_account.py -k delete -v`
Expected: FAIL (404 sur `/auth/delete-account`).

- [ ] **Step 3: Implement the delete-account route**

Ajouter à la fin de `src/auth/routes.py` :

```python
@auth_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    current_pw = request.form.get("current_password") or ""
    row = db.get_user_by_id(current_user.id)
    if not check_password_hash(row["password_hash"], current_pw):
        return _redirect_with_error("/compte/admin", "invalid_current_password")

    user_id = current_user.id
    db.delete_email_verification_tokens_for_user(user_id)
    db.delete_password_reset_tokens_for_user(user_id)
    db.delete_user(user_id)
    logout_user()
    return redirect("/?account_deleted=1")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/auth/test_account.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/auth/routes.py tests/auth/test_account.py
git commit -m "feat(auth): route delete-account avec confirmation par mot de passe (#73)"
```

---

### Task 5: Coquille partagée `_compte_shell.py`

**Files:**

- Create: `src/pages/_compte_shell.py`
- Test: `tests/test_compte_shell.py` (créer)

**Interfaces:**

- Consumes: `dash.dcc`, `dash_bootstrap_components`, `flask_login.current_user`.
- Produces:

  - `SECTIONS: list[dict]` — chaque entrée `{"key", "label", "href", "require_subscription"}`.
  - `current_user_has_subscription() -> bool` (stub `False`).
  - `visible_sections(has_subscription: bool) -> list[dict]`.
  - `guard_redirect(is_authenticated: bool, has_subscription: bool, require_subscription: bool, path: str) -> str | None`.
  - `account_guard(path: str, require_subscription: bool)` → `dcc.Location | None`.
  - `account_shell(active: str, contenu)` → composant `dbc` (sidebar + offcanvas + contenu).

- [ ] **Step 1: Write the failing tests (fonctions pures)**

Créer `tests/test_compte_shell.py` :

```python
from src.pages import _compte_shell as shell


def test_visible_sections_hides_gated_without_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=False)}
    assert "admin" in keys
    assert "abonnement" in keys
    assert "archives" not in keys


def test_visible_sections_shows_all_with_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=True)}
    assert "archives" in keys


def test_guard_redirect_anonymous_goes_to_login():
    href = shell.guard_redirect(
        is_authenticated=False,
        has_subscription=False,
        require_subscription=False,
        path="/compte/admin",
    )
    assert href == "/connexion?next=/compte/admin"


def test_guard_redirect_unsubscribed_on_gated_goes_to_abonnement():
    href = shell.guard_redirect(
        is_authenticated=True,
        has_subscription=False,
        require_subscription=True,
        path="/compte/archives",
    )
    assert href == "/compte/abonnement"


def test_guard_redirect_allowed_returns_none():
    href = shell.guard_redirect(
        is_authenticated=True,
        has_subscription=False,
        require_subscription=False,
        path="/compte/admin",
    )
    assert href is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_compte_shell.py -v`
Expected: FAIL (`ModuleNotFoundError` / attributs manquants).

- [ ] **Step 3: Implement the shell module**

Créer `src/pages/_compte_shell.py` :

```python
import dash_bootstrap_components as dbc
from dash import dcc, html
from flask_login import current_user

# Définition centralisée des sections de l'espace compte.
# Ajouter une section future = ajouter une ligne ici (+ créer sa page).
SECTIONS = [
    {"key": "admin", "label": "Compte", "href": "/compte/admin",
     "require_subscription": False},
    {"key": "abonnement", "label": "Abonnement", "href": "/compte/abonnement",
     "require_subscription": False},
    {"key": "archives", "label": "Mes archives", "href": "/compte/archives",
     "require_subscription": True},
    {"key": "filtres", "label": "Mes filtres", "href": "/compte/filtres",
     "require_subscription": True},
    {"key": "siret", "label": "Mon SIRET", "href": "/compte/siret",
     "require_subscription": True},
]


def current_user_has_subscription() -> bool:
    """Stub : à brancher sur la facturation (issue #73)."""
    return False


def visible_sections(has_subscription: bool) -> list[dict]:
    return [
        s for s in SECTIONS if has_subscription or not s["require_subscription"]
    ]


def guard_redirect(
    is_authenticated: bool,
    has_subscription: bool,
    require_subscription: bool,
    path: str,
) -> str | None:
    if not is_authenticated:
        return f"/connexion?next={path}"
    if require_subscription and not has_subscription:
        return "/compte/abonnement"
    return None


def account_guard(path: str, require_subscription: bool):
    href = guard_redirect(
        current_user.is_authenticated,
        current_user_has_subscription(),
        require_subscription,
        path,
    )
    return dcc.Location(href=href, id="compte-guard-redirect") if href else None


def _nav(active: str):
    links = [
        dbc.NavLink(s["label"], href=s["href"], active=(s["key"] == active))
        for s in visible_sections(current_user_has_subscription())
    ]
    return dbc.Nav(links, vertical=True, pills=True)


def account_shell(active: str, contenu):
    sidebar = dbc.Col(
        html.Div([html.H5("Mon compte", className="mb-3"), _nav(active)]),
        md=3,
        className="d-none d-md-block",
    )
    mobile = html.Div(
        [
            dbc.Button(
                "☰ Sections",
                id="compte-offcanvas-open",
                color="secondary",
                outline=True,
                className="mb-3",
            ),
            dbc.Offcanvas(
                _nav(active),
                id="compte-offcanvas",
                title="Mon compte",
                is_open=False,
            ),
        ],
        className="d-md-none",
    )
    content = dbc.Col([mobile, contenu], md=9)
    return dbc.Container(dbc.Row([sidebar, content]), className="py-4")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_compte_shell.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pages/_compte_shell.py tests/test_compte_shell.py
git commit -m "feat(compte): coquille account_shell (sidebar + offcanvas + garde d'accès) (#73)"
```

---

### Task 6: Page `/compte/admin` + redirection `/compte` + navbar

**Files:**

- Create: `src/pages/compte_admin.py`
- Modify: `src/pages/compte.py` (devient une redirection)
- Modify: `src/app.py:269` (lien navbar `/compte` → `/compte/admin`)
- Modify: `src/auth/routes.py` (cibles de redirection de `change_password` : `/compte` → `/compte/admin`)
- Test: `tests/auth/test_account.py` (mise à jour de l'assertion existante)

**Interfaces:**

- Consumes: `account_shell`, `account_guard` (Task 5) ; routes `/auth/change-email`, `/auth/change-password`, `/auth/delete-account`, `/auth/logout`.
- Produces: page enregistrée `/compte/admin` (name "Mon compte"), page `/compte` redirigeant vers `/compte/admin`.

- [ ] **Step 1: Update the existing change-password redirect target**

Dans `src/auth/routes.py`, fonction `change_password`, remplacer les 3 occurrences de `"/compte"` par `"/compte/admin"` :

- `_redirect_with_error("/compte", "invalid_current_password")` → `"/compte/admin"`
- `_redirect_with_error("/compte", "password_too_short")` → `"/compte/admin"`
- `_redirect_with_error("/compte", "password_mismatch")` → `"/compte/admin"`
- `redirect("/compte?password_changed=1")` → `redirect("/compte/admin?password_changed=1")`

- [ ] **Step 2: Update the existing test assertion**

Dans `tests/auth/test_account.py`, `test_change_password_success`, remplacer :

```python
    assert "password_changed=1" in resp.headers["Location"]
```

reste valide (l'URL `/compte/admin?password_changed=1` contient toujours `password_changed=1`). Aucune modification nécessaire — vérifier en lançant :

Run: `uv run pytest tests/auth/test_account.py -k change_password -v`
Expected: PASS

- [ ] **Step 3: Create the `/compte/admin` page**

Créer `src/pages/compte_admin.py` :

```python
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, register_page
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell

register_page(
    __name__,
    path="/compte/admin",
    title="Mon compte | decp.info",
    name="Mon compte",
    description="Gestion de votre compte decp.info.",
)

ERROR_MESSAGES = {
    "invalid_current_password": "Le mot de passe actuel est incorrect.",
    "password_too_short": "Le nouveau mot de passe doit faire au moins 8 caractères.",
    "password_mismatch": "Les nouveaux mots de passe ne correspondent pas.",
    "invalid_email": "L'adresse email n'est pas valide.",
    "email_taken": "Cette adresse email est déjà utilisée.",
    "email_send_failed": "L'envoi de l'email de confirmation a échoué.",
    "invalid_token": "Le lien de confirmation est invalide ou expiré.",
}

SUCCESS_MESSAGES = {
    "password_changed": "Mot de passe mis à jour.",
    "email_pending": "Un email de confirmation a été envoyé à la nouvelle adresse.",
    "email_changed": "Votre adresse email a été mise à jour.",
}


def _csrf(index: str):
    return dcc.Input(
        type="hidden",
        id={"type": "csrf-input", "index": index},
        name="csrf_token",
    )


def _email_section():
    return html.Div(
        [
            html.H4("Adresse email", className="mt-2"),
            html.P([html.Strong("Email actuel : "), current_user.email]),
            html.Form(
                method="POST",
                action="/auth/change-email",
                children=[
                    _csrf("change-email"),
                    dbc.Label("Nouvelle adresse email"),
                    dbc.Input(type="email", name="email", required=True,
                              className="mb-3"),
                    dbc.Button("Mettre à jour l'email", type="submit",
                               color="primary"),
                ],
            ),
        ]
    )


def _password_section():
    return html.Div(
        [
            html.H4("Mot de passe", className="mt-4"),
            html.Form(
                method="POST",
                action="/auth/change-password",
                children=[
                    _csrf("change-password"),
                    dbc.Label("Mot de passe actuel"),
                    dbc.Input(type="password", name="current_password",
                              required=True, className="mb-3"),
                    dbc.Label("Nouveau mot de passe (8 caractères minimum)"),
                    dbc.Input(type="password", name="password", required=True,
                              minLength=8, className="mb-3"),
                    dbc.Label("Confirmer le nouveau mot de passe"),
                    dbc.Input(type="password", name="password_confirm",
                              required=True, minLength=8, className="mb-3"),
                    dbc.Button("Changer le mot de passe", type="submit",
                               color="primary"),
                ],
            ),
        ]
    )


def _danger_section():
    return html.Div(
        [
            html.H4("Zone danger", className="mt-5 text-danger"),
            html.P("La suppression de votre compte est définitive."),
            dbc.Button("Supprimer mon compte", id="delete-open",
                       color="danger", outline=True),
            dbc.Modal(
                id="delete-modal",
                is_open=False,
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("Supprimer le compte")),
                    html.Form(
                        method="POST",
                        action="/auth/delete-account",
                        children=[
                            dbc.ModalBody(
                                [
                                    _csrf("delete-account"),
                                    html.P(
                                        "Cette action est définitive. "
                                        "Saisissez votre mot de passe pour confirmer."
                                    ),
                                    dbc.Input(type="password",
                                              name="current_password",
                                              required=True,
                                              placeholder="Mot de passe"),
                                ]
                            ),
                            dbc.ModalFooter(
                                [
                                    dbc.Button("Annuler", id="delete-cancel",
                                               color="secondary"),
                                    dbc.Button("Supprimer définitivement",
                                               type="submit", color="danger"),
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        ],
        className="border border-danger rounded p-3 mt-4",
    )


def _logout_section():
    return html.Form(
        method="POST",
        action="/auth/logout",
        className="mt-4",
        children=[
            _csrf("logout"),
            dbc.Button("Déconnexion", type="submit", color="secondary"),
        ],
    )


def layout(error=None, password_changed=None, email_pending=None,
           email_changed=None, **_):
    guard = account_guard("/compte/admin", require_subscription=False)
    if guard is not None:
        return guard

    alerts = []
    if error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    for flag, value in (("password_changed", password_changed),
                        ("email_pending", email_pending),
                        ("email_changed", email_changed)):
        if value == "1":
            alerts.append(dbc.Alert(SUCCESS_MESSAGES[flag], color="success"))

    contenu = html.Div(
        [
            html.H2("Compte"),
            *alerts,
            _email_section(),
            html.Hr(className="mt-4"),
            _password_section(),
            html.Hr(className="mt-4"),
            _danger_section(),
            _logout_section(),
        ]
    )
    return account_shell("admin", contenu)


@callback(
    Output("delete-modal", "is_open"),
    Input("delete-open", "n_clicks"),
    Input("delete-cancel", "n_clicks"),
    State("delete-modal", "is_open"),
    prevent_initial_call=True,
)
def _toggle_delete_modal(_open, _cancel, is_open):
    return not is_open


@callback(
    Output("compte-offcanvas", "is_open"),
    Input("compte-offcanvas-open", "n_clicks"),
    State("compte-offcanvas", "is_open"),
    prevent_initial_call=True,
)
def _toggle_offcanvas(_n, is_open):
    return not is_open
```

- [ ] **Step 4: Convert `/compte` into a redirect**

Remplacer **tout** le contenu de `src/pages/compte.py` par :

```python
from dash import dcc, register_page

register_page(
    __name__,
    path="/compte",
    title="Mon compte | decp.info",
    name="Mon compte",
    description="Redirection vers la gestion de compte.",
)


def layout(**_):
    return dcc.Location(href="/compte/admin", id="compte-root-redirect")
```

- [ ] **Step 5: Update the navbar link**

Dans `src/app.py:269`, remplacer :

```python
                dbc.DropdownMenuItem("Mon compte", href="/compte"),
```

par :

```python
                dbc.DropdownMenuItem("Mon compte", href="/compte/admin"),
```

- [ ] **Step 6: Verify the app imports and auth tests pass**

Run: `uv run python -c "import src.app"`
Expected: aucune erreur (les pages s'enregistrent sans exception de callback dupliqué).

Run: `uv run pytest tests/auth/test_account.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/pages/compte_admin.py src/pages/compte.py src/app.py src/auth/routes.py
git commit -m "feat(compte): page /compte/admin (email, mot de passe, suppression) (#73)"
```

---

### Task 7: Coquille de la page `/compte/abonnement`

**Files:**

- Create: `src/pages/compte_abonnement.py`

**Interfaces:**

- Consumes: `account_shell`, `account_guard` (Task 5).
- Produces: page enregistrée `/compte/abonnement` (accessible à tout compte connecté).

- [ ] **Step 1: Create the page**

Créer `src/pages/compte_abonnement.py` :

```python
from dash import html, register_page

from src.pages._compte_shell import account_guard, account_shell

register_page(
    __name__,
    path="/compte/abonnement",
    title="Abonnement | decp.info",
    name="Abonnement",
    description="Gestion de votre abonnement decp.info.",
)


def layout(**_):
    guard = account_guard("/compte/abonnement", require_subscription=False)
    if guard is not None:
        return guard

    contenu = html.Div(
        [
            html.H2("Abonnement"),
            html.P("La gestion de l'abonnement arrive bientôt."),
        ]
    )
    return account_shell("abonnement", contenu)
```

- [ ] **Step 2: Verify the app imports**

Run: `uv run python -c "import src.app"`
Expected: aucune erreur.

- [ ] **Step 3: Commit**

```bash
git add src/pages/compte_abonnement.py
git commit -m "feat(compte): coquille de la section Abonnement (#73)"
```

---

### Task 8: Test d'intégration — navigation et accès (Selenium)

**Files:**

- Create: `tests/test_compte_pages.py`

**Interfaces:**

- Consumes: `dash.testing` (`dash_duo`), pattern des tests Selenium existants dans `tests/test_main.py`.

- [ ] **Step 1: Inspect an existing Selenium test for the import pattern**

Lire le haut de `tests/test_main.py` pour reprendre exactement la façon d'importer `app` et d'utiliser `dash_duo.start_server(app)` ainsi que la configuration des variables d'environnement (`DEVELOPMENT`, `USERS_DB_PATH`).

- [ ] **Step 2: Write the integration test**

Créer `tests/test_compte_pages.py` (adapter `from src.app import app` au nom réel utilisé dans `tests/test_main.py`) :

```python
def test_compte_redirects_anonymous_to_login(dash_duo):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/compte/admin")
    dash_duo.wait_for_text_to_equal("h1, h2", "Connexion", timeout=8)
    assert "/connexion" in dash_duo.driver.current_url


def test_compte_root_redirects_to_admin(dash_duo):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/compte")
    # /compte (anonyme) → /compte/admin → /connexion
    dash_duo.wait_for_text_to_equal("h1, h2", "Connexion", timeout=8)
```

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_compte_pages.py -v`
Expected: PASS (un Chrome/Chromium doit être disponible).

> Si le sélecteur de titre de la page Connexion diffère, ajuster `wait_for_text_to_equal` au texte réel rendu par `src/pages/connexion.py`.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest`
Expected: PASS (aucune régression).

- [ ] **Step 5: Commit**

```bash
git add tests/test_compte_pages.py
git commit -m "test(compte): redirections d'accès de l'espace compte (#73)"
```

---

## Self-Review

**Spec coverage:**

- Routage une page/section + redirection `/compte` → Tasks 6, 7 ✓
- Coquille `account_shell` (sidebar + offcanvas) → Task 5 ✓
- 3 niveaux d'accès + `account_guard` + stub `current_user_has_subscription` → Task 5 ✓
- Sections gated masquées → Task 5 (`visible_sections`) ✓
- Section Compte agencement A (email, mdp, zone danger + modale) → Task 6 ✓
- Changement d'email avec re-vérification (`pending_email`, lien) → Tasks 1, 2, 3 ✓
- Suppression de compte (vérif mdp, purge tokens, logout) → Task 4 ✓
- Tests routes + accès → Tasks 1-4, 8 ✓

**Écarts assumés vs spec :**

- Le spec mentionnait `update_email` ; le flux de re-vérification le remplace par `set_pending_email` + `promote_pending_email` (plus sûr, pas de fonction inutilisée — YAGNI).
- L'email de changement réutilise le template Brevo `BREVO_TEMPLATE_VERIFY_ID` (pas de nouvelle variable d'environnement à déployer).

**Placeholder scan :** aucun TBD/TODO ; tout le code est fourni.

**Type consistency :** `set_pending_email`/`promote_pending_email`/`visible_sections`/`guard_redirect`/`account_guard`/`account_shell` ont des signatures cohérentes entre la définition (Tasks 1, 5) et leurs usages (Tasks 3, 6, 7).

## Hors périmètre (rappel)

- Contenu réel de la section Abonnement (perks, tarifs, paiement).
- Pages Archives, Filtres, Mon SIRET (leurs entrées existent dans `SECTIONS` mais restent masquées tant que `current_user_has_subscription()` renvoie `False`).
- Branchement réel de la facturation.
