# Sauvegarde des vues du Tableau — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre aux abonné·es d'enregistrer des vues nommées (filtres + tris + colonnes) sur `/tableau`, de les appliquer en un clic, et de les gérer sur `/compte/vues`.

**Architecture:** Une vue = un nom + la query string `filtres`/`tris`/`colonnes` que `/tableau` produit et restaure déjà. Stockage serveur dans `users.sqlite` (nouveau module `src/saved_views/`). La logique métier (construction de query, validation, builders d'UI) vit dans des fonctions pures testables ; les callbacks Dash ne font que les câbler. Réutilisation du `restore_view_from_url` existant pour appliquer une vue (navigation vers `/tableau?<query>`).

**Tech Stack:** Python, Dash 3.4, Dash Bootstrap Components, SQLite (`users.sqlite` via `src.auth.db.get_conn()`), Flask-Login (`current_user`), pytest.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `src.saved_views.db`), jamais `saved_views.db`.
- Accès DB via `src.auth.db.get_conn()` (connexion thread-local sur `users.sqlite`).
- Contrôle d'abonnement via `src.pages._compte_shell.current_user_has_subscription()` (respecte `TOUS_ABONNES`). Ne jamais appeler `db.has_active_subscription()` directement pour le gating UI.
- Toute opération DB inclut `user_id` dans le `WHERE` (isolation entre comptes).
- Périmètre strict : `/tableau` uniquement. La colonne `table_name` vaut toujours `'tableau'`.
- Tests lancés avec `uv run pytest`.
- Format/lint : `prettier` (markdown) et `ruff` tournent en pre-commit ; committer du code déjà formaté.

---

## Structure des fichiers

| Fichier                                              | Responsabilité                                                                                                                                                                                         |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `src/saved_views/__init__.py` (créer)                | Marqueur de package.                                                                                                                                                                                   |
| `src/saved_views/db.py` (créer)                      | Schéma `saved_views` + CRUD (`init_schema`, `list_views`, `upsert`, `rename`, `delete`, `get`).                                                                                                        |
| `src/saved_views/ui.py` (créer)                      | Fonctions **pures** d'UI/validation : `bar_style`, `clean_view_name`, `prepare_view_to_save`, `saved_views_items`, `views_table`. Aucune dépendance à un app Dash (pas de `register_page`/`callback`). |
| `src/utils/table.py` (modifier)                      | Ajouter `build_view_query()` ; refactorer `sync_url_and_reset_button` (dans `tableau.py`) pour l'utiliser.                                                                                             |
| `src/app.py` (modifier)                              | Appeler `saved_views.db.init_schema()` au démarrage.                                                                                                                                                   |
| `src/pages/tableau.py` (modifier)                    | Barre « vues » dans `table-menu` + 3 callbacks (visibilité, sauvegarde, remplissage du menu) qui câblent les helpers.                                                                                  |
| `src/pages/_compte_shell.py` (modifier)              | Ajouter la section `vues` à `SECTIONS`.                                                                                                                                                                |
| `src/pages/compte_vues.py` (créer)                   | Page `/compte/vues` (liste/renommer/supprimer), gabarit `compte_admin.py`.                                                                                                                             |
| `tests/saved_views/__init__.py` (créer)              | Package de tests.                                                                                                                                                                                      |
| `tests/saved_views/conftest.py` (créer)              | Fixture `users_db_path` (copie de `tests/subscriptions/conftest.py`).                                                                                                                                  |
| `tests/saved_views/test_db.py` (créer)               | Tests unitaires du CRUD.                                                                                                                                                                               |
| `tests/saved_views/test_ui.py` (créer)               | Tests des fonctions pures d'UI/validation.                                                                                                                                                             |
| `tests/saved_views/test_build_view_query.py` (créer) | Tests de `build_view_query`.                                                                                                                                                                           |

---

## Task 1: Module DB `src/saved_views/db.py`

**Files:**

- Create: `src/saved_views/__init__.py`
- Create: `src/saved_views/db.py`
- Create: `tests/saved_views/__init__.py`
- Create: `tests/saved_views/conftest.py`
- Create: `tests/saved_views/test_db.py`
- Modify: `src/app.py` (après `init_subscriptions(app.server)`)

