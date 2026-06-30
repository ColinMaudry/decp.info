# Vote pour les prochaines fonctionnalités (Roadmap) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre aux abonnés de voter pour les prochaines fonctionnalités depuis `/compte/roadmap`, exposer la même roadmap en lecture seule sur `/a-propos/roadmap`, et afficher le changelog du dépôt.

**Architecture:** Le « portefeuille » de votes (solde + curseur d'accumulation) vit sur la table `subscriptions` avec une accumulation paresseuse (pas de cronjob). Un nouveau package `src/roadmap/` (calqué sur `src/saved_views/`) regroupe la récupération des issues GitHub (mises en cache 1 h), le registre des votes émis (`feature_votes`), et les composants d'affichage partagés entre les deux pages.

**Tech Stack:** Python, Dash 3.4 + Dash Bootstrap Components, SQLite (`users.sqlite` via `src.auth.db.get_conn`), `httpx`, `flask_caching`.

## Global Constraints

- Importer tous les modules de l'app avec le préfixe `src.` (ex. `src.roadmap.db`), jamais `roadmap.db`.
- UI en **français**.
- Client HTTP : **`httpx`** uniquement (déjà dépendance). Ne pas ajouter `requests`.
- Cache GitHub : `@cache.memoize(timeout=3600)` (1 heure).
- **Pas** de `GITHUB_TOKEN` : appel anonyme à l'API GitHub publique.
- Dépôt GitHub cible : `ColinMaudry/decp.info`.
- Dash 3.4 : utiliser `dcc.Input` (jamais `html.Input`).
- Lancer les tests avec `uv run pytest` (pas de `source .venv/bin/activate`).
- Les fonctions DB suivent le style existant de `src/subscriptions/db.py` : pas de `conn.commit()` explicite (la connexion auto-commite), helper `_now()` pour les timestamps ISO UTC.
- `+2` votes initiaux à la fin d'essai (passage à `active`), `+1`/semaine en abonnement actif, gel hors abonnement, pas de re-crédit des `+2` au réabonnement, pas de retrait de vote.

---

## File Structure

- `src/subscriptions/db.py` (modifier) — colonnes `votes_balance` / `votes_credited_until` dans le schéma ; fonctions `credit_pending`, `spend_vote`, `freeze_votes_cursor` ; intégration freeze dans `update_from_webhook` et `set_cancelled`.
- `src/migrations.py` (modifier) — migrations `ALTER TABLE` pour les 2 colonnes (DB de prod existante).
- `src/roadmap/__init__.py` (créer) — package vide.
- `src/roadmap/db.py` (créer) — table `feature_votes` (`init_schema`), `record_vote`, `vote_counts`.
- `src/roadmap/github.py` (créer) — `fetch_roadmap_issues()` (caché 1 h).
- `src/roadmap/ui.py` (créer) — `roadmap_content`, `vote_items`, `balance_text`, `changelog_markdown`.
- `src/pages/compte_roadmap.py` (créer) — page abonné `/compte/roadmap` + callback de vote.
- `src/pages/a_propos/roadmap.py` (créer) — page publique `/a-propos/roadmap`.
- `src/pages/_compte_shell.py` (modifier) — entrée nav `roadmap`.
- `src/pages/_apropos_shell.py` (modifier) — entrée nav `roadmap`.
- `src/app.py` (modifier) — lien version → `/a-propos/roadmap` ; appel `roadmap_db.init_schema()`.
- `tests/roadmap/__init__.py`, `tests/roadmap/conftest.py` (créer) — fixtures DB.
- `tests/roadmap/test_db.py`, `tests/roadmap/test_github.py`, `tests/roadmap/test_ui.py` (créer).
- `tests/subscriptions/test_db.py` (modifier) — tests d'accumulation.

> **Note de conception :** la table `feature_votes` est créée via `init_schema()` (`CREATE TABLE IF NOT EXISTS`, idempotent, appelé au démarrage comme `src/saved_views/db.py`), pas via une migration. Les migrations restent réservées à l'ajout de colonnes sur la table `subscriptions` déjà existante en prod (précédent : `0001_add_prix_ht_to_subscriptions`).

---

## Task 1 : Colonnes de votes sur `subscriptions` + migrations

**Files:**

- Modify: `src/subscriptions/db.py` (constante `SUBSCRIPTIONS_SCHEMA`)
- Modify: `src/migrations.py` (`_MIGRATIONS`)
- Test: `tests/subscriptions/test_db.py`

**Interfaces:**

- Produces : table `subscriptions` avec colonnes `votes_balance INTEGER NOT NULL DEFAULT 0` et `votes_credited_until TEXT` (NULL par défaut), disponibles via `db.get_by_user(user_id)["votes_balance"]` / `["votes_credited_until"]`.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter dans `tests/subscriptions/test_db.py` :

```python
def test_init_schema_creates_votes_columns(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    row = db.get_by_user(uid)
    assert row["votes_balance"] == 0
    assert row["votes_credited_until"] is None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/subscriptions/test_db.py::test_init_schema_creates_votes_columns -v`
Expected: FAIL (`no such column: votes_balance` ou `KeyError`)

- [ ] **Step 3: Ajouter les colonnes au schéma**

Dans `src/subscriptions/db.py`, modifier `SUBSCRIPTIONS_SCHEMA` pour ajouter les deux colonnes juste après `trial_used` :

```python
SUBSCRIPTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id                     INTEGER PRIMARY KEY,
    frisbii_customer_handle     TEXT,
    frisbii_subscription_handle TEXT,
    plan                        TEXT,
    prix_ht                     REAL,
    status                      TEXT,
    current_period_end          TEXT,
    trial_used                  INTEGER NOT NULL DEFAULT 0,
    votes_balance               INTEGER NOT NULL DEFAULT 0,
    votes_credited_until        TEXT,
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer
    ON subscriptions(frisbii_customer_handle);
"""
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest tests/subscriptions/test_db.py::test_init_schema_creates_votes_columns -v`
Expected: PASS

- [ ] **Step 5: Ajouter les migrations pour la prod**

Dans `src/migrations.py`, ajouter à la fin de `_MIGRATIONS` :

```python
    (
        "0003_add_votes_balance_to_subscriptions",
        "ALTER TABLE subscriptions ADD COLUMN votes_balance INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "0004_add_votes_credited_until_to_subscriptions",
        "ALTER TABLE subscriptions ADD COLUMN votes_credited_until TEXT",
    ),
```

(`apply_pending()` tolère déjà `duplicate column name` sur une DB fraîche où le schéma contient déjà la colonne.)

- [ ] **Step 6: Commit**

```bash
git add src/subscriptions/db.py src/migrations.py tests/subscriptions/test_db.py
git commit -m "feat: colonnes de votes sur subscriptions #94"
```

---

## Task 2 : Accumulation paresseuse (`credit_pending`) + dépense (`spend_vote`)

**Files:**

- Modify: `src/subscriptions/db.py`
- Test: `tests/subscriptions/test_db.py`

**Interfaces:**

- Consumes : colonnes de la Task 1.
- Produces :

  - `INITIAL_VOTES = 2`, `WEEK_SECONDS = 7 * 24 * 3600`
  - `credit_pending(user_id: int) -> int` — crédite les votes acquis et renvoie le solde courant.
  - `spend_vote(user_id: int) -> bool` — débite 1 vote si le solde le permet, renvoie `True` si débité.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `tests/subscriptions/test_db.py` (les imports `datetime, timedelta, timezone` y sont déjà) :

```python
def _activate(uid, cursor_iso=None):
    """Met l'abonnement en statut actif avec un curseur d'accumulation donné."""
    db.get_conn().execute(
        "UPDATE subscriptions SET status = 'active', votes_credited_until = ? "
        "WHERE user_id = ?",
        (cursor_iso, uid),
    )


def test_credit_pending_grants_initial_two_on_first_active(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    _activate(uid, cursor_iso=None)
    balance = db.credit_pending(uid)
    assert balance == 2
    assert db.get_by_user(uid)["votes_credited_until"] is not None


def test_credit_pending_is_idempotent_same_day(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)
    assert db.credit_pending(uid) == 2  # aucun crédit supplémentaire


def test_credit_pending_adds_one_vote_per_full_week(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    fifteen_days_ago = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    _activate(uid, cursor_iso=fifteen_days_ago)
    # 15 jours = 2 semaines pleines
    assert db.credit_pending(uid) == 2


def test_credit_pending_no_credit_when_not_active(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")  # statut 'pending'
    assert db.credit_pending(uid) == 0


def test_spend_vote_decrements_when_balance_positive(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)  # solde = 2
    assert db.spend_vote(uid) is True
    assert db.get_by_user(uid)["votes_balance"] == 1


def test_spend_vote_refused_when_balance_zero(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    _activate(uid, cursor_iso=None)
    # solde reste 0 tant que credit_pending n'est pas appelé
    assert db.spend_vote(uid) is False
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_db.py -k "credit_pending or spend_vote" -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'credit_pending'`)

