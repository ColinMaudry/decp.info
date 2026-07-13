# Partage de vues sauvegardées par URL courte — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre une vue sauvegardée partageable via une URL courte `?vue=<slug>_<token>` que `/tableau` résout et applique côté serveur, ouverte au public.

**Architecture:** Un jeton aléatoire base62(6) devient la clé publique et immuable de chaque vue (colonne `token` sur `saved_views`). L'URL `?vue=<slug>_<token>` porte un slug décoratif en tirets + le jeton après un `_` séparateur ; la résolution ignore le slug et cherche par jeton. `/tableau` résout le paramètre au chargement, applique filtres/tris/colonnes, et affiche un bloc « URL directe » masqué à la première modification de l'état (verrou one-shot).

**Tech Stack:** Python, Dash 4.4, SQLite (via `src.auth.db.get_conn`), `unidecode`, `secrets`, `dash-ag-grid`, `dcc.Clipboard`.

## Global Constraints

- Imports internes préfixés `src.` (ex. `from src.saved_views import db`), jamais `saved_views.db`.
- Créer/sauvegarder une vue = abonnés uniquement (inchangé). **Ouvrir par URL = public**, aucun contrôle d'abonnement.
- Jeton : **6 caractères base62** `[0-9a-zA-Z]`, générés par `secrets`.
- Slug : **tirets** `-` (pas d'underscore) ; séparateur slug↔jeton = `_` ; parsing = `rsplit("_", 1)[-1]`.
- Message de repli **identique** dans tous les cas d'échec : `« Cette vue est introuvable ou a été supprimée. »` (anti-énumération).
- URL absolue : `https://{DOMAIN_NAME}/tableau?vue=...` où `DOMAIN_NAME` vient de `src.utils`.
- Avant tout `git add`/commit : lancer `pre-commit` (formatage ruff/prettier).
- Lancer les tests avec `uv run pytest <chemin>` ; **suite complète (`uv run pytest`) uniquement à la dernière tâche**.

## File Structure

- `src/saved_views/db.py` (modif) — colonne `token`, `generate_token`, `upsert` renvoie le jeton, `get_by_token`, backfill dans `init_schema`.
- `src/migrations.py` (modif) — migration `0012_add_token_to_saved_views`.
- `src/saved_views/ui.py` (modif) — `slugify`, `build_view_url`, `token_from_vue_param` ; `_view_row` avec `dcc.Clipboard` + « Ouvrir » vers l'URL courte.
- `src/saved_views/resolve.py` (nouveau) — `resolve_vue_param` (fonction pure, testable sans Dash).
- `src/pages/tableau.py` (modif) — stores + bloc de partage + callbacks de résolution/affichage/dérive ; `apply_saved_view` et `save_view` alimentent les stores.
- Tests : `tests/saved_views/test_db.py`, `test_ui.py`, `test_resolve.py` (nouveau), `test_tableau_share.py` (nouveau), `test_compte_vues.py`.

---

### Task 1 : Colonne `token`, génération, `get_by_token`, backfill

**Files:**

- Modify: `src/saved_views/db.py`
- Modify: `src/migrations.py`
- Test: `tests/saved_views/test_db.py`

**Interfaces:**

- Consumes: `src.auth.db.get_conn`.
- Produces:

  - `generate_token(length: int = 6) -> str` — base62.
  - `upsert(user_id: int, table_name: str, name: str, query: str) -> str` — renvoie le jeton (nouveau à l'insertion, **inchangé** à l'écrasement).
  - `get_by_token(token: str) -> sqlite3.Row | None` — lookup public, sans filtre `user_id`.
  - `init_schema()` crée la colonne `token`, l'index unique, et backfille les lignes `token IS NULL`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/saved_views/test_db.py` (le fichier importe déjà `from src.saved_views import db`, `from src.auth import db as auth_db`, et définit `_make_user`) :

```python
import string


def test_generate_token_is_base62_and_length_6():
    token = db.generate_token()
    assert len(token) == 6
    alphabet = set(string.ascii_letters + string.digits)
    assert set(token) <= alphabet


def test_upsert_returns_token_on_insert(users_db_path):
    db.init_schema()
    uid = _make_user()
    token = db.upsert(uid, "tableau", "Ma vue", "q1")
    assert token
    assert db.list_views(uid, "tableau")[0]["token"] == token


def test_upsert_preserves_token_on_overwrite(users_db_path):
    db.init_schema()
    uid = _make_user()
    token1 = db.upsert(uid, "tableau", "Ma vue", "q1")
    token2 = db.upsert(uid, "tableau", "Ma vue", "q2")
    assert token2 == token1  # écrasement → lien stable
    assert db.list_views(uid, "tableau")[0]["query"] == "q2"


def test_get_by_token_public_lookup(users_db_path):
    db.init_schema()
    uid = _make_user()
    token = db.upsert(uid, "tableau", "Ma vue", "q1")
    row = db.get_by_token(token)
    assert row is not None
    assert row["name"] == "Ma vue"
    assert db.get_by_token("zzzzzz") is None


def test_tokens_are_unique_across_views(users_db_path):
    db.init_schema()
    uid = _make_user()
    t1 = db.upsert(uid, "tableau", "Vue A", "a")
    t2 = db.upsert(uid, "tableau", "Vue B", "b")
    assert t1 != t2


def test_backfill_assigns_tokens_to_null_rows(users_db_path):
    db.init_schema()
    uid = _make_user()
    conn = auth_db.get_conn()
    # Simule une ligne pré-migration (token NULL) en contournant upsert.
    conn.execute(
        "INSERT INTO saved_views "
        "(user_id, table_name, name, query, token, created_at, updated_at) "
        "VALUES (?, 'tableau', 'Ancienne', 'q', NULL, '', '')",
        (uid,),
    )
    db.init_schema()  # doit backfiller
    row = conn.execute(
        "SELECT token FROM saved_views WHERE name = 'Ancienne'"
    ).fetchone()
    assert row["token"] and len(row["token"]) == 6
    # Idempotent : un second appel ne change pas le jeton attribué.
    token_after_first = row["token"]
    db.init_schema()
    row2 = conn.execute(
        "SELECT token FROM saved_views WHERE name = 'Ancienne'"
    ).fetchone()
    assert row2["token"] == token_after_first
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_db.py -q`
Expected: FAIL (`AttributeError: module 'src.saved_views.db' has no attribute 'generate_token'` / `get_by_token`, et `KeyError: 'token'`).

- [ ] **Step 3: Implémenter dans `src/saved_views/db.py`**

En tête du fichier, ajouter les imports :

```python
import secrets
import string
```

Remplacer la constante `SCHEMA` par (ajout de la colonne `token` et de l'index unique) :

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_views (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    table_name  TEXT NOT NULL DEFAULT 'tableau',
    name        TEXT NOT NULL,
    query       TEXT NOT NULL,
    token       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, table_name, name)
);
CREATE INDEX IF NOT EXISTS idx_saved_views_user
    ON saved_views(user_id, table_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_saved_views_token
    ON saved_views(token);
"""

_TOKEN_ALPHABET = string.ascii_letters + string.digits  # base62


def generate_token(length: int = 6) -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length))


def _unique_token(conn) -> str:
    while True:
        token = generate_token()
        exists = conn.execute(
            "SELECT 1 FROM saved_views WHERE token = ?", (token,)
        ).fetchone()
        if exists is None:
            return token
```

Remplacer `init_schema` (ajout du backfill) :

```python
def init_schema() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Backfill des lignes pré-migration (token NULL). L'index unique tolère
    # plusieurs NULL transitoires ; on attribue un jeton à chacune. Idempotent :
    # sans effet une fois toutes les lignes pourvues.
    null_rows = conn.execute(
        "SELECT id FROM saved_views WHERE token IS NULL"
    ).fetchall()
    for row in null_rows:
        conn.execute(
            "UPDATE saved_views SET token = ? WHERE id = ?",
            (_unique_token(conn), row["id"]),
        )
```

Remplacer `upsert` (génère + renvoie le jeton, préservé à l'écrasement) :

```python
def upsert(user_id: int, table_name: str, name: str, query: str) -> str:
    now = _now()
    conn = get_conn()
    # Jeton candidat, utilisé uniquement en cas d'INSERT réel ; à l'écrasement
    # (ON CONFLICT ... DO UPDATE), `token` n'est pas dans le SET → conservé.
    conn.execute(
        "INSERT INTO saved_views "
        "(user_id, table_name, name, query, token, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, table_name, name) DO UPDATE SET "
        "query = excluded.query, updated_at = excluded.updated_at",
        (user_id, table_name, name, query, _unique_token(conn), now, now),
    )
    row = conn.execute(
        "SELECT token FROM saved_views "
        "WHERE user_id = ? AND table_name = ? AND name = ?",
        (user_id, table_name, name),
    ).fetchone()
    return row["token"]
```

Ajouter `get_by_token` (après `get`) :

```python
def get_by_token(token: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute("SELECT * FROM saved_views WHERE token = ?", (token,))
        .fetchone()
    )
```

Dans `src/migrations.py`, ajouter à la fin de la liste `_MIGRATIONS` :

```python
    (
        "0012_add_token_to_saved_views",
        "ALTER TABLE saved_views ADD COLUMN token TEXT",
    ),
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_db.py -q`
Expected: PASS (tous, y compris les tests existants).

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/saved_views/db.py src/migrations.py tests/saved_views/test_db.py
git add src/saved_views/db.py src/migrations.py tests/saved_views/test_db.py
git commit -m "feat(vues): jeton public + get_by_token + backfill (#112)"
```

---

### Task 2 : Slug, construction et parsing d'URL

**Files:**

- Modify: `src/saved_views/ui.py`
- Test: `tests/saved_views/test_ui.py`

**Interfaces:**

- Consumes: `unidecode`, `src.utils.DOMAIN_NAME`.
- Produces:

  - `slugify(name: str | None) -> str` — minuscule, ASCII, non-alphanum → `-`, collapse/trim, jamais d'`_`.
  - `build_view_url(name: str, token: str) -> str` — `https://{DOMAIN_NAME}/tableau?vue=<slug>_<token>` (préfixe slug omis si vide).
  - `token_from_vue_param(value: str | None) -> str | None` — segment après le dernier `_` ; `None` si vide.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/saved_views/test_ui.py` :

```python
def test_slugify_accents_spaces_case():
    assert ui.slugify("Mes Marchés 2024") == "mes-marches-2024"


def test_slugify_special_chars_collapse_and_trim():
    assert ui.slugify("  Éà!! ---  test__ok  ") == "ea-test-ok"


def test_slugify_never_contains_underscore():
    assert "_" not in ui.slugify("a_b c")


def test_slugify_empty():
    assert ui.slugify("") == ""
    assert ui.slugify(None) == ""


def test_build_view_url_dev_domain(monkeypatch):
    # DOMAIN_NAME est résolu à l'import ; on patche l'attribut du module ui.
    monkeypatch.setattr(ui, "DOMAIN_NAME", "test.colibre.fr")
    url = ui.build_view_url("Mes Marchés", "abc123")
    assert url == "https://test.colibre.fr/tableau?vue=mes-marches_abc123"


def test_build_view_url_empty_slug_omits_prefix(monkeypatch):
    monkeypatch.setattr(ui, "DOMAIN_NAME", "test.colibre.fr")
    url = ui.build_view_url("!!!", "abc123")
    assert url == "https://test.colibre.fr/tableau?vue=abc123"


def test_token_from_vue_param():
    assert ui.token_from_vue_param("mes-marches-2024_abc123") == "abc123"
    assert ui.token_from_vue_param("zzz_abc123") == "abc123"
    assert ui.token_from_vue_param("abc123") == "abc123"
    assert ui.token_from_vue_param("") is None
    assert ui.token_from_vue_param(None) is None
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_ui.py -q`
Expected: FAIL (`AttributeError: module 'src.saved_views.ui' has no attribute 'slugify'`).

- [ ] **Step 3: Implémenter dans `src/saved_views/ui.py`**

En tête, ajouter les imports :

```python
import re

from unidecode import unidecode

from src.utils import DOMAIN_NAME
```

Ajouter les fonctions (par ex. après `clean_view_name`) :

```python
def slugify(name: str | None) -> str:
    """Slug décoratif en tirets (convention web) : minuscule, translittéré ASCII,
    non-alphanumériques → '-', collapse/trim. Ne contient jamais d'underscore
    (qui sert de séparateur slug↔jeton dans l'URL)."""
    ascii_name = unidecode(name or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


def build_view_url(name: str, token: str) -> str:
    slug = slugify(name)
    prefix = f"{slug}_" if slug else ""
    return f"https://{DOMAIN_NAME}/tableau?vue={prefix}{token}"


def token_from_vue_param(value: str | None) -> str | None:
    """Extrait le jeton du paramètre ?vue=. Le jeton base62 ne contient pas d'`_`
    et le slug est en tirets, donc le segment après le dernier `_` est le jeton
    (`?vue=abc123` sans slug fonctionne aussi)."""
    if not value:
        return None
    token = value.rsplit("_", 1)[-1]
    return token or None
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_ui.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/saved_views/ui.py tests/saved_views/test_ui.py
git add src/saved_views/ui.py tests/saved_views/test_ui.py
git commit -m "feat(vues): slugify + build_view_url + parsing du jeton (#112)"
```

---

### Task 3 : Résolveur pur `resolve_vue_param`

**Files:**

- Create: `src/saved_views/resolve.py`
- Test: `tests/saved_views/test_resolve.py` (nouveau)

**Interfaces:**

- Consumes: `src.saved_views.db.get_by_token`, `src.saved_views.ui.token_from_vue_param`, `src.saved_views.ui.build_view_url`, `src.utils.query_ast.{ast_from_dict, ast_to_filtermodel}`.
- Produces:

  - `NOT_FOUND_MESSAGE: str = "Cette vue est introuvable ou a été supprimée."`
  - `resolve_vue_param(vue_param: str | None, schema) -> dict` avec les clés :
    `found: bool`, `filter_model: dict | None`, `column_state: list | None`,
    `hidden_columns: list | None`, `token: str | None`, `url: str | None`, `error: str | None`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/saved_views/test_resolve.py` :

```python
import json

from src.auth import db as auth_db
from src.db import schema
from src.saved_views import db as saved_views_db
from src.saved_views import resolve
from src.utils.query_ast import And, Condition, ast_to_dict


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def _seed_view(uid, name="Ma vue"):
    ast = And([Condition("objet", "contains", "route")])
    column_state = [
        {"colId": "montant", "sort": "desc"},
        {"colId": "acheteur_nom", "hide": True},
    ]
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": column_state})
    return saved_views_db.upsert(uid, "tableau", name, query)


def test_resolve_found_applies_view(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed_view(uid, "Mes Marchés")

    out = resolve.resolve_vue_param(f"mes-marches_{token}", schema)

    assert out["found"] is True
    assert out["filter_model"] == {
        "objet": {"filterType": "text", "type": "contains", "filter": "route"}
    }
    assert out["hidden_columns"] == ["acheteur_nom"]
    assert out["token"] == token
    assert out["url"] == f"https://test.colibre.fr/tableau?vue=mes-marches_{token}"
    assert out["error"] is None


def test_resolve_slug_is_ignored(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed_view(uid)
    # Slug bidon → même résolution.
    out = resolve.resolve_vue_param(f"nimportequoi_{token}", schema)
    assert out["found"] is True
    assert out["token"] == token


def test_resolve_unknown_token_returns_error(users_db_path):
    saved_views_db.init_schema()
    _make_user()
    out = resolve.resolve_vue_param("slug_zzzzzz", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE
    assert out["filter_model"] is None


def test_resolve_empty_param_returns_error(users_db_path):
    saved_views_db.init_schema()
    out = resolve.resolve_vue_param("", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE


def test_resolve_corrupt_query_returns_error(users_db_path):
    saved_views_db.init_schema()
    uid = _make_user()
    # query pré-migration (pas du JSON) → même message de repli.
    token = saved_views_db.upsert(uid, "tableau", "Vieille", "filtres=a&tris=b")
    out = resolve.resolve_vue_param(f"vieille_{token}", schema)
    assert out["found"] is False
    assert out["error"] == resolve.NOT_FOUND_MESSAGE
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_resolve.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.saved_views.resolve'`).

- [ ] **Step 3: Implémenter `src/saved_views/resolve.py`**

```python
"""Résolution publique d'une vue depuis le paramètre d'URL ?vue=<slug>_<token>.

Fonction pure (aucune dépendance à Dash), testable directement : elle prend le
paramètre brut et le schéma, renvoie un dict décrivant la vue à appliquer ou une
erreur. Le slug est ignoré ; seul le jeton fait foi.
"""

import json

from src.saved_views import db
from src.saved_views import ui
from src.utils import logger
from src.utils.query_ast import ast_from_dict, ast_to_filtermodel

NOT_FOUND_MESSAGE = "Cette vue est introuvable ou a été supprimée."


def _error() -> dict:
    return {
        "found": False,
        "filter_model": None,
        "column_state": None,
        "hidden_columns": None,
        "token": None,
        "url": None,
        "error": NOT_FOUND_MESSAGE,
    }


def resolve_vue_param(vue_param: str | None, schema) -> dict:
    token = ui.token_from_vue_param(vue_param)
    if not token:
        return _error()
    row = db.get_by_token(token)
    if row is None:
        return _error()
    try:
        view = json.loads(row["query"])
        # AST canonique stocké par save_view (cf. spec vues sauvegardées).
        ast = ast_from_dict(view.get("ast"))
        filter_model = ast_to_filtermodel(ast, schema)
        column_state = view.get("columnState") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        # Vue pré-migration (query string, pas du JSON) : repli propre, même
        # message que pour un jeton inconnu (anti-énumération).
        logger.warning(
            "Vue partagée au format pré-migration, non applicable : "
            f"token={token!r} name={row['name']!r}"
        )
        return _error()
    hidden_columns = [c["colId"] for c in column_state if c.get("hide")]
    return {
        "found": True,
        "filter_model": filter_model,
        "column_state": column_state,
        "hidden_columns": hidden_columns,
        "token": row["token"],
        "url": ui.build_view_url(row["name"], row["token"]),
        "error": None,
    }
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_resolve.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/saved_views/resolve.py tests/saved_views/test_resolve.py
git add src/saved_views/resolve.py tests/saved_views/test_resolve.py
git commit -m "feat(vues): resolveur pur du parametre ?vue= (#112)"
```

---

### Task 4 : `/tableau` — stores, bloc de partage, résolution `?vue=`

**Files:**

- Modify: `src/pages/tableau.py`
- Test: `tests/saved_views/test_tableau_share.py` (nouveau)

**Interfaces:**

- Consumes: `resolve.resolve_vue_param`, `saved_views_ui.build_view_url`, `src.db.schema`.
- Produces (callbacks/stores lus par la Task 5) :

  - Stores `active-view` (`{"token","url"}` | `None`), `suppress-next` (int), `vue-resolution` (dict | `None`).
  - `resolve_vue_from_url(search: str) -> dict | None` (A1) et `apply_vue_resolution(resolution) -> tuple` (A2, 6 sorties).
  - Bloc `share-url-box` (`html.Div` masqué), `share-url-input` (`dcc.Input` lecture seule), `vue-resolve-feedback` (`html.Div`).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/saved_views/test_tableau_share.py` :

```python
import json

import dash

import src.app  # noqa: F401  # instancie l'app → register_page()
from src.auth import db as auth_db
from src.pages import tableau
from src.saved_views import db as saved_views_db
from src.saved_views import resolve
from src.utils.query_ast import And, Condition, ast_to_dict


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def _seed(uid, name="Ma vue"):
    ast = And([Condition("objet", "contains", "route")])
    query = json.dumps(
        {"ast": ast_to_dict(ast), "columnState": [{"colId": "montant", "hide": True}]}
    )
    return saved_views_db.upsert(uid, "tableau", name, query)


def test_resolve_vue_from_url_found(monkeypatch, users_db_path):
    monkeypatch.setattr(resolve.ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed(uid)
    out = tableau.resolve_vue_from_url(f"?vue=ma-vue_{token}")
    assert out["found"] is True
    assert out["token"] == token


def test_resolve_vue_from_url_no_param_returns_none(users_db_path):
    saved_views_db.init_schema()
    assert tableau.resolve_vue_from_url("") is None
    assert tableau.resolve_vue_from_url("?autre=1") is None


def test_apply_vue_resolution_found_shows_box(users_db_path):
    resolution = {
        "found": True,
        "filter_model": {"objet": {"filterType": "text", "type": "contains",
                                   "filter": "route"}},
        "column_state": [{"colId": "montant", "hide": True}],
        "hidden_columns": ["montant"],
        "token": "abc123",
        "url": "https://test.colibre.fr/tableau?vue=ma-vue_abc123",
        "error": None,
    }
    fm, cs, hidden, active, suppress, feedback = tableau.apply_vue_resolution(
        resolution
    )
    assert fm == resolution["filter_model"]
    assert cs == resolution["column_state"]
    assert hidden == ["montant"]
    assert active == {"token": "abc123", "url": resolution["url"]}
    assert suppress == 1
    assert feedback == ""


def test_apply_vue_resolution_not_found_shows_alert(users_db_path):
    resolution = {
        "found": False, "filter_model": None, "column_state": None,
        "hidden_columns": None, "token": None, "url": None,
        "error": resolve.NOT_FOUND_MESSAGE,
    }
    fm, cs, hidden, active, suppress, feedback = tableau.apply_vue_resolution(
        resolution
    )
    assert fm is dash.no_update
    assert cs is dash.no_update
    assert active is None
    assert suppress == 0
    assert resolve.NOT_FOUND_MESSAGE in str(feedback)


def test_apply_vue_resolution_none_is_noop(users_db_path):
    out = tableau.apply_vue_resolution(None)
    assert all(v is dash.no_update for v in out)
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_tableau_share.py -q`
Expected: FAIL (`AttributeError: module 'src.pages.tableau' has no attribute 'resolve_vue_from_url'`).

- [ ] **Step 3: Implémenter dans `src/pages/tableau.py`**

Ajouter aux imports en tête :

```python
from urllib.parse import parse_qs
```

et à côté des imports `src.saved_views` :

```python
from src.saved_views import resolve as saved_views_resolve
```

Dans `layout`, ajouter les stores à côté des autres `dcc.Store` (après `dcc.Store(id="saved-views-refresh")` ou dans la liste de tête) :

```python
    dcc.Store(id="active-view"),
    dcc.Store(id="suppress-next", data=0),
    dcc.Store(id="vue-resolution"),
```

Dans `layout`, juste après `html.Div([], id="header"),` insérer la zone de feedback :

```python
    html.Div(id="vue-resolve-feedback"),
```

Dans le bloc `html.Div(className="table-toolbar", ...)`, **juste après** ce `html.Div` de barre d'outils (et avant `html.Div(className="table-meta", ...)`), insérer le bloc de partage :

```python
            html.Div(
                id="share-url-box",
                style={"display": "none"},
                className="d-flex align-items-center gap-2 my-2",
                children=[
                    dbc.Label(
                        "URL directe vers cette vue :",
                        html_for="share-url-input",
                        className="mb-0",
                    ),
                    dcc.Input(
                        id="share-url-input",
                        type="text",
                        readOnly=True,
                        className="form-control form-control-sm",
                        style={"maxWidth": "420px"},
                    ),
                    dcc.Clipboard(
                        target_id="share-url-input",
                        title="Copier le lien vers cette vue",
                        style={"cursor": "pointer", "fontSize": "1.1rem"},
                    ),
                ],
            ),
```

Ajouter les deux callbacks de résolution (par ex. après `toggle_saved_views_bar`) :

```python
def resolve_vue_from_url(search: str) -> dict | None:
    """Extrait ?vue=... de la query string et le résout. Renvoie None s'il n'y a
    pas de paramètre `vue` (chargement normal du tableau)."""
    params = parse_qs((search or "").lstrip("?"))
    values = params.get("vue")
    if not values:
        return None
    return saved_views_resolve.resolve_vue_param(values[0], schema)


@callback(
    Output("vue-resolution", "data"),
    Input("tableau_url", "search"),
)
def store_vue_resolution(search):
    resolution = resolve_vue_from_url(search)
    return resolution if resolution is not None else no_update


def apply_vue_resolution(resolution):
    """Mappe le dict de résolution vers les sorties de la grille + stores. Séparé
    du callback pour être testable sans contexte Dash."""
    if resolution is None:
        return (no_update,) * 6
    if not resolution["found"]:
        return (
            no_update,
            no_update,
            no_update,
            None,  # active-view : masque le bloc de partage
            0,
            html.Div(resolution["error"], className="alert alert-warning py-2"),
        )
    return (
        resolution["filter_model"],
        resolution["column_state"],
        resolution["hidden_columns"],
        {"token": resolution["token"], "url": resolution["url"]},
        1,  # suppress-next : neutralise l'écho de l'application (verrou one-shot)
        "",
    )


@callback(
    Output("tableau_grid", "filterModel", allow_duplicate=True),
    Output("tableau_grid", "columnState", allow_duplicate=True),
    Output("tableau-hidden-columns", "data", allow_duplicate=True),
    Output("active-view", "data", allow_duplicate=True),
    Output("suppress-next", "data", allow_duplicate=True),
    Output("vue-resolve-feedback", "children"),
    Input("vue-resolution", "data"),
    prevent_initial_call=True,
)
def apply_vue_resolution_cb(resolution):
    return apply_vue_resolution(resolution)
```

> **Note Dash importante :** `store_vue_resolution` n'a **aucune** sortie
> `allow_duplicate`, donc il s'exécute au chargement initial (le paramètre `?vue=`
> est présent dès l'ouverture). Il alimente le store intermédiaire `vue-resolution`,
> qui déclenche `apply_vue_resolution_cb` (celui-ci a des sorties `allow_duplicate`
> → `prevent_initial_call=True` obligatoire). Ce découpage en deux callbacks est
> nécessaire : un callback avec des sorties `allow_duplicate` ne peut pas tourner
> au chargement.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_tableau_share.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/tableau.py tests/saved_views/test_tableau_share.py
git add src/pages/tableau.py tests/saved_views/test_tableau_share.py
git commit -m "feat(tableau): resolution ?vue= + bloc URL de partage (#112)"
```

---

### Task 5 : Verrou de dérive + affichage du bloc (menu & sauvegarde)

**Files:**

- Modify: `src/pages/tableau.py`
- Test: `tests/saved_views/test_tableau_share.py`

**Interfaces:**

- Consumes: stores `active-view`, `suppress-next` (Task 4) ; `saved_views_ui.build_view_url`.
- Produces:

  - `render_share_box(active_view) -> tuple[dict, str]` (D) → style de `share-url-box`, valeur de `share-url-input`.
  - `hide_share_box_on_change(filter_model, column_state, suppress) -> tuple` (E).
  - `apply_saved_view` et `save_view` alimentent `active-view` / `suppress-next`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/saved_views/test_tableau_share.py` :

```python
import dash
from unittest.mock import patch


def _fake_user(user_id):
    u = type("U", (), {})()
    u.is_authenticated = True
    u.id = user_id
    return u


class _Ctx:
    triggered_id = None


def test_render_share_box_visible_when_active():
    style, value = tableau.render_share_box(
        {"token": "abc123", "url": "https://x/tableau?vue=a_abc123"}
    )
    assert style == {}
    assert value == "https://x/tableau?vue=a_abc123"


def test_render_share_box_hidden_when_none():
    style, value = tableau.render_share_box(None)
    assert style == {"display": "none"}
    assert value == ""


def test_hide_lock_consumes_echo_then_hides():
    # 1er changement = écho de l'application (suppress=1) → garde la box.
    active, suppress = tableau.hide_share_box_on_change({}, [], 1)
    assert active is dash.no_update
    assert suppress == 0
    # Changement réel suivant (suppress=0) → masque.
    active2, suppress2 = tableau.hide_share_box_on_change({"objet": {}}, [], 0)
    assert active2 is None
    assert suppress2 == 0


def test_apply_saved_view_sets_active_and_suppress(monkeypatch, users_db_path):
    monkeypatch.setattr(tableau.saved_views_ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed(uid, "Ma vue")
    view_id = saved_views_db.list_views(uid, "tableau")[0]["id"]
    _Ctx.triggered_id = {"type": "saved-view-item", "index": view_id}
    monkeypatch.setattr(tableau, "ctx", _Ctx)
    with patch.object(tableau, "current_user", _fake_user(uid)):
        out = tableau.apply_saved_view(
            [1], [{"type": "saved-view-item", "index": view_id}]
        )
    # (filter_model, column_state, hidden, active-view, suppress-next)
    assert out[3] == {"token": token,
                      "url": f"https://test.colibre.fr/tableau?vue=ma-vue_{token}"}
    assert out[4] == 1


def test_save_view_shows_box(monkeypatch, users_db_path):
    monkeypatch.setattr(tableau.saved_views_ui, "DOMAIN_NAME", "test.colibre.fr")
    saved_views_db.init_schema()
    uid = _make_user()
    monkeypatch.setattr(tableau, "current_user_has_subscription", lambda: True)
    with patch.object(tableau, "current_user", _fake_user(uid)):
        out = tableau.save_view(1, "Nouvelle", {}, [])
    # (is_open, feedback, refresh, active-view, suppress-next)
    assert out[3]["url"].startswith("https://test.colibre.fr/tableau?vue=nouvelle_")
    assert out[4] == 0  # sauvegarde ne modifie pas la grille → pas d'écho
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_tableau_share.py -q`
Expected: FAIL (`AttributeError: ... 'render_share_box'`, et longueurs de tuple incorrectes pour `apply_saved_view`/`save_view`).

- [ ] **Step 3: Implémenter dans `src/pages/tableau.py`**

Ajouter les deux nouveaux callbacks (après `apply_vue_resolution_cb`) :

```python
@callback(
    Output("share-url-box", "style"),
    Output("share-url-input", "value"),
    Input("active-view", "data"),
)
def render_share_box(active_view):
    if active_view and active_view.get("url"):
        return {}, active_view["url"]
    return {"display": "none"}, ""


@callback(
    Output("active-view", "data", allow_duplicate=True),
    Output("suppress-next", "data", allow_duplicate=True),
    Input("tableau_grid", "filterModel"),
    Input("tableau_grid", "columnState"),
    State("suppress-next", "data"),
    prevent_initial_call=True,
)
def hide_share_box_on_change(_filter_model, _column_state, suppress):
    # Verrou « sale » à sens unique. L'application d'une vue modifie elle-même
    # filterModel/columnState (écho) : on l'absorbe une fois (suppress>0), puis
    # tout changement réel masque la box en effaçant active-view.
    if suppress and suppress > 0:
        return no_update, suppress - 1
    return None, 0
```

> **Note :** `render_share_box` et `hide_share_box_on_change` ci-dessus sont des
> callbacks Dash. Les fonctions Python sous-jacentes portent le même nom et sont
> appelées directement dans les tests (Dash n'enveloppe pas la fonction).

Modifier `apply_saved_view` — remplacer sa signature de sorties et son corps pour
ajouter `active-view` + `suppress-next`. Le décorateur devient :

```python
@callback(
    Output("tableau_grid", "filterModel"),
    Output("tableau_grid", "columnState"),
    Output("tableau-hidden-columns", "data", allow_duplicate=True),
    Output("active-view", "data", allow_duplicate=True),
    Output("suppress-next", "data", allow_duplicate=True),
    Input({"type": "saved-view-item", "index": ALL}, "n_clicks"),
    State({"type": "saved-view-item", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def apply_saved_view(n_clicks, ids):
    triggered = ctx.triggered_id
    if not triggered or not any(n_clicks):
        return no_update, no_update, no_update, no_update, no_update
    row = saved_views_db.get(triggered["index"], current_user.id)
    if not row:
        return no_update, no_update, no_update, no_update, no_update
    try:
        view = json.loads(row["query"])
        ast = ast_from_dict(view.get("ast"))
        filter_model = ast_to_filtermodel(ast, schema)
        column_state = view.get("columnState") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        logger.warning(
            "Vue sauvegardée au format pré-migration, impossible de l'appliquer : "
            f"id={row['id']!r} name={row['name']!r}"
        )
        return no_update, no_update, no_update, no_update, no_update
    hidden_columns = [c["colId"] for c in column_state if c.get("hide")]
    active = {
        "token": row["token"],
        "url": saved_views_ui.build_view_url(row["name"], row["token"]),
    }
    return filter_model, column_state, hidden_columns, active, 1
```

Modifier `save_view` — ajouter les deux sorties et alimenter les stores :

```python
@callback(
    Output("save-view-modal", "is_open", allow_duplicate=True),
    Output("save-view-feedback", "children"),
    Output("saved-views-refresh", "data"),
    Output("active-view", "data", allow_duplicate=True),
    Output("suppress-next", "data", allow_duplicate=True),
    Input("btn-save-view-confirm", "n_clicks"),
    State("save-view-name", "value"),
    State("tableau_grid", "filterModel"),
    State("tableau_grid", "columnState"),
    prevent_initial_call=True,
)
def save_view(_n, name, filter_model, column_state):
    has_sub = current_user_has_subscription()
    clean_name, error = saved_views_ui.prepare_view_to_save(has_sub, name)
    if error:
        return (
            True,
            html.Span(error, style={"color": "red"}),
            no_update,
            no_update,
            no_update,
        )
    ast = filtermodel_to_ast(filter_model, schema)
    query = json.dumps({"ast": ast_to_dict(ast), "columnState": column_state or []})
    token = saved_views_db.upsert(current_user.id, "tableau", clean_name, query)
    active = {"token": token, "url": saved_views_ui.build_view_url(clean_name, token)}
    return (
        False,
        html.Span(f"Vue « {clean_name} » enregistrée.", style={"color": "green"}),
        clean_name,
        active,
        0,  # la sauvegarde ne modifie pas la grille → pas d'écho à absorber
    )
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_tableau_share.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/tableau.py tests/saved_views/test_tableau_share.py
git add src/pages/tableau.py tests/saved_views/test_tableau_share.py
git commit -m "feat(tableau): verrou de derive + affichage du bloc de partage (#112)"
```

---

### Task 6 : `/compte/vues` — « Ouvrir » vers l'URL courte + bouton copier

**Files:**

- Modify: `src/saved_views/ui.py` (`_view_row`)
- Test: `tests/saved_views/test_ui.py`

**Interfaces:**

- Consumes: `build_view_url` (Task 2), `dcc.Clipboard`.
- Produces: `_view_row(view)` avec « Ouvrir » → `build_view_url(view["name"], view["token"])` et un `dcc.Clipboard` copiant cette URL.

- [ ] **Step 1: Écrire les tests qui échouent**

Le helper `_view` de `tests/saved_views/test_ui.py` construit un `_Row` sans `token`.
Le mettre à jour et ajouter les assertions. Remplacer la définition de `_view` :

```python
def _view(view_id, name, query, token="abc123"):
    return _Row(id=view_id, name=name, query=query, token=token)
```

Ajouter :

```python
def test_view_row_open_uses_short_url(monkeypatch):
    monkeypatch.setattr(ui, "DOMAIN_NAME", "test.colibre.fr")
    row = ui._view_row(_view(1, "Mes Marchés", "q", token="tok123"))
    text = str(row)
    assert "https://test.colibre.fr/tableau?vue=mes-marches_tok123" in text


def test_view_row_has_clipboard_with_url(monkeypatch):
    monkeypatch.setattr(ui, "DOMAIN_NAME", "test.colibre.fr")
    row = ui._view_row(_view(1, "Mes Marchés", "q", token="tok123"))
    text = str(row)
    assert "Clipboard" in text
    assert "Copier le lien" in text
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `uv run pytest tests/saved_views/test_ui.py -q`
Expected: FAIL (l'URL courte n'est pas dans le rendu ; pas de `Clipboard`).

- [ ] **Step 3: Implémenter dans `src/saved_views/ui.py`**

Ajouter `dcc` à l'import Dash en tête :

```python
from dash import dcc, html
```

Remplacer `_view_row` (le bouton « Ouvrir » pointe vers l'URL courte, ajout d'un
`dcc.Clipboard`) :

```python
def _view_row(view) -> html.Div:
    view_id = view["id"]
    share_url = build_view_url(view["name"], view["token"])
    return html.Div(
        className="saved-view-row d-flex align-items-center gap-2 mb-2",
        children=[
            html.Span(view["name"], className="flex-grow-1"),
            dbc.Button(
                "Ouvrir",
                href=share_url,
                color="link",
                size="sm",
            ),
            dcc.Clipboard(
                content=share_url,
                title="Copier le lien vers cette vue",
                style={"cursor": "pointer", "fontSize": "1.1rem"},
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
```

> Le commentaire obsolète « Limitation connue : la vue n'est pas appliquée
> automatiquement… » est supprimé avec l'ancien `href="/tableau"` : la vue est
> désormais bien appliquée via `?vue=`.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `uv run pytest tests/saved_views/test_ui.py tests/saved_views/test_compte_vues.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/saved_views/ui.py tests/saved_views/test_ui.py
git add src/saved_views/ui.py tests/saved_views/test_ui.py
git commit -m "feat(compte/vues): Ouvrir via URL courte + bouton copier (#112)"
```

---

### Task 7 : Validation E2E + suite complète

**Files:**

- Test: `tests/saved_views/test_tableau_share.py` (ajout d'un test d'intégration Dash)

**Interfaces:**

- Consumes: tout ce qui précède. Valide l'hypothèse d'écho unique (verrou `suppress-next=1`).

- [ ] **Step 1: Écrire le test d'intégration**

Ajouter à `tests/saved_views/test_tableau_share.py` un test Selenium qui ouvre
`/tableau?vue=<token>` et vérifie l'application + l'affichage/masquage de la box.
Suivre le patron des tests existants dans `tests/test_main.py` (fixture
`dash_duo` / `DashComposite`). Repérer d'abord le patron :

```bash
grep -n "dash_duo\|DashComposite\|start_server" tests/test_main.py | head
```

Puis écrire (adapter les sélecteurs au patron repéré) :

```python
def test_open_shared_view_applies_and_shows_box(dash_duo, users_db_path):
    """?vue=<token> applique la vue et affiche le bloc de partage ; une
    modification de filtre le masque et il ne revient pas."""
    saved_views_db.init_schema()
    uid = _make_user()
    token = _seed(uid, "Ma vue")

    import src.app as app_module

    dash_duo.start_server(app_module.app)
    dash_duo.wait_for_page(url=dash_duo.server_url + f"/tableau?vue=ma-vue_{token}")

    # Le bloc de partage est visible et contient l'URL.
    box = dash_duo.wait_for_element("#share-url-box", timeout=10)
    assert box.value_of_css_property("display") != "none"
    share_input = dash_duo.find_element("#share-url-input")
    assert token in share_input.get_attribute("value")

    # Après un changement de filtre (via l'API du grid), la box se masque.
    dash_duo.driver.execute_script(
        "document.querySelector('#tableau_grid')"
        ".dash_ag_grid = true;"  # placeholder : déclencher un filterModel change
    )
    # NB : le déclenchement exact du changement de filtre dépend du patron
    # AG Grid du projet ; consulter tests/test_main.py pour la bonne technique
    # d'interaction (saisie dans un filtre de colonne). Vérifier ensuite :
    #   box masqué (display == "none") et non réaffiché.
```

> **Important pour l'exécutant :** ce test valide l'hypothèse « une seule
> invocation coalescée » du callback `hide_share_box_on_change`. Si, en pratique,
> ouvrir une vue masque immédiatement la box (l'écho a déclenché **deux**
> invocations, pas une), corriger en posant `suppress-next=2` à l'application dans
> `apply_vue_resolution` et `apply_saved_view`, et documenter le constat dans un
> commentaire. Ne pas monter `suppress-next` au-delà du nombre d'échos réellement
> observés (sinon le premier vrai changement serait absorbé). Finaliser l'interaction
> de filtre en s'inspirant strictement de `tests/test_main.py`.

- [ ] **Step 2: Lancer le test E2E**

Run: `uv run pytest tests/saved_views/test_tableau_share.py -q`
Expected: PASS (nécessite Chrome/Chromium).

- [ ] **Step 3: Lancer la suite complète**

Run: `uv run pytest`
Expected: PASS (aucune régression sur les vues sauvegardées, le tableau, `/compte/vues`).

- [ ] **Step 4: Commit**

```bash
pre-commit run --all-files
git add -A
git commit -m "test(vues): E2E partage par URL courte + validation ecouteur d'echo (#112)"
```

---

## Self-Review

**Couverture du spec :**

- Format `?vue=<slug>_<token>`, jeton base62(6) = clé → Task 1, 2. ✓
- Slug en tirets, séparateur `_`, parsing `rsplit` → Task 2. ✓
- Modèle : colonne `token` + index unique + migration 0012 + backfill → Task 1. ✓
- `upsert` préserve le jeton à l'écrasement (lien stable) → Task 1. ✓
- Résolution publique, sans gating, message de repli identique → Task 3, 4. ✓
- Bloc URL sur `/tableau` (input lecture seule + Clipboard + infobulle), affiché à
  l'ouverture/sauvegarde → Task 4, 5. ✓
- Verrou de dérive one-shot (écho absorbé, sens unique) → Task 5. ✓
- `/compte/vues` : « Ouvrir » via URL courte + Clipboard → Task 6. ✓
- Gating inchangé (créer = abonnés) → `save_view` conserve `prepare_view_to_save` (Task 5). ✓
- E2E léger + validation de l'hypothèse d'écho → Task 7. ✓

**Cohérence des types :**

- `upsert(...) -> str`, `get_by_token(token) -> Row | None`, `resolve_vue_param(...) -> dict`
  (clés `found/filter_model/column_state/hidden_columns/token/url/error`) utilisées
  de façon cohérente entre Task 1/3/4/5. ✓
- Stores `active-view` (`{"token","url"}` | `None`), `suppress-next` (int) cohérents
  entre Task 4 et 5. ✓
- `build_view_url(name, token) -> str` : même signature en Task 2/3/5/6. ✓

**Placeholders :** le seul point ouvert (technique d'interaction filtre AG Grid et
nombre d'échos) est explicitement délégué au patron `tests/test_main.py` en Task 7,
avec la marche à suivre corrective — pas un TODO silencieux.