**Interfaces:**

- Consumes: `src.auth.db.get_conn()`, `src.auth.db.init_schema()`, `src.auth.db.create_user(email, password_hash) -> int`, `src.auth.db.delete_user(user_id)`.
- Produces:

  - `SCHEMA: str`
  - `init_schema() -> None`
  - `list_views(user_id: int, table_name: str = "tableau") -> list[sqlite3.Row]`
  - `upsert(user_id: int, table_name: str, name: str, query: str) -> None`
  - `rename(view_id: int, user_id: int, new_name: str) -> None`
  - `delete(view_id: int, user_id: int) -> None`
  - `get(view_id: int, user_id: int) -> sqlite3.Row | None`

- [ ] **Step 1: Créer le package et le fichier de tests vide**

Créer `src/saved_views/__init__.py` (vide) et `tests/saved_views/__init__.py` (vide).

Créer `tests/saved_views/conftest.py` (copie de la fixture de `tests/subscriptions/conftest.py`) :

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

- [ ] **Step 2: Écrire les tests qui échouent**

Créer `tests/saved_views/test_db.py` :

```python
from src.auth import db as auth_db
from src.saved_views import db


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def test_init_schema_creates_table(users_db_path):
    db.init_schema()
    conn = auth_db.get_conn()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "saved_views" in tables


def test_upsert_creates_and_lists(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.upsert(uid, "tableau", "Ma vue", "filtres=foo")
    views = db.list_views(uid, "tableau")
    assert len(views) == 1
    assert views[0]["name"] == "Ma vue"
    assert views[0]["query"] == "filtres=foo"


def test_upsert_same_name_overwrites(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.upsert(uid, "tableau", "Ma vue", "filtres=foo")
    db.upsert(uid, "tableau", "Ma vue", "filtres=bar")
    views = db.list_views(uid, "tableau")
    assert len(views) == 1
    assert views[0]["query"] == "filtres=bar"


def test_list_views_is_isolated_per_user(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    assert db.list_views(uid2, "tableau") == []


def test_rename_only_affects_owner(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    view_id = db.list_views(uid1, "tableau")[0]["id"]
    db.rename(view_id, uid2, "Pirate")  # mauvais propriétaire → no-op
    assert db.get(view_id, uid1)["name"] == "Vue A"
    db.rename(view_id, uid1, "Vue B")
    assert db.get(view_id, uid1)["name"] == "Vue B"


def test_delete_only_affects_owner(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    view_id = db.list_views(uid1, "tableau")[0]["id"]
    db.delete(view_id, uid2)  # mauvais propriétaire → no-op
    assert db.get(view_id, uid1) is not None
    db.delete(view_id, uid1)
    assert db.get(view_id, uid1) is None


def test_views_deleted_on_user_cascade(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.upsert(uid, "tableau", "Vue A", "filtres=a")
    auth_db.delete_user(uid)
    assert db.list_views(uid, "tableau") == []
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_db.py -v`
Expected: FAIL (ModuleNotFoundError: `src.saved_views.db`).

- [ ] **Step 4: Écrire `src/saved_views/db.py`**