- [ ] **Step 3: Implémenter `credit_pending` et `spend_vote`**

Dans `src/subscriptions/db.py`, après `_now()` ajouter les constantes, puis ajouter les fonctions (par exemple après `has_used_trial`). Adapter l'import en tête du fichier : `from datetime import datetime, timedelta, timezone`.

```python
INITIAL_VOTES = 2
WEEK_SECONDS = 7 * 24 * 3600


def _set_votes(user_id: int, balance: int, cursor_iso: str) -> None:
    get_conn().execute(
        "UPDATE subscriptions SET votes_balance = ?, votes_credited_until = ?, "
        "updated_at = ? WHERE user_id = ?",
        (balance, cursor_iso, _now(), user_id),
    )


def credit_pending(user_id: int) -> int:
    """Crédite paresseusement les votes acquis et renvoie le solde courant.

    +2 à la première activation (fin d'essai), puis +1 par semaine pleine tant
    que l'abonnement est actif. Idempotent : ne crédite que des semaines pleines.
    """
    row = get_by_user(user_id)
    if row is None:
        return 0
    balance = row["votes_balance"] or 0
    if row["status"] != "active":
        return balance
    now = datetime.now(timezone.utc)
    cursor = row["votes_credited_until"]
    if cursor is None:
        balance += INITIAL_VOTES
        _set_votes(user_id, balance, now.isoformat())
        return balance
    cur = datetime.fromisoformat(cursor)
    weeks = int((now - cur).total_seconds() // WEEK_SECONDS)
    if weeks > 0:
        balance += weeks
        new_cursor = cur + timedelta(seconds=weeks * WEEK_SECONDS)
        _set_votes(user_id, balance, new_cursor.isoformat())
    return balance


def spend_vote(user_id: int) -> bool:
    """Débite 1 vote si le solde le permet. Renvoie True si un vote a été débité."""
    cur = get_conn().execute(
        "UPDATE subscriptions SET votes_balance = votes_balance - 1, updated_at = ? "
        "WHERE user_id = ? AND votes_balance > 0",
        (_now(), user_id),
    )
    return cur.rowcount > 0
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_db.py -k "credit_pending or spend_vote" -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/db.py tests/subscriptions/test_db.py
git commit -m "feat: accumulation paresseuse et dépense de votes #94"
```

---

## Task 3 : Gel au désabonnement / réabonnement

**Files:**

- Modify: `src/subscriptions/db.py` (`freeze_votes_cursor`, `update_from_webhook`, `set_cancelled`)
- Test: `tests/subscriptions/test_db.py`

**Interfaces:**

- Consumes : `credit_pending`, `get_by_customer` (existant).
- Produces : `freeze_votes_cursor(user_id: int) -> None` — remet le curseur à maintenant si déjà posé (jamais de re-crédit des +2).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter dans `tests/subscriptions/test_db.py` :

```python
def test_reactivation_resets_cursor_without_regranting(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    _activate(uid, cursor_iso=None)
    db.credit_pending(uid)  # +2, curseur posé
    # désabonnement
    db.update_from_webhook("decpinfo-1", "sub_1", "cancelled", _future())
    # période sans abonnement simulée : on recule artificiellement le curseur
    old_cursor = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    db.get_conn().execute(
        "UPDATE subscriptions SET votes_credited_until = ? WHERE user_id = ?",
        (old_cursor, uid),
    )
    # réabonnement
    db.update_from_webhook("decpinfo-1", "sub_1", "active", _future())
    row = db.get_by_user(uid)
    assert row["votes_balance"] == 2  # pas de re-crédit des +2
    # le curseur a été remis ~à maintenant → pas de crédit du gap de 30 jours
    assert db.credit_pending(uid) == 2


def test_trial_to_active_does_not_reset_then_grants_two(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    db.update_from_webhook("decpinfo-1", "sub_1", "trial", _future())
    db.update_from_webhook("decpinfo-1", "sub_1", "active", _future())
    # fin d'essai : credit_pending accorde les +2 initiaux
    assert db.credit_pending(uid) == 2
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_db.py -k "reactivation or trial_to_active" -v`
Expected: FAIL (re-crédit des +2 ou crédit du gap, selon le cas)

- [ ] **Step 3: Implémenter `freeze_votes_cursor` et brancher webhook/cancel**

Dans `src/subscriptions/db.py`, ajouter :

```python
def freeze_votes_cursor(user_id: int) -> None:
    """Réactivation après une période sans abonnement : repart de maintenant.

    Ne fait rien si le curseur est NULL (première activation jamais atteinte) :
    les +2 initiaux restent gérés par credit_pending. Ne re-crédite jamais.
    """
    row = get_by_user(user_id)
    if row is None or row["votes_credited_until"] is None:
        return
    now = _now()
    get_conn().execute(
        "UPDATE subscriptions SET votes_credited_until = ?, updated_at = ? "
        "WHERE user_id = ?",
        (now, now, user_id),
    )
```