```python
import sqlite3
from datetime import datetime, timezone

from src.auth.db import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_views (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    table_name  TEXT NOT NULL DEFAULT 'tableau',
    name        TEXT NOT NULL,
    query       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, table_name, name)
);
CREATE INDEX IF NOT EXISTS idx_saved_views_user
    ON saved_views(user_id, table_name);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema() -> None:
    get_conn().executescript(SCHEMA)


def list_views(user_id: int, table_name: str = "tableau") -> list[sqlite3.Row]:
    return (
        get_conn()
        .execute(
            "SELECT * FROM saved_views WHERE user_id = ? AND table_name = ? "
            "ORDER BY name COLLATE NOCASE",
            (user_id, table_name),
        )
        .fetchall()
    )


def get(view_id: int, user_id: int) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM saved_views WHERE id = ? AND user_id = ?",
            (view_id, user_id),
        )
        .fetchone()
    )


def upsert(user_id: int, table_name: str, name: str, query: str) -> None:
    now = _now()
    get_conn().execute(
        "INSERT INTO saved_views "
        "(user_id, table_name, name, query, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, table_name, name) DO UPDATE SET "
        "query = excluded.query, updated_at = excluded.updated_at",
        (user_id, table_name, name, query, now, now),
    )


def rename(view_id: int, user_id: int, new_name: str) -> None:
    get_conn().execute(
        "UPDATE saved_views SET name = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (new_name, _now(), view_id, user_id),
    )


def delete(view_id: int, user_id: int) -> None:
    get_conn().execute(
        "DELETE FROM saved_views WHERE id = ? AND user_id = ?",
        (view_id, user_id),
    )
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_db.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Câbler `init_schema()` au démarrage dans `src/app.py`**

Juste après la ligne `init_subscriptions(app.server)` (≈ ligne 106), ajouter :

```python
from src.saved_views import db as saved_views_db  # noqa: E402

saved_views_db.init_schema()
```

- [ ] **Step 7: Vérifier l'import de l'app**

Run: `uv run python -c "import src.app"`
Expected: aucune erreur (sortie vide ou logs normaux).

- [ ] **Step 8: Commit**

```bash
git add src/saved_views/__init__.py src/saved_views/db.py src/app.py \
        tests/saved_views/__init__.py tests/saved_views/conftest.py \
        tests/saved_views/test_db.py
git commit -m "feat: table saved_views et CRUD #95"
```

---

## Task 2: Helper `build_view_query` dans `src/utils/table.py`

Extrait la construction de query string aujourd'hui inline dans `sync_url_and_reset_button` (`tableau.py`), pour la réutiliser à la sauvegarde.

**Files:**

- Modify: `src/utils/table.py` (ajouter la fonction + imports si absents)
- Modify: `src/pages/tableau.py` (`sync_url_and_reset_button` utilise le helper)
- Create: `tests/saved_views/test_build_view_query.py`

**Interfaces:**

- Consumes: `src.utils.table.invert_columns(columns) -> list[str]`.
- Produces: `build_view_query(filter_query: str | None, sort_by: list | None, hidden_columns: list | None) -> str` — renvoie une query string (`urlencode`) avec les clés `filtres`, `tris` (JSON), `colonnes` (CSV des colonnes **visibles**). Renvoie `""` si aucun paramètre.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/saved_views/test_build_view_query.py` :

```python
import urllib.parse

from src.utils.table import build_view_query


def test_empty_inputs_give_empty_string():
    assert build_view_query(None, None, None) == ""
    assert build_view_query("", [], []) == ""


def test_filter_only():
    q = build_view_query("{objet} icontains route", None, None)
    params = urllib.parse.parse_qs(q)
    assert params["filtres"] == ["{objet} icontains route"]
    assert "tris" not in params
    assert "colonnes" not in params


def test_sort_is_json_encoded():
    sort_by = [{"column_id": "montant", "direction": "desc"}]
    q = build_view_query(None, sort_by, None)
    params = urllib.parse.parse_qs(q)
    import json

    assert json.loads(params["tris"][0]) == sort_by


def test_hidden_columns_become_visible_csv():
    # build_view_query reçoit les colonnes MASQUÉES et stocke les VISIBLES
    q = build_view_query(None, None, ["objet"])
    params = urllib.parse.parse_qs(q)
    visible = params["colonnes"][0].split(",")
    assert "objet" not in visible
    assert len(visible) > 0
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_build_view_query.py -v`
Expected: FAIL (ImportError: `build_view_query`).

- [ ] **Step 3: Ajouter `build_view_query` à `src/utils/table.py`**

Vérifier que le haut du fichier contient `import json` et `import urllib.parse` ; les ajouter sinon. Puis ajouter, à la fin du fichier (après `invert_columns`) :