Modifier `update_from_webhook` pour banquer avant un gel et réinitialiser le curseur à la réactivation :

```python
def update_from_webhook(
    customer_handle: str,
    subscription_handle: str | None,
    status: str,
    current_period_end: str | None,
) -> None:
    prev = get_by_customer(customer_handle)
    if prev is not None and prev["status"] == "active" and status != "active":
        credit_pending(prev["user_id"])  # banque les semaines acquises avant gel
    trial_flag = 1 if status in _ACCESS_STATUSES else 0
    get_conn().execute(
        "UPDATE subscriptions SET "
        "frisbii_subscription_handle = COALESCE(?, frisbii_subscription_handle), "
        "status = ?, current_period_end = ?, "
        "trial_used = max(trial_used, ?), updated_at = ? "
        "WHERE frisbii_customer_handle = ?",
        (
            subscription_handle,
            status,
            current_period_end,
            trial_flag,
            _now(),
            customer_handle,
        ),
    )
    if prev is not None and prev["status"] != "active" and status == "active":
        freeze_votes_cursor(prev["user_id"])
```

Modifier `set_cancelled` pour banquer les semaines acquises avant de figer le statut :

```python
def set_cancelled(user_id: int, current_period_end: str | None) -> None:
    credit_pending(user_id)  # banque les semaines pleines acquises (statut encore actif)
    get_conn().execute(
        "UPDATE subscriptions SET status = 'cancelled', current_period_end = ?, "
        "updated_at = ? WHERE user_id = ?",
        (current_period_end, _now(), user_id),
    )
```

- [ ] **Step 4: Lancer toute la suite `test_db` pour vérifier qu'elle passe (pas de régression)**

Run: `uv run pytest tests/subscriptions/test_db.py -v`
Expected: PASS (tous les tests, anciens et nouveaux)

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/db.py tests/subscriptions/test_db.py
git commit -m "feat: gel des votes au désabonnement/réabonnement #94"
```

---

## Task 4 : Registre des votes émis (`src/roadmap/db.py`)

**Files:**

- Create: `src/roadmap/__init__.py`
- Create: `src/roadmap/db.py`
- Create: `tests/roadmap/__init__.py`
- Create: `tests/roadmap/conftest.py`
- Test: `tests/roadmap/test_db.py`

**Interfaces:**

- Produces :

  - `init_schema() -> None`
  - `record_vote(user_id: int, issue_number: int) -> None`
  - `vote_counts() -> dict[int, int]` — `{numéro_issue: nombre_total_de_votes}`.

- [ ] **Step 1: Créer le package et les fixtures de test**

Créer `src/roadmap/__init__.py` (vide) et `tests/roadmap/__init__.py` (vide).

Créer `tests/roadmap/conftest.py` :

```python
import pytest

# Dash minimal pour que register_page() fonctionne dans les tests de pages de ce
# répertoire (CONFIG peuplé). Instancié une seule fois, ici, avant tout import de page.
from dash import Dash as _Dash

_Dash(__name__, use_pages=True, pages_folder="", assets_folder="assets")


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

Créer `tests/roadmap/test_db.py` :

```python
from src.auth import db as auth_db
from src.roadmap import db as roadmap_db


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def test_init_schema_creates_feature_votes(users_db_path):
    roadmap_db.init_schema()
    conn = auth_db.get_conn()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "feature_votes" in tables


def test_record_vote_and_counts(users_db_path):
    roadmap_db.init_schema()
    uid = _make_user()
    roadmap_db.record_vote(uid, 42)
    roadmap_db.record_vote(uid, 42)  # vote multiple autorisé
    roadmap_db.record_vote(uid, 7)
    assert roadmap_db.vote_counts() == {42: 2, 7: 1}


def test_vote_counts_empty(users_db_path):
    roadmap_db.init_schema()
    assert roadmap_db.vote_counts() == {}
```

- [ ] **Step 3: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/roadmap/test_db.py -v`
Expected: FAIL (`ModuleNotFoundError` ou `no such table`)

- [ ] **Step 4: Implémenter `src/roadmap/db.py`**

```python
from datetime import datetime, timezone

from src.auth.db import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_votes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    issue_number INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_feature_votes_issue
    ON feature_votes(issue_number);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema() -> None:
    get_conn().executescript(SCHEMA)


def record_vote(user_id: int, issue_number: int) -> None:
    get_conn().execute(
        "INSERT INTO feature_votes (user_id, issue_number, created_at) "
        "VALUES (?, ?, ?)",
        (user_id, issue_number, _now()),
    )


def vote_counts() -> dict[int, int]:
    rows = get_conn().execute(
        "SELECT issue_number, COUNT(*) FROM feature_votes GROUP BY issue_number"
    ).fetchall()
    return {row[0]: row[1] for row in rows}
```

- [ ] **Step 5: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/roadmap/test_db.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Wirer `init_schema` au démarrage**

Dans `src/app.py`, à côté de l'appel existant `saved_views_db.init_schema()` (~ligne 110), ajouter :

```python
from src.roadmap import db as roadmap_db  # noqa: E402

roadmap_db.init_schema()
```

- [ ] **Step 7: Commit**

```bash
git add src/roadmap/__init__.py src/roadmap/db.py src/app.py \
        tests/roadmap/__init__.py tests/roadmap/conftest.py tests/roadmap/test_db.py
git commit -m "feat: registre des votes feature_votes #94"
```

---

## Task 5 : Récupération des issues GitHub (`src/roadmap/github.py`)

**Files:**

- Create: `src/roadmap/github.py`
- Test: `tests/roadmap/test_github.py`

**Interfaces:**

- Produces : `fetch_roadmap_issues() -> dict[str, list[dict]]` avec les clés `"en_cours"` et `"au_vote"` ; chaque élément = `{"number": int, "title": str, "html_url": str}`. Caché 1 h.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/roadmap/test_github.py` :

```python
from src.roadmap import github


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


_ISSUES = [
    {
        "number": 10,
        "title": "Feature en cours",
        "html_url": "https://github.com/ColinMaudry/decp.info/issues/10",
        "labels": [{"name": "en cours"}],
    },
    {
        "number": 20,
        "title": "Feature au vote",
        "html_url": "https://github.com/ColinMaudry/decp.info/issues/20",
        "labels": [{"name": "mis au vote"}],
    },
    {
        "number": 30,
        "title": "Issue sans label pertinent",
        "html_url": "https://github.com/ColinMaudry/decp.info/issues/30",
        "labels": [{"name": "bug"}],
    },
    {
        "number": 40,
        "title": "Une PR déguisée en issue",
        "html_url": "https://github.com/ColinMaudry/decp.info/pull/40",
        "labels": [{"name": "mis au vote"}],
        "pull_request": {"url": "..."},
    },
]


def test_fetch_roadmap_issues_filters_by_label(monkeypatch):
    monkeypatch.setattr(github.httpx, "get", lambda *a, **k: _FakeResp(_ISSUES))
    result = github.fetch_roadmap_issues.uncached()
    assert [i["number"] for i in result["en_cours"]] == [10]
    assert [i["number"] for i in result["au_vote"]] == [20]  # PR #40 exclue
    assert result["en_cours"][0] == {
        "number": 10,
        "title": "Feature en cours",
        "html_url": "https://github.com/ColinMaudry/decp.info/issues/10",
    }
```

> `@cache.memoize` expose la fonction non-cachée via l'attribut `.uncached`, ce qui permet de tester la logique sans dépendre de l'état du cache.

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/roadmap/test_github.py -v`
Expected: FAIL (`ModuleNotFoundError: src.roadmap.github`)

- [ ] **Step 3: Implémenter `src/roadmap/github.py`**

```python
import httpx

from src.utils.cache import cache

GITHUB_REPO = "ColinMaudry/decp.info"
_LABEL_KEYS = {"en cours": "en_cours", "mis au vote": "au_vote"}


@cache.memoize(timeout=3600)
def fetch_roadmap_issues() -> dict[str, list[dict]]:
    """Issues ouvertes du dépôt portant un label de roadmap, regroupées par label.

    Appel anonyme à l'API GitHub publique. Mis en cache 1 h.
    """
    resp = httpx.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        params={"state": "open", "per_page": 100},
        headers={"Accept": "application/vnd.github+json"},
        timeout=10,
    )
    resp.raise_for_status()
    result: dict[str, list[dict]] = {"en_cours": [], "au_vote": []}
    for issue in resp.json():
        if "pull_request" in issue:
            continue  # l'endpoint /issues inclut les PR
        labels = {lbl["name"] for lbl in issue.get("labels", [])}
        for label, key in _LABEL_KEYS.items():
            if label in labels:
                result[key].append(
                    {
                        "number": issue["number"],
                        "title": issue["title"],
                        "html_url": issue["html_url"],
                    }
                )
    return result
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest tests/roadmap/test_github.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/roadmap/github.py tests/roadmap/test_github.py
git commit -m "feat: récupération cachée des issues roadmap GitHub #94"
```

---

## Task 6 : Composants d'affichage partagés (`src/roadmap/ui.py`)

**Files:**

- Create: `src/roadmap/ui.py`
- Test: `tests/roadmap/test_ui.py`

**Interfaces:**

- Consumes : `src.roadmap.github.fetch_roadmap_issues`, `src.roadmap.db.vote_counts`.
- Produces :

  - `balance_text(balance: int) -> str`
  - `vote_items(au_vote: list[dict], counts: dict[int, int], editable: bool) -> list` — items de `dbc.ListGroup` triés par votes décroissants.
  - `changelog_markdown() -> dcc.Markdown`
  - `roadmap_content(editable: bool, balance: int | None = None) -> html.Div` — section complète (en cours + au vote + changelog), avec bandeau de solde si `editable` et `balance` fourni.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/roadmap/test_ui.py` :