```python
def build_view_query(filter_query, sort_by, hidden_columns) -> str:
    """
    Construit la query string d'une vue Tableau (filtres + tris + colonnes),
    identique à celle produite par le bouton « Partager la vue ».

    hidden_columns : colonnes masquées ; on stocke les colonnes visibles.
    """
    params = {}
    if filter_query:
        params["filtres"] = filter_query
    if sort_by:
        params["tris"] = json.dumps(sort_by)
    if hidden_columns:
        params["colonnes"] = ",".join(invert_columns(hidden_columns))
    return urllib.parse.urlencode(params)
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_build_view_query.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Refactorer `sync_url_and_reset_button` dans `src/pages/tableau.py`**

Dans `src/pages/tableau.py`, importer le helper en haut (ajouter `build_view_query` à l'import existant depuis `src.utils.table`).

Remplacer le corps de construction de l'URL (lignes ≈ 427-440, du `params = {}` jusqu'au `full_url = ...`) par :

```python
    query_string = build_view_query(filter_query, sort_by, hidden_columns)
    full_url = f"{base_url}?{query_string}" if query_string else base_url
```

Supprimer l'import devenu inutile s'il n'est plus utilisé ailleurs (vérifier `json`/`urllib` restent utilisés par d'autres callbacks — ils le sont, ne pas les retirer).

- [ ] **Step 6: Vérifier la non-régression du partage**

Run: `uv run python -c "import src.app"`
Expected: aucune erreur.
Run: `uv run pytest tests/saved_views -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/utils/table.py src/pages/tableau.py tests/saved_views/test_build_view_query.py
git commit -m "refactor: extrait build_view_query et le réutilise dans le partage #95"
```

---

## Task 3: Fonctions pures d'UI/validation `src/saved_views/ui.py`

**Files:**

- Create: `src/saved_views/ui.py`
- Create: `tests/saved_views/test_ui.py`

**Interfaces:**

- Consumes: `dash_bootstrap_components as dbc`, `dash.html`.
- Produces:

  - `bar_style(has_subscription: bool) -> dict` — `{}` si abonné, `{"display": "none"}` sinon.
  - `clean_view_name(name: str | None) -> str` — `name.strip()`, `""` si vide/None.
  - `prepare_view_to_save(has_subscription: bool, name: str | None) -> tuple[str | None, str | None]` — renvoie `(clean_name, None)` si OK ; `(None, message)` si refus (non-abonné ou nom vide).
  - `saved_views_items(views) -> list` — liste de `dbc.DropdownMenuItem` liens `href="/tableau?<query>"` (un par vue).
  - `views_table(views) -> html.Div` — bloc de gestion pour `/compte/vues` (un `html.Div` par vue avec id pattern-matching pour Ouvrir/Renommer/Supprimer), ou message d'état vide.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/saved_views/test_ui.py` :

```python
from src.saved_views import ui


class _Row(dict):
    """Imite un sqlite3.Row : accès par clé."""


def _view(view_id, name, query):
    return _Row(id=view_id, name=name, query=query)


def test_bar_style_hidden_for_non_subscriber():
    assert ui.bar_style(False) == {"display": "none"}
    assert ui.bar_style(True) == {}


def test_clean_view_name_strips_and_empties():
    assert ui.clean_view_name("  Ma vue  ") == "Ma vue"
    assert ui.clean_view_name("   ") == ""
    assert ui.clean_view_name(None) == ""


def test_prepare_refuses_non_subscriber():
    name, err = ui.prepare_view_to_save(False, "Ma vue")
    assert name is None
    assert err


def test_prepare_refuses_empty_name():
    name, err = ui.prepare_view_to_save(True, "   ")
    assert name is None
    assert err


def test_prepare_accepts_valid():
    name, err = ui.prepare_view_to_save(True, "  Ma vue  ")
    assert name == "Ma vue"
    assert err is None


def test_saved_views_items_build_links():
    items = ui.saved_views_items(
        [_view(1, "Vue A", "filtres=a"), _view(2, "Vue B", "tris=b")]
    )
    assert len(items) == 2
    assert items[0].href == "/tableau?filtres=a"
    assert items[0].children == "Vue A"


def test_views_table_empty_state():
    out = ui.views_table([])
    # un Div non vide (message d'état) sans item de suppression
    assert out is not None


def test_views_table_lists_views():
    out = ui.views_table([_view(1, "Vue A", "filtres=a")])
    text = str(out)
    assert "Vue A" in text
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_ui.py -v`
Expected: FAIL (ModuleNotFoundError: `src.saved_views.ui`).