```python
from dash import dcc, html

from src.roadmap import ui


def test_balance_text_singular_plural():
    assert ui.balance_text(1) == "Il te reste 1 vote."
    assert ui.balance_text(3) == "Il te reste 3 votes."


def test_vote_items_sorted_by_count_desc():
    au_vote = [
        {"number": 1, "title": "A", "html_url": "u1"},
        {"number": 2, "title": "B", "html_url": "u2"},
    ]
    counts = {1: 1, 2: 5}
    items = ui.vote_items(au_vote, counts, editable=False)
    # le plus voté (numéro 2) vient en premier
    assert "B" in str(items[0])
    assert "A" in str(items[1])


def test_vote_items_buttons_only_when_editable():
    au_vote = [{"number": 1, "title": "A", "html_url": "u1"}]
    assert "Voter" in str(ui.vote_items(au_vote, {1: 0}, editable=True))
    assert "Voter" not in str(ui.vote_items(au_vote, {1: 0}, editable=False))


def test_changelog_markdown_returns_component():
    comp = ui.changelog_markdown()
    assert isinstance(comp, dcc.Markdown)
    assert "##" in comp.children  # le CHANGELOG.md contient des titres markdown


def test_roadmap_content_renders(monkeypatch):
    monkeypatch.setattr(
        ui.github,
        "fetch_roadmap_issues",
        lambda: {
            "en_cours": [{"number": 9, "title": "En cours X", "html_url": "u9"}],
            "au_vote": [{"number": 5, "title": "Au vote Y", "html_url": "u5"}],
        },
    )
    monkeypatch.setattr(ui.roadmap_db, "vote_counts", lambda: {5: 3})
    content = ui.roadmap_content(editable=True, balance=2)
    s = str(content)
    assert isinstance(content, html.Div)
    assert "En cours X" in s
    assert "Au vote Y" in s
    assert "Il te reste 2 votes." in s
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/roadmap/test_ui.py -v`
Expected: FAIL (`ModuleNotFoundError: src.roadmap.ui`)

- [ ] **Step 3: Implémenter `src/roadmap/ui.py`**

```python
from pathlib import Path

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.roadmap import db as roadmap_db
from src.roadmap import github

_CHANGELOG_PATH = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def balance_text(balance: int) -> str:
    mot = "vote" if balance == 1 else "votes"
    return f"Il te reste {balance} {mot}."


def changelog_markdown() -> dcc.Markdown:
    try:
        text = _CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError:
        text = "_Changelog indisponible._"
    return dcc.Markdown(text)


def _vote_item(issue: dict, count: int, editable: bool):
    mot = "vote" if count == 1 else "votes"
    children = [
        html.A(issue["title"], href=issue["html_url"], target="_blank"),
        html.Span(f" — {count} {mot}", className="text-muted ms-1"),
    ]
    if editable:
        children.append(
            dbc.Button(
                "Voter",
                id={"type": "roadmap-vote", "index": issue["number"]},
                size="sm",
                color="primary",
                className="ms-2",
            )
        )
    return dbc.ListGroupItem(children)


def vote_items(au_vote: list[dict], counts: dict[int, int], editable: bool) -> list:
    ordered = sorted(au_vote, key=lambda i: counts.get(i["number"], 0), reverse=True)
    if not ordered:
        return [dbc.ListGroupItem("Aucune fonctionnalité au vote pour le moment.")]
    return [_vote_item(i, counts.get(i["number"], 0), editable) for i in ordered]


def _en_cours_items(en_cours: list[dict]) -> list:
    if not en_cours:
        return [dbc.ListGroupItem("Rien en cours pour le moment.")]
    return [
        dbc.ListGroupItem(html.A(i["title"], href=i["html_url"], target="_blank"))
        for i in en_cours
    ]


def roadmap_content(editable: bool, balance: int | None = None) -> html.Div:
    try:
        issues = github.fetch_roadmap_issues()
    except Exception:
        issues = {"en_cours": [], "au_vote": []}
    counts = roadmap_db.vote_counts()

    body: list = []
    if editable and balance is not None:
        body.append(
            dbc.Alert(balance_text(balance), color="info", id="roadmap-balance")
        )
    body.append(html.H3("En cours", className="mt-3"))
    body.append(dbc.ListGroup(_en_cours_items(issues["en_cours"]), className="mb-4"))
    body.append(html.H3("Au vote"))
    body.append(
        dbc.ListGroup(
            vote_items(issues["au_vote"], counts, editable),
            id="roadmap-vote-list",
            className="mb-4",
        )
    )
    body.append(html.Hr())
    body.append(html.H3("Changelog"))
    body.append(changelog_markdown())
    return html.Div(body)
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/roadmap/test_ui.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/roadmap/ui.py tests/roadmap/test_ui.py
git commit -m "feat: composants d'affichage de la roadmap #94"
```

---

## Task 7 : Page abonné `/compte/roadmap` + navigation + vote

**Files:**

- Create: `src/pages/compte_roadmap.py`
- Modify: `src/pages/_compte_shell.py` (`SECTIONS`)
- Test: `tests/roadmap/test_compte_roadmap.py`

**Interfaces:**

- Consumes : `account_guard`, `account_shell` (`src.pages._compte_shell`) ; `credit_pending`, `spend_vote` (`src.subscriptions.db`) ; `record_vote`, `vote_counts` (`src.roadmap.db`) ; `fetch_roadmap_issues` (`src.roadmap.github`) ; `roadmap_content`, `vote_items`, `balance_text` (`src.roadmap.ui`).

- [ ] **Step 1: Ajouter l'entrée de navigation abonné**

Dans `src/pages/_compte_shell.py`, ajouter une entrée à la liste `SECTIONS` (après `"vues"`) :

```python
    {
        "key": "roadmap",
        "label": "Roadmap",
        "href": "/compte/roadmap",
        "require_subscription": True,
    },
```

- [ ] **Step 2: Écrire le test qui échoue**

Créer `tests/roadmap/test_compte_roadmap.py` (le Dash partagé vient de `conftest.py`) :

```python
def test_module_imports_and_registers():
    from src.pages import compte_roadmap

    assert callable(compte_roadmap.layout)
    assert callable(compte_roadmap.cast_vote)
```

> On ne teste pas `layout()` directement : il dépend de `current_user` et d'un
> contexte de requête Flask. La logique métier (accumulation, dépense, rendu) est
> déjà couverte par les Tasks 2, 3 et 6. La vérification de bout en bout est faite
> manuellement (section « Vérification finale »).

- [ ] **Step 3: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/roadmap/test_compte_roadmap.py -v`
Expected: FAIL (`ModuleNotFoundError: src.pages.compte_roadmap`)

- [ ] **Step 4: Implémenter `src/pages/compte_roadmap.py`**

```python
from dash import ALL, Input, Output, callback, ctx, no_update, register_page
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell
from src.roadmap import db as roadmap_db
from src.roadmap import github
from src.roadmap import ui as roadmap_ui
from src.subscriptions import db as subs_db

register_page(
    __name__,
    path="/compte/roadmap",
    title="Roadmap | decp.info",
    name="Roadmap",
    description="Votez pour les prochaines fonctionnalités de decp.info.",
)


def layout(**_):
    guard = account_guard("/compte/roadmap", require_subscription=True)
    if guard is not None:
        return guard
    balance = subs_db.credit_pending(current_user.id)
    return account_shell(
        "roadmap", roadmap_ui.roadmap_content(editable=True, balance=balance)
    )