- [ ] **Step 3: Écrire `src/saved_views/ui.py`**

```python
import dash_bootstrap_components as dbc
from dash import html


def bar_style(has_subscription: bool) -> dict:
    return {} if has_subscription else {"display": "none"}


def clean_view_name(name: str | None) -> str:
    return (name or "").strip()


def prepare_view_to_save(
    has_subscription: bool, name: str | None
) -> tuple[str | None, str | None]:
    if not has_subscription:
        return None, "Réservé aux abonné·es."
    clean = clean_view_name(name)
    if not clean:
        return None, "Veuillez saisir un nom pour la vue."
    return clean, None


def saved_views_items(views) -> list:
    return [
        dbc.DropdownMenuItem(view["name"], href=f"/tableau?{view['query']}")
        for view in views
    ]


def _view_row(view) -> html.Div:
    view_id = view["id"]
    return html.Div(
        className="saved-view-row d-flex align-items-center gap-2 mb-2",
        children=[
            html.Span(view["name"], className="flex-grow-1"),
            dbc.Button(
                "Ouvrir",
                href=f"/tableau?{view['query']}",
                color="link",
                size="sm",
            ),
            dbc.Button(
                "Renommer",
                id={"type": "vue-rename-open", "index": view_id},
                color="secondary",
                outline=True,
                size="sm",
            ),
            dbc.Button(
                "Supprimer",
                id={"type": "vue-delete", "index": view_id},
                color="danger",
                outline=True,
                size="sm",
            ),
        ],
    )


def views_table(views) -> html.Div:
    if not views:
        return html.Div(
            html.P(
                "Vous n'avez pas encore de vue enregistrée. "
                "Créez-en une depuis le Tableau, bouton « Sauvegarder la vue »."
            )
        )
    return html.Div([_view_row(v) for v in views])
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_ui.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/saved_views/ui.py tests/saved_views/test_ui.py
git commit -m "feat: helpers UI/validation des vues sauvegardées #95"
```

---

## Task 4: Intégration sur `/tableau`

Câble les helpers : barre « vues » (masquée par défaut), callback de visibilité (gating), callback de sauvegarde (avec modale), callback de remplissage du menu déroulant.

**Files:**

- Modify: `src/pages/tableau.py`

**Interfaces:**

- Consumes: `src.saved_views.db` (`upsert`, `list_views`), `src.saved_views.ui` (`bar_style`, `prepare_view_to_save`, `saved_views_items`), `src.utils.table.build_view_query`, `src.pages._compte_shell.current_user_has_subscription`, `flask_login.current_user`.
- Produces: composants d'id `saved-views-bar`, `btn-save-view`, `save-view-modal`, `save-view-name`, `btn-save-view-confirm`, `save-view-feedback`, `saved-views-menu`, `saved-views-refresh` (Store).

- [ ] **Step 1: Ajouter les imports en haut de `src/pages/tableau.py`**

```python
from flask_login import current_user

from src.pages._compte_shell import current_user_has_subscription
from src.saved_views import db as saved_views_db
from src.saved_views import ui as saved_views_ui
```