@callback(
    Output("roadmap-vote-list", "children"),
    Output("roadmap-balance", "children"),
    Input({"type": "roadmap-vote", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def cast_vote(n_clicks):
    if not ctx.triggered_id or not any(n_clicks):
        return no_update, no_update
    issue_number = ctx.triggered_id["index"]
    if subs_db.spend_vote(current_user.id):
        roadmap_db.record_vote(current_user.id, issue_number)
    balance = subs_db.credit_pending(current_user.id)
    issues = github.fetch_roadmap_issues()
    counts = roadmap_db.vote_counts()
    items = roadmap_ui.vote_items(issues["au_vote"], counts, editable=True)
    return items, roadmap_ui.balance_text(balance)
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest tests/roadmap/test_compte_roadmap.py -v`
Expected: PASS

- [ ] **Step 6: Vérifier la non-régression du shell compte**

Run: `uv run pytest tests/test_compte_shell.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/pages/compte_roadmap.py src/pages/_compte_shell.py \
        tests/roadmap/test_compte_roadmap.py
git commit -m "feat: page abonné /compte/roadmap avec vote #94"
```

---

## Task 8 : Page publique `/a-propos/roadmap` + navigation

**Files:**

- Create: `src/pages/a_propos/roadmap.py`
- Modify: `src/pages/_apropos_shell.py` (`SECTIONS`)
- Test: `tests/roadmap/test_apropos_roadmap.py`

**Interfaces:**

- Consumes : `apropos_shell` (`src.pages._apropos_shell`) ; `roadmap_content` (`src.roadmap.ui`).

- [ ] **Step 1: Ajouter l'entrée de navigation publique**

Dans `src/pages/_apropos_shell.py`, ajouter à `SECTIONS` (après `"abonnement"`) :

```python
    {
        "key": "roadmap",
        "label": "Roadmap",
        "href": "/a-propos/roadmap",
    },
```

- [ ] **Step 2: Écrire le test qui échoue**

Créer `tests/roadmap/test_apropos_roadmap.py` (le Dash partagé vient de `conftest.py`) :

```python
def test_public_layout_renders_read_only(monkeypatch):
    from src.roadmap import ui as roadmap_ui

    monkeypatch.setattr(
        roadmap_ui.github,
        "fetch_roadmap_issues",
        lambda: {"en_cours": [], "au_vote": [
            {"number": 1, "title": "Feature publique", "html_url": "u1"}
        ]},
    )
    monkeypatch.setattr(roadmap_ui.roadmap_db, "vote_counts", lambda: {1: 4})

    from src.pages.a_propos import roadmap

    layout = roadmap.layout()
    s = str(layout)
    assert "Feature publique" in s
    assert "Voter" not in s  # lecture seule : aucun bouton
```

- [ ] **Step 3: Lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/roadmap/test_apropos_roadmap.py -v`
Expected: FAIL (`ModuleNotFoundError: src.pages.a_propos.roadmap`)

- [ ] **Step 4: Implémenter `src/pages/a_propos/roadmap.py`**

```python
from dash import register_page

from src.pages._apropos_shell import apropos_shell
from src.roadmap import ui as roadmap_ui
from src.utils.seo import META_CONTENT

register_page(
    __name__,
    path="/a-propos/roadmap",
    title="Roadmap | À propos | decp.info",
    description="Les prochaines fonctionnalités de decp.info, soumises au vote des abonnés.",
    image_url=META_CONTENT["image_url"],
)


def layout(**_):
    return apropos_shell("roadmap", roadmap_ui.roadmap_content(editable=False))
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `uv run pytest tests/roadmap/test_apropos_roadmap.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/pages/a_propos/roadmap.py src/pages/_apropos_shell.py \
        tests/roadmap/test_apropos_roadmap.py
git commit -m "feat: page publique /a-propos/roadmap (lecture seule) #94"
```

---

## Task 9 : Lien du numéro de version → `/a-propos/roadmap`

**Files:**

- Modify: `src/app.py` (~ligne 195)

**Interfaces:** aucune (changement de présentation).

- [ ] **Step 1: Modifier le lien**

Dans `src/app.py`, remplacer le `href` GitHub du numéro de version :

```python
                                    html.A(
                                        version,
                                        href="/a-propos/roadmap",
                                    )
```

- [ ] **Step 2: Vérifier que l'app démarre et que le lien est correct**

Run: `uv run python -c "import src.app"`
Expected: import sans erreur.

Run: `git grep -n 'href="/a-propos/roadmap"' src/app.py`
Expected: une ligne correspondante.

- [ ] **Step 3: Commit**

```bash
git add src/app.py
git commit -m "feat: le lien de version pointe vers /a-propos/roadmap #94"
```

---

## Vérification finale

- [ ] **Suite complète des tests roadmap + subscriptions**

Run: `uv run pytest tests/roadmap tests/subscriptions tests/test_compte_shell.py -v`
Expected: PASS

- [ ] **Vérification manuelle (optionnelle, nécessite réseau + abonnement)**

Lancer `uv run python run.py`, se connecter avec un compte abonné, visiter `/compte/roadmap` : vérifier le bandeau de solde, les sections « En cours » / « Au vote », le bouton « Voter » (qui décrémente le solde et incrémente le décompte), et le changelog. Visiter `/a-propos/roadmap` en navigation privée : mêmes listes, décomptes visibles, aucun bouton. Cliquer le numéro de version près du logo → arrive sur `/a-propos/roadmap`.