(`build_view_query` a déjà été ajouté à l'import `src.utils.table` en Task 2.)

- [ ] **Step 2: Ajouter la barre « vues » dans la `table-menu`**

Dans le `children` de la `html.Div(className="table-menu", ...)` (≈ lignes 154-265), juste après le bouton « Choisir les colonnes » (id `tableau_columns_open`), insérer :

```python
                    html.Div(
                        id="saved-views-bar",
                        style={"display": "none"},
                        className="d-inline-flex align-items-center gap-2",
                        children=[
                            dbc.Button(
                                "Sauvegarder la vue",
                                id="btn-save-view",
                                title="Enregistrer les filtres, tris et colonnes actuels sous un nom",
                            ),
                            dbc.DropdownMenu(
                                id="saved-views-menu",
                                label="Mes vues",
                                children=[],
                                className="d-inline-block",
                            ),
                        ],
                    ),
                    dcc.Store(id="saved-views-refresh"),
                    dbc.Modal(
                        id="save-view-modal",
                        is_open=False,
                        children=[
                            dbc.ModalHeader(dbc.ModalTitle("Sauvegarder la vue")),
                            dbc.ModalBody(
                                [
                                    dbc.Label("Nom de la vue"),
                                    dcc.Input(
                                        id="save-view-name",
                                        type="text",
                                        className="form-control",
                                    ),
                                    html.Div(id="save-view-feedback", className="mt-2"),
                                ]
                            ),
                            dbc.ModalFooter(
                                dbc.Button(
                                    "Enregistrer",
                                    id="btn-save-view-confirm",
                                    color="primary",
                                )
                            ),
                        ],
                    ),
```

- [ ] **Step 3: Ajouter le callback de visibilité (gating)**

À la fin de `src/pages/tableau.py`, ajouter :

```python
@callback(
    Output("saved-views-bar", "style"),
    Input("tableau_url", "pathname"),
)
def toggle_saved_views_bar(_pathname):
    return saved_views_ui.bar_style(current_user_has_subscription())
```

- [ ] **Step 4: Ajouter le callback d'ouverture de la modale**

```python
@callback(
    Output("save-view-modal", "is_open"),
    Input("btn-save-view", "n_clicks"),
    Input("btn-save-view-confirm", "n_clicks"),
    State("save-view-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_save_view_modal(_open, _confirm, is_open):
    return not is_open
```

- [ ] **Step 5: Ajouter le callback de sauvegarde (avec contrôle serveur)**

```python
@callback(
    Output("save-view-feedback", "children"),
    Output("saved-views-refresh", "data"),
    Input("btn-save-view-confirm", "n_clicks"),
    State("save-view-name", "value"),
    State("tableau_datatable", "filter_query"),
    State("tableau_datatable", "sort_by"),
    State("tableau_datatable", "hidden_columns"),
    prevent_initial_call=True,
)
def save_view(_n, name, filter_query, sort_by, hidden_columns):
    has_sub = current_user_has_subscription()
    clean_name, error = saved_views_ui.prepare_view_to_save(has_sub, name)
    if error:
        return html.Span(error, style={"color": "red"}), no_update
    query = build_view_query(filter_query, sort_by, hidden_columns)
    saved_views_db.upsert(current_user.id, "tableau", clean_name, query)
    return (
        html.Span(f"Vue « {clean_name} » enregistrée.", style={"color": "green"}),
        clean_name,
    )
```

- [ ] **Step 6: Ajouter le callback de remplissage du menu déroulant**

```python
@callback(
    Output("saved-views-menu", "children"),
    Input("tableau_url", "pathname"),
    Input("saved-views-refresh", "data"),
)
def populate_saved_views_menu(_pathname, _refresh):
    if not current_user_has_subscription():
        return []
    views = saved_views_db.list_views(current_user.id, "tableau")
    return saved_views_ui.saved_views_items(views)
```

- [ ] **Step 7: Vérifier l'import et la non-régression**

Run: `uv run python -c "import src.app"`
Expected: aucune erreur (pas d'erreur de callback dupliqué/composant manquant).
Run: `uv run pytest tests/saved_views -v`
Expected: PASS.

- [ ] **Step 8: Vérification manuelle (smoke test)**

Démarrer `uv run python run.py`, se connecter avec un compte abonné (ou `TOUS_ABONNES=true` dans `.env`), aller sur `/tableau` :

- la barre « Sauvegarder la vue » + « Mes vues » est visible ;
- appliquer un filtre, cliquer « Sauvegarder la vue », saisir un nom, Enregistrer → confirmation verte ;
- ouvrir « Mes vues » → la vue apparaît ; cliquer dessus applique le filtre.
- Se déconnecter → la barre disparaît.

- [ ] **Step 9: Commit**

```bash
git add src/pages/tableau.py
git commit -m "feat: UI sauvegarde et application des vues sur /tableau #95"
```

---

## Task 5: Page de gestion `/compte/vues`

**Files:**

- Modify: `src/pages/_compte_shell.py` (ajout section `vues`)
- Create: `src/pages/compte_vues.py`
- Create: `tests/saved_views/test_compte_vues.py`

**Interfaces:**

- Consumes: `src.pages._compte_shell` (`account_guard`, `account_shell`, `SECTIONS`), `src.saved_views.db` (`list_views`, `rename`, `delete`), `src.saved_views.ui.views_table`, `flask_login.current_user`.
- Produces: page enregistrée sur `/compte/vues` ; section `vues` dans `SECTIONS`.

- [ ] **Step 1: Écrire le test de la section (échoue)**

Créer `tests/saved_views/test_compte_vues.py` :

```python
from src.pages import _compte_shell as shell


def test_vues_section_is_gated_subscription():
    section = next(s for s in shell.SECTIONS if s["key"] == "vues")
    assert section["href"] == "/compte/vues"
    assert section["require_subscription"] is True


def test_vues_hidden_without_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=False)}
    assert "vues" not in keys


def test_vues_visible_with_subscription():
    keys = {s["key"] for s in shell.visible_sections(has_subscription=True)}
    assert "vues" in keys
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_compte_vues.py -v`
Expected: FAIL (`StopIteration` : section `vues` absente).

- [ ] **Step 3: Ajouter la section dans `src/pages/_compte_shell.py`**

Dans la liste `SECTIONS`, après l'entrée `filtres`, ajouter :

```python
    {
        "key": "vues",
        "label": "Mes vues",
        "href": "/compte/vues",
        "require_subscription": True,
    },
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_compte_vues.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Créer la page `src/pages/compte_vues.py`**

```python
import dash_bootstrap_components as dbc
from dash import (
    ALL,
    Input,
    Output,
    State,
    callback,
    ctx,
    html,
    no_update,
    register_page,
)
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell
from src.saved_views import db as saved_views_db
from src.saved_views import ui as saved_views_ui

register_page(
    __name__,
    path="/compte/vues",
    title="Mes vues | decp.info",
    name="Mes vues",
    description="Gérez vos vues enregistrées du tableau des marchés.",
)


def _content():
    views = saved_views_db.list_views(current_user.id, "tableau")
    return html.Div(
        [
            html.H2("Mes vues"),
            html.P(
                "Les vues que vous enregistrez depuis le Tableau apparaissent ici. "
                "Cliquez sur « Ouvrir » pour appliquer une vue."
            ),
            html.Div(saved_views_ui.views_table(views), id="vues-list"),
        ]
    )


def layout(**_):
    guard = account_guard("/compte/vues", require_subscription=True)
    if guard is not None:
        return guard
    return account_shell("vues", _content())


@callback(
    Output("vues-list", "children"),
    Input({"type": "vue-delete", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def delete_view(n_clicks):
    if not ctx.triggered_id or not any(n_clicks):
        return no_update
    saved_views_db.delete(ctx.triggered_id["index"], current_user.id)
    views = saved_views_db.list_views(current_user.id, "tableau")
    return saved_views_ui.views_table(views)
```

- [ ] **Step 6: Ajouter le renommage (modale partagée)**

Ajouter en bas de `src/pages/compte_vues.py` une modale de renommage et ses callbacks. Compléter `_content()` pour inclure la modale :

Dans `_content()`, ajouter à la liste des enfants (après `vues-list`) :

```python
            dbc.Modal(
                id="vue-rename-modal",
                is_open=False,
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("Renommer la vue")),
                    dbc.ModalBody(
                        dbc.Input(id="vue-rename-input", type="text"),
                    ),
                    dbc.ModalFooter(
                        dbc.Button("Renommer", id="vue-rename-confirm", color="primary")
                    ),
                ],
            ),
            dbc.Input(id="vue-rename-id", type="hidden"),
```

Puis les callbacks :

```python
@callback(
    Output("vue-rename-modal", "is_open"),
    Output("vue-rename-id", "value"),
    Input({"type": "vue-rename-open", "index": ALL}, "n_clicks"),
    Input("vue-rename-confirm", "n_clicks"),
    State("vue-rename-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_rename_modal(_open, _confirm, is_open):
    if isinstance(ctx.triggered_id, dict) and any(_open):
        return True, str(ctx.triggered_id["index"])
    return False, no_update


@callback(
    Output("vues-list", "children", allow_duplicate=True),
    Input("vue-rename-confirm", "n_clicks"),
    State("vue-rename-id", "value"),
    State("vue-rename-input", "value"),
    prevent_initial_call=True,
)
def rename_view(_n, view_id, new_name):
    clean = saved_views_ui.clean_view_name(new_name)
    if not view_id or not clean:
        return no_update
    saved_views_db.rename(int(view_id), current_user.id, clean)
    views = saved_views_db.list_views(current_user.id, "tableau")
    return saved_views_ui.views_table(views)
```

- [ ] **Step 7: Vérifier l'import et les tests**

Run: `uv run python -c "import src.app"`
Expected: aucune erreur.
Run: `uv run pytest tests/saved_views -v`
Expected: PASS.

- [ ] **Step 8: Vérification manuelle (smoke test)**

Avec un compte abonné, aller sur `/compte/vues` : la liste des vues s'affiche ; « Supprimer » retire une vue ; « Renommer » ouvre la modale et met à jour le nom. Vérifier qu'un·e non-abonné·e est redirigé·e vers `/compte/abonnement`.

- [ ] **Step 9: Commit**

```bash
git add src/pages/_compte_shell.py src/pages/compte_vues.py tests/saved_views/test_compte_vues.py
git commit -m "feat: page /compte/vues (liste, renommer, supprimer) #95"
```

---

## Task 6: Vérification finale

- [ ] **Step 1: Lancer toute la suite**

Run: `uv run pytest`
Expected: PASS (les tests Selenium peuvent nécessiter Chrome ; au minimum `tests/saved_views`, `tests/test_compte_shell.py`, `tests/subscriptions` doivent passer).

- [ ] **Step 2: Vérifier le formatage**

Run: `uv run ruff format --check src/saved_views src/pages/compte_vues.py`
Expected: déjà formaté (sinon lancer `uv run ruff format` et committer).

- [ ] **Step 3: Commit final si nécessaire**

```bash
git add -A
git commit -m "chore: formatage vues sauvegardées #95"
```

---

## Self-Review

**Couverture de la spec :**

- Stockage `saved_views` dans `users.sqlite` → Task 1. ✓
- Vue = nom + query (`filtres`/`tris`/`colonnes`), réutilise le mécanisme existant → Task 2 (`build_view_query`) + Task 4. ✓
- Bouton « Sauvegarder la vue » + modale de nommage → Task 4. ✓
- Menu déroulant des vues, application par navigation → Task 4 (`saved_views_items`, liens `/tableau?<query>` + `restore_view_from_url` existant). ✓
- Masquage pour non-abonné·es + contrôle serveur → Task 4 (`toggle_saved_views_bar`, `save_view` re-vérifie l'abonnement). ✓
- Gestion `/compte/vues` (liste, renommer, supprimer), section gatée → Task 5. ✓
- Isolation par `user_id`, cascade → Task 1 (tests). ✓
- Hors périmètre titulaire/acheteur, colonne `table_name` réservée → respecté (`table_name="tableau"` partout). ✓
- Tests DB + gating → Tasks 1, 3, 5. ✓

**Scan placeholders :** aucun TBD/TODO ; tout le code est fourni.

**Cohérence des types/noms :** `build_view_query(filter_query, sort_by, hidden_columns)` cohérent Task 2↔4 ; `upsert(user_id, table_name, name, query)`, `list_views(user_id, table_name)`, `rename(view_id, user_id, new_name)`, `delete(view_id, user_id)` cohérents Task 1↔4↔5 ; `prepare_view_to_save(has_subscription, name) -> (clean_name, error)` cohérent Task 3↔4 ; ids des composants pattern-matching (`vue-delete`, `vue-rename-open`) cohérents `ui.py`↔`compte_vues.py`.
