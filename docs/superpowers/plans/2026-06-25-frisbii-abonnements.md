# Abonnements Frisbii — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un utilisateur connecté de souscrire et résilier un abonnement payant decp.info via Frisbii (ex-Reepay), avec essai gratuit configuré côté Frisbii.

**Architecture:** Nouveau module isolé `src/subscriptions/` (client HTTP pur, état SQLite, catalogue de plans, fonctions pures de webhook, blueprint Flask, setup). Paiement par session de checkout hébergée Frisbii ; les webhooks sont la source de vérité. Le webhook **vérifie la signature puis relit l'état courant de l'abonnement via l'API** (`get_subscription`) et le mappe vers nos statuts — plus robuste que de dépendre des champs exacts de chaque événement (dont les noms sont à confirmer dans la doc Frisbii). Spec : `docs/superpowers/specs/2026-06-25-frisbii-abonnements-design.md`.

**Tech Stack:** Python 3, Flask + flask-login + flask-wtf (CSRF), Dash (page), `httpx` (client HTTP, déjà dépendance), SQLite (`users.sqlite`, via `src.auth.db.get_conn`), pytest.

## Global Constraints

- Tous les imports internes commencent par `src.` (ex. `from src.subscriptions import db`), jamais `subscriptions.db`.
- UI et messages en **français**.
- Client HTTP : **`httpx`** (pas `requests`).
- Logging : `from src.utils import logger`.
- Tests exécutés avec **`uv run pytest`**.
- Clé privée Frisbii **jamais exposée au frontend** ; utilisée uniquement en HTTP Basic Auth côté serveur (clé en username, mot de passe vide).
- Deux plans : `simple` (20 € HT/mois) et `soutien` (50 € HT/mois), **même accès premium**.
- Statuts d'abonnement : `pending`, `trial`, `active`, `cancelled`, `expired`. Accès premium si `trial`/`active`, ou `cancelled` avec `current_period_end` futur.
- Hooks pre-commit actifs (ruff, prettier) : ne pas s'étonner d'un reformatage automatique au commit ; re-`git add` puis re-commit si un hook modifie un fichier.

---

### Task 1: Client HTTP Frisbii (`client.py`)

**Files:**

- Create: `src/subscriptions/__init__.py` (vide)
- Create: `src/subscriptions/client.py`
- Create: `tests/subscriptions/__init__.py` (vide)
- Create: `tests/subscriptions/conftest.py`
- Test: `tests/subscriptions/test_client.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  - `class FrisbiiError(Exception)` avec attribut `.status_code: int` et `.body`.
  - `get_or_create_customer(handle: str, email: str) -> dict`
  - `create_subscription_session(plan_handle: str, customer_handle: str, accept_url: str, cancel_url: str, no_trial: bool = False) -> str` (renvoie l'URL hébergée ; `no_trial=True` désactive l'essai du plan pour cette souscription)
  - `cancel_subscription(subscription_handle: str) -> dict`
  - `get_subscription(subscription_handle: str) -> dict`
  - `get_plan(plan_handle: str) -> dict`

- [ ] **Step 1: Créer le fake httpx partagé pour les tests**

Create `tests/subscriptions/__init__.py` (vide) puis `tests/subscriptions/conftest.py` :

```python
import json as _json

import pytest


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    @property
    def text(self):
        return _json.dumps(self._payload)


@pytest.fixture
def fake_httpx(monkeypatch):
    """Capture les appels httpx.request du client Frisbii et renvoie des réponses programmées."""
    from src.subscriptions import client

    calls = []
    queue = []

    def _fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        if queue:
            return queue.pop(0)
        return FakeResponse(200, {})

    monkeypatch.setenv("FRISBII_API_KEY", "priv_test")
    monkeypatch.setenv("FRISBII_API_BASE_URL", "https://api.test")
    monkeypatch.setattr(client.httpx, "request", _fake_request)
    return {"calls": calls, "queue": queue, "Response": FakeResponse}
```

- [ ] **Step 2: Écrire les tests du client**

Create `tests/subscriptions/test_client.py` :

```python
import pytest

from src.subscriptions import client


def test_auth_and_base_url_used(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "decpinfo-1"}))
    client.get_or_create_customer("decpinfo-1", "a@b.fr")
    call = fake_httpx["calls"][0]
    assert call["url"] == "https://api.test/v1/customer/decpinfo-1"
    assert call["auth"] == ("priv_test", "")


def test_get_or_create_customer_existing(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "decpinfo-1"}))
    result = client.get_or_create_customer("decpinfo-1", "a@b.fr")
    assert result == {"handle": "decpinfo-1"}
    assert len(fake_httpx["calls"]) == 1  # pas de POST de création


def test_get_or_create_customer_creates_on_404(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](404, {"error": "not found"}))
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "decpinfo-1"}))
    result = client.get_or_create_customer("decpinfo-1", "a@b.fr")
    assert result == {"handle": "decpinfo-1"}
    assert fake_httpx["calls"][1]["method"] == "POST"
    assert fake_httpx["calls"][1]["json"] == {"handle": "decpinfo-1", "email": "a@b.fr"}


def test_create_subscription_session_returns_url(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](200, {"id": "cs_1", "url": "https://pay.test/cs_1"})
    )
    url = client.create_subscription_session(
        "plan_simple", "decpinfo-1", "https://app/ok", "https://app/ko"
    )
    assert url == "https://pay.test/cs_1"
    body = fake_httpx["calls"][0]["json"]
    assert body["prepare_subscription"] == {"plan": "plan_simple", "customer": "decpinfo-1"}
    assert body["accept_url"] == "https://app/ok"
    assert body["cancel_url"] == "https://app/ko"


def test_create_subscription_session_no_trial(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"url": "https://pay.test/cs_2"}))
    client.create_subscription_session(
        "plan_simple", "decpinfo-1", "https://app/ok", "https://app/ko", no_trial=True
    )
    assert fake_httpx["calls"][0]["json"]["prepare_subscription"]["no_trial"] is True


def test_http_error_raises_frisbii_error(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](500, {"error": "boom"}))
    with pytest.raises(client.FrisbiiError) as exc:
        client.get_plan("plan_simple")
    assert exc.value.status_code == 500
```

- [ ] **Step 3: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/subscriptions/test_client.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.subscriptions'` / attributs manquants).

- [ ] **Step 4: Implémenter le client**

Create `src/subscriptions/__init__.py` vide. Create `src/subscriptions/client.py` :

```python
import os

import httpx

# NB : base URL et schémas d'endpoints à confirmer dans la doc Frisbii lors de la
# première intégration en environnement de test. Frisbii Billing/Pay s'appuie sur
# l'API Reepay (api.reepay.com) ; ajuster FRISBII_API_BASE_URL si besoin.
_DEFAULT_BASE_URL = "https://api.reepay.com"
_TIMEOUT = 15.0


class FrisbiiError(Exception):
    def __init__(self, status_code: int, body):
        super().__init__(f"Frisbii API error {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def _api_key() -> str:
    return os.getenv("FRISBII_API_KEY", "")


def _base_url() -> str:
    return os.getenv("FRISBII_API_BASE_URL") or _DEFAULT_BASE_URL


def _call(method: str, path: str, json: dict | None = None) -> dict:
    resp = httpx.request(
        method,
        f"{_base_url()}{path}",
        auth=(_api_key(), ""),
        json=json,
        timeout=_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise FrisbiiError(resp.status_code, resp.text)
    return resp.json()


def get_or_create_customer(handle: str, email: str) -> dict:
    try:
        return _call("GET", f"/v1/customer/{handle}")
    except FrisbiiError as exc:
        if exc.status_code != 404:
            raise
        return _call("POST", "/v1/customer", json={"handle": handle, "email": email})


def create_subscription_session(
    plan_handle: str,
    customer_handle: str,
    accept_url: str,
    cancel_url: str,
    no_trial: bool = False,
) -> str:
    prepare = {"plan": plan_handle, "customer": customer_handle}
    if no_trial:
        prepare["no_trial"] = True
    data = _call(
        "POST",
        "/v1/session/subscription",
        json={
            "accept_url": accept_url,
            "cancel_url": cancel_url,
            "prepare_subscription": prepare,
        },
    )
    return data["url"]


def cancel_subscription(subscription_handle: str) -> dict:
    return _call("POST", f"/v1/subscription/{subscription_handle}/cancel")


def get_subscription(subscription_handle: str) -> dict:
    return _call("GET", f"/v1/subscription/{subscription_handle}")


def get_plan(plan_handle: str) -> dict:
    return _call("GET", f"/v1/plan/{plan_handle}")
```

- [ ] **Step 5: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/subscriptions/test_client.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add src/subscriptions/__init__.py src/subscriptions/client.py tests/subscriptions/
git commit -m "feat(abonnement): client HTTP Frisbii (#90)"
```

---

### Task 2: État d'abonnement SQLite (`db.py`)

**Files:**

- Create: `src/subscriptions/db.py`
- Test: `tests/subscriptions/test_db.py`

**Interfaces:**

- Consumes: `src.auth.db.get_conn`, `src.auth.db.reset_conn_for_tests` (réutilise la connexion `users.sqlite`).
- Produces:

  - `init_schema() -> None`
  - `create_pending(user_id: int, customer_handle: str, plan: str) -> None`
  - `get_by_user(user_id: int) -> sqlite3.Row | None`
  - `get_by_customer(customer_handle: str) -> sqlite3.Row | None`
  - `update_from_webhook(customer_handle: str, subscription_handle: str | None, status: str, current_period_end: str | None) -> None`
  - `set_cancelled(user_id: int, current_period_end: str | None) -> None`
  - `has_active_subscription(user_id: int) -> bool`
  - `has_used_trial(user_id: int) -> bool` (anti-abus : essai déjà consommé ?)

- [ ] **Step 1: Écrire les tests du module DB**

Create `tests/subscriptions/test_db.py` :

```python
from datetime import datetime, timedelta, timezone

from src.auth import db as auth_db
from src.subscriptions import db


def _future():
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def _past():
    return (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()


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
    assert "subscriptions" in tables


def test_create_pending_and_get_by_user(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    row = db.get_by_user(uid)
    assert row["status"] == "pending"
    assert row["plan"] == "simple"
    assert row["frisbii_customer_handle"] == "decpinfo-1"


def test_update_from_webhook_sets_status_and_handle(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    db.update_from_webhook("decpinfo-1", "sub_42", "trial", _future())
    row = db.get_by_user(uid)
    assert row["status"] == "trial"
    assert row["frisbii_subscription_handle"] == "sub_42"
    assert db.get_by_customer("decpinfo-1")["user_id"] == uid


def test_has_active_subscription_by_status(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    # pending → faux
    assert db.has_active_subscription(uid) is False
    for status in ("trial", "active"):
        db.update_from_webhook("decpinfo-1", "sub_42", status, _future())
        assert db.has_active_subscription(uid) is True
    # cancelled futur → vrai, cancelled passé → faux
    db.update_from_webhook("decpinfo-1", "sub_42", "cancelled", _future())
    assert db.has_active_subscription(uid) is True
    db.update_from_webhook("decpinfo-1", "sub_42", "cancelled", _past())
    assert db.has_active_subscription(uid) is False
    db.update_from_webhook("decpinfo-1", "sub_42", "expired", None)
    assert db.has_active_subscription(uid) is False


def test_set_cancelled(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    db.update_from_webhook("decpinfo-1", "sub_42", "active", _future())
    end = _future()
    db.set_cancelled(uid, end)
    row = db.get_by_user(uid)
    assert row["status"] == "cancelled"
    assert row["current_period_end"] == end


def test_trial_used_is_sticky_across_resubscribe(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.create_pending(uid, "decpinfo-1", "simple")
    assert db.has_used_trial(uid) is False
    # l'abonnement entre en essai → trial_used positionné
    db.update_from_webhook("decpinfo-1", "sub_42", "trial", _future())
    assert db.has_used_trial(uid) is True
    # essai abandonné, puis nouvelle souscription : trial_used reste vrai
    db.update_from_webhook("decpinfo-1", "sub_42", "expired", _past())
    db.create_pending(uid, "decpinfo-1", "soutien")
    assert db.has_used_trial(uid) is True
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/subscriptions/test_db.py -v`
Expected: FAIL (module/fonctions absents).

- [ ] **Step 3: Implémenter `db.py`**

Create `src/subscriptions/db.py` :

```python
import sqlite3
from datetime import datetime, timezone

from src.auth.db import get_conn

SUBSCRIPTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id                     INTEGER PRIMARY KEY,
    frisbii_customer_handle     TEXT,
    frisbii_subscription_handle TEXT,
    plan                        TEXT,
    status                      TEXT,
    current_period_end          TEXT,
    trial_used                  INTEGER NOT NULL DEFAULT 0,
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer
    ON subscriptions(frisbii_customer_handle);
"""

_ACCESS_STATUSES = ("trial", "active")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema() -> None:
    get_conn().executescript(SUBSCRIPTIONS_SCHEMA)


def create_pending(user_id: int, customer_handle: str, plan: str) -> None:
    now = _now()
    get_conn().execute(
        "INSERT INTO subscriptions "
        "(user_id, frisbii_customer_handle, plan, status, created_at, updated_at) "
        "VALUES (?, ?, ?, 'pending', ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "frisbii_customer_handle=excluded.frisbii_customer_handle, "
        "plan=excluded.plan, status='pending', updated_at=excluded.updated_at",
        (user_id, customer_handle, plan, now, now),
    )


def get_by_user(user_id: int) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))
        .fetchone()
    )


def get_by_customer(customer_handle: str) -> sqlite3.Row | None:
    return (
        get_conn()
        .execute(
            "SELECT * FROM subscriptions WHERE frisbii_customer_handle = ?",
            (customer_handle,),
        )
        .fetchone()
    )


def update_from_webhook(
    customer_handle: str,
    subscription_handle: str | None,
    status: str,
    current_period_end: str | None,
) -> None:
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


def set_cancelled(user_id: int, current_period_end: str | None) -> None:
    get_conn().execute(
        "UPDATE subscriptions SET status = 'cancelled', current_period_end = ?, "
        "updated_at = ? WHERE user_id = ?",
        (current_period_end, _now(), user_id),
    )


def has_active_subscription(user_id: int) -> bool:
    row = get_by_user(user_id)
    if row is None:
        return False
    if row["status"] in _ACCESS_STATUSES:
        return True
    if row["status"] == "cancelled" and row["current_period_end"]:
        return row["current_period_end"] > _now()
    return False


def has_used_trial(user_id: int) -> bool:
    row = get_by_user(user_id)
    return bool(row and row["trial_used"])
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/subscriptions/test_db.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/db.py tests/subscriptions/test_db.py
git commit -m "feat(abonnement): table subscriptions + état (#90)"
```

---

### Task 3: Catalogue de plans + durée d'essai (`plans.py`)

**Files:**

- Create: `src/subscriptions/plans.py`
- Test: `tests/subscriptions/test_plans.py`

**Interfaces:**

- Consumes: `src.subscriptions.client.get_plan`, `src.subscriptions.client.FrisbiiError`.
- Produces:

  - `PLANS: dict` (clé → `{"handle", "label", "prix_ht", "description"}`)
  - `resolve_handle(key: str) -> str | None`
  - `plan_meta(key: str) -> dict | None`
  - `trial_days(key: str) -> int | None` (lit `trial_interval` du plan Frisbii, mis en cache ~1 h)

- [ ] **Step 1: Écrire les tests**

Create `tests/subscriptions/test_plans.py` :

```python
import pytest

from src.subscriptions import client, plans


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    plans._trial_cache.clear()


def test_resolve_handle(monkeypatch):
    assert plans.resolve_handle("simple") == "plan_simple"
    assert plans.resolve_handle("inconnu") is None


def test_trial_days_parses_and_caches(monkeypatch):
    calls = []

    def fake_get_plan(handle):
        calls.append(handle)
        return {"trial_interval": "2d"}

    monkeypatch.setattr(client, "get_plan", fake_get_plan)
    assert plans.trial_days("simple") == 2
    assert plans.trial_days("simple") == 2  # depuis le cache
    assert calls == ["plan_simple"]  # un seul appel API


def test_trial_days_none_on_error(monkeypatch):
    def fake_get_plan(handle):
        raise client.FrisbiiError(500, "boom")

    monkeypatch.setattr(client, "get_plan", fake_get_plan)
    assert plans.trial_days("simple") is None


def test_trial_days_none_when_no_trial(monkeypatch):
    monkeypatch.setattr(client, "get_plan", lambda h: {"trial_interval": None})
    assert plans.trial_days("simple") is None
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/subscriptions/test_plans.py -v`
Expected: FAIL (module/attributs absents).

- [ ] **Step 3: Implémenter `plans.py`**

Create `src/subscriptions/plans.py` :

```python
import os
import time

from src.subscriptions import client
from src.utils import logger

_TTL_SECONDS = 3600
_trial_cache: dict[str, tuple[float, int | None]] = {}


def _handle(env_name: str) -> str:
    return os.getenv(env_name, "")


PLANS = {
    "simple": {
        "env": "FRISBII_PLAN_SIMPLE",
        "label": "Abonnement simple",
        "prix_ht": 20,
        "description": "Accès aux fonctionnalités premium de decp.info.",
    },
    "soutien": {
        "env": "FRISBII_PLAN_SOUTIEN",
        "label": "Abonnement de soutien",
        "prix_ht": 50,
        "description": "Mêmes fonctionnalités, contribution renforcée au projet.",
    },
}


def resolve_handle(key: str) -> str | None:
    meta = PLANS.get(key)
    return _handle(meta["env"]) if meta else None


def plan_meta(key: str) -> dict | None:
    meta = PLANS.get(key)
    if meta is None:
        return None
    return {
        "key": key,
        "handle": _handle(meta["env"]),
        "label": meta["label"],
        "prix_ht": meta["prix_ht"],
        "description": meta["description"],
    }


def _parse_trial_interval(value) -> int | None:
    # Reepay/Frisbii renvoie une durée type "2d" (jours), "1m" (mois), etc.
    # On ne sait afficher que les jours pour l'instant ; format à confirmer.
    if not value or not isinstance(value, str):
        return None
    value = value.strip().lower()
    if value.endswith("d") and value[:-1].isdigit():
        return int(value[:-1])
    return None


def trial_days(key: str) -> int | None:
    handle = resolve_handle(key)
    if not handle:
        return None
    now = time.monotonic()
    cached = _trial_cache.get(handle)
    if cached and now - cached[0] < _TTL_SECONDS:
        return cached[1]
    try:
        plan = client.get_plan(handle)
    except client.FrisbiiError:
        logger.warning("Impossible de lire le plan Frisbii %s", handle)
        return cached[1] if cached else None
    days = _parse_trial_interval(plan.get("trial_interval"))
    _trial_cache[handle] = (now, days)
    return days
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/subscriptions/test_plans.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/plans.py tests/subscriptions/test_plans.py
git commit -m "feat(abonnement): catalogue de plans + durée d'essai dynamique (#90)"
```

---

### Task 4: Signature et mapping webhook (`webhooks.py`)

**Files:**

- Create: `src/subscriptions/webhooks.py`
- Test: `tests/subscriptions/test_webhooks.py`

**Interfaces:**

- Consumes: rien (fonctions pures).
- Produces:

  - `verify_signature(payload: dict, secret: str) -> bool`
  - `map_subscription(sub: dict) -> tuple[str, str | None]` (renvoie `(status, current_period_end)`)

- [ ] **Step 1: Écrire les tests**

Create `tests/subscriptions/test_webhooks.py` :

```python
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from src.subscriptions import webhooks


def _sign(secret, timestamp, event_id):
    return hmac.new(
        secret.encode(), (timestamp + event_id).encode(), hashlib.sha256
    ).hexdigest()


def test_verify_signature_accepts_valid():
    payload = {"id": "evt_1", "timestamp": "2026-06-25T10:00:00Z"}
    payload["signature"] = _sign("s3cr3t", payload["timestamp"], payload["id"])
    assert webhooks.verify_signature(payload, "s3cr3t") is True


def test_verify_signature_rejects_tampered():
    payload = {
        "id": "evt_1",
        "timestamp": "2026-06-25T10:00:00Z",
        "signature": "deadbeef",
    }
    assert webhooks.verify_signature(payload, "s3cr3t") is False


def test_verify_signature_rejects_without_secret():
    payload = {"id": "evt_1", "timestamp": "t", "signature": "x"}
    assert webhooks.verify_signature(payload, "") is False


def _future():
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def test_map_trial():
    status, end = webhooks.map_subscription(
        {"state": "active", "trial_end": _future(), "next_period_start": _future()}
    )
    assert status == "trial"


def test_map_active():
    nxt = _future()
    status, end = webhooks.map_subscription({"state": "active", "next_period_start": nxt})
    assert status == "active"
    assert end == nxt


def test_map_cancelled():
    exp = _future()
    status, end = webhooks.map_subscription(
        {"state": "active", "is_cancelled": True, "expires": exp}
    )
    assert status == "cancelled"
    assert end == exp


def test_map_expired():
    status, end = webhooks.map_subscription({"state": "expired", "expires": "2020-01-01T00:00:00Z"})
    assert status == "expired"
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/subscriptions/test_webhooks.py -v`
Expected: FAIL (module absent).

- [ ] **Step 3: Implémenter `webhooks.py`**

Create `src/subscriptions/webhooks.py` :

```python
import hashlib
import hmac
from datetime import datetime, timezone


def verify_signature(payload: dict, secret: str) -> bool:
    # Schéma Reepay/Frisbii : HMAC-SHA256(secret, timestamp + id), hex.
    # À confirmer dans la doc webhooks Frisbii lors de l'intégration.
    if not secret:
        return False
    timestamp = payload.get("timestamp", "")
    event_id = payload.get("id", "")
    received = payload.get("signature", "")
    expected = hmac.new(
        secret.encode(), (timestamp + event_id).encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)


def _in_future(value) -> bool:
    if not value:
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) > datetime.now(
            timezone.utc
        )
    except ValueError:
        return False


def map_subscription(sub: dict) -> tuple[str, str | None]:
    """Mappe un objet subscription Frisbii vers (status, current_period_end).

    Noms de champs Reepay (à confirmer) : state, trial_end, expires,
    is_cancelled, next_period_start.
    """
    state = sub.get("state")
    if state == "expired":
        return "expired", sub.get("expires")
    if sub.get("is_cancelled") or state == "cancelled":
        return "cancelled", sub.get("expires")
    if _in_future(sub.get("trial_end")):
        return "trial", sub.get("trial_end")
    if state == "active":
        return "active", sub.get("next_period_start")
    if state == "pending":
        return "pending", None
    return (state or "pending"), sub.get("next_period_start")
```

- [ ] **Step 4: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/subscriptions/test_webhooks.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/subscriptions/webhooks.py tests/subscriptions/test_webhooks.py
git commit -m "feat(abonnement): signature + mapping des webhooks Frisbii (#90)"
```

---

### Task 5: Routes Flask + setup + câblage app (`routes.py`, `setup.py`, `app.py`, `.template.env`)

**Files:**

- Create: `src/subscriptions/routes.py`
- Create: `src/subscriptions/setup.py`
- Modify: `src/app.py` (appeler `init_subscriptions` après `init_api`)
- Modify: `.template.env` (variables Frisbii)
- Test: `tests/subscriptions/test_routes.py`

**Interfaces:**

- Consumes: `client`, `db`, `plans`, `webhooks` (tasks 1-4) ; `src.auth.setup.init_auth`, `src.auth.db`, `flask_login`.
- Produces:

  - `subscriptions_bp` (Blueprint)
  - `init_subscriptions(app) -> None`

- [ ] **Step 1: Ajouter au conftest une app abonnements + un client connecté**

Append to `tests/subscriptions/conftest.py` :

```python
@pytest.fixture
def sub_app(users_db_path, monkeypatch):
    from flask import Flask

    from src.auth.setup import init_auth
    from src.subscriptions.setup import init_subscriptions

    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    monkeypatch.setenv("FRISBII_WEBHOOK_SECRET", "s3cr3t")
    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    init_auth(app)
    init_subscriptions(app)
    return app


@pytest.fixture
def logged_in_client(sub_app):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("sub@ex.fr", "hash")
    auth_db.set_email_verified(uid)
    client = sub_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True
    return client, uid
```

- [ ] **Step 2: Écrire les tests des routes**

Create `tests/subscriptions/test_routes.py` :

```python
import hashlib
import hmac

from src.subscriptions import client as frisbii_client
from src.subscriptions import db


def _sign(secret, timestamp, event_id):
    return hmac.new(
        secret.encode(), (timestamp + event_id).encode(), hashlib.sha256
    ).hexdigest()


def test_subscribe_redirects_to_hosted_url(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    monkeypatch.setattr(
        frisbii_client, "get_or_create_customer", lambda h, e: {"handle": h}
    )
    monkeypatch.setattr(
        frisbii_client,
        "create_subscription_session",
        lambda plan, cust, ok, ko, no_trial=False: "https://pay.test/cs_1",
    )
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 303
    assert resp.headers["Location"] == "https://pay.test/cs_1"
    assert db.get_by_user(uid)["status"] == "pending"


def test_subscribe_disables_trial_after_first_use(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    # L'utilisateur a déjà consommé un essai par le passé.
    db.create_pending(uid, "decpinfo-%d" % uid, "simple")
    db.update_from_webhook("decpinfo-%d" % uid, "sub_42", "trial", "2099-01-01T00:00:00+00:00")
    captured = {}
    monkeypatch.setattr(
        frisbii_client, "get_or_create_customer", lambda h, e: {"handle": h}
    )

    def fake_session(plan, cust, ok, ko, no_trial=False):
        captured["no_trial"] = no_trial
        return "https://pay.test/cs_9"

    monkeypatch.setattr(frisbii_client, "create_subscription_session", fake_session)
    resp = client.post("/subscriptions/subscribe", data={"plan": "soutien"})
    assert resp.status_code == 303
    assert captured["no_trial"] is True


def test_subscribe_unknown_plan(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/subscriptions/subscribe", data={"plan": "bidon"})
    assert resp.status_code == 400


def test_subscribe_api_error_redirects_with_error(logged_in_client, monkeypatch):
    client, _ = logged_in_client

    def boom(h, e):
        raise frisbii_client.FrisbiiError(500, "boom")

    monkeypatch.setattr(frisbii_client, "get_or_create_customer", boom)
    resp = client.post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code == 302
    assert "error=frisbii" in resp.headers["Location"]


def test_subscribe_requires_login(sub_app):
    resp = sub_app.test_client().post("/subscriptions/subscribe", data={"plan": "simple"})
    assert resp.status_code in (302, 401)


def test_cancel_calls_api_and_marks_cancelled(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    db.create_pending(uid, "decpinfo-%d" % uid, "simple")
    db.update_from_webhook("decpinfo-%d" % uid, "sub_42", "active", "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(
        frisbii_client,
        "cancel_subscription",
        lambda handle: {"expires": "2099-02-01T00:00:00+00:00"},
    )
    resp = client.post("/subscriptions/cancel")
    assert resp.status_code == 302
    assert "resiliation=ok" in resp.headers["Location"]
    row = db.get_by_user(uid)
    assert row["status"] == "cancelled"
    assert row["current_period_end"] == "2099-02-01T00:00:00+00:00"


def test_webhook_invalid_signature(sub_app):
    resp = sub_app.test_client().post("/frisbii/webhook", json={"id": "e", "signature": "x"})
    assert resp.status_code == 403


def test_webhook_updates_subscription(sub_app, monkeypatch):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("wh@ex.fr", "hash")
    db.create_pending(uid, "decpinfo-%d" % uid, "simple")
    monkeypatch.setattr(
        frisbii_client,
        "get_subscription",
        lambda h: {"state": "active", "next_period_start": "2099-01-01T00:00:00+00:00"},
    )
    payload = {
        "id": "evt_1",
        "timestamp": "2026-06-25T10:00:00Z",
        "event_type": "subscription_created",
        "customer": "decpinfo-%d" % uid,
        "subscription": "sub_42",
    }
    payload["signature"] = _sign("s3cr3t", payload["timestamp"], payload["id"])
    resp = sub_app.test_client().post("/frisbii/webhook", json=payload)
    assert resp.status_code == 200
    row = db.get_by_user(uid)
    assert row["status"] == "active"
    assert row["frisbii_subscription_handle"] == "sub_42"
```

- [ ] **Step 3: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/subscriptions/test_routes.py -v`
Expected: FAIL (blueprint / setup absents).

- [ ] **Step 4: Implémenter `routes.py`**

Create `src/subscriptions/routes.py` :

```python
import os

from flask import Blueprint, redirect, request
from flask_login import current_user, login_required

from src.subscriptions import client, db, plans, webhooks
from src.utils import logger

subscriptions_bp = Blueprint("subscriptions", __name__)


def _customer_handle(user_id: int) -> str:
    return f"decpinfo-{user_id}"


@subscriptions_bp.route("/subscriptions/subscribe", methods=["POST"])
@login_required
def subscribe():
    plan_key = request.form.get("plan") or ""
    handle = plans.resolve_handle(plan_key)
    if handle is None:
        return "Plan inconnu", 400

    base = os.getenv("APP_BASE_URL", "")
    cust = _customer_handle(current_user.id)
    try:
        client.get_or_create_customer(cust, current_user.email)
        db.create_pending(current_user.id, cust, plan_key)
        # Anti-abus : pas de nouvel essai si l'utilisateur en a déjà consommé un.
        no_trial = db.has_used_trial(current_user.id)
        url = client.create_subscription_session(
            handle,
            cust,
            f"{base}/compte/abonnement?paiement=succes",
            f"{base}/compte/abonnement?paiement=annule",
            no_trial=no_trial,
        )
    except client.FrisbiiError:
        logger.exception("Échec de création de session d'abonnement Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    return redirect(url, code=303)


@subscriptions_bp.route("/subscriptions/cancel", methods=["POST"])
@login_required
def cancel():
    row = db.get_by_user(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement à résilier", 400
    try:
        sub = client.cancel_subscription(row["frisbii_subscription_handle"])
    except client.FrisbiiError:
        logger.exception("Échec de résiliation Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    db.set_cancelled(current_user.id, sub.get("expires"))
    return redirect("/compte/abonnement?resiliation=ok")


@subscriptions_bp.route("/frisbii/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    if not webhooks.verify_signature(payload, os.getenv("FRISBII_WEBHOOK_SECRET", "")):
        return "", 403

    customer = payload.get("customer")
    sub_handle = payload.get("subscription")
    if not customer or db.get_by_customer(customer) is None:
        return "", 200  # rien à rapprocher
    try:
        sub = client.get_subscription(sub_handle) if sub_handle else None
    except client.FrisbiiError:
        logger.exception("Webhook : lecture de l'abonnement Frisbii impossible")
        return "", 502  # Frisbii réessaiera
    if sub is None:
        return "", 200
    status, current_period_end = webhooks.map_subscription(sub)
    db.update_from_webhook(customer, sub_handle, status, current_period_end)
    return "", 200
```

- [ ] **Step 5: Implémenter `setup.py`**

L'exemption CSRF doit cibler **la seule vue webhook** (pas tout le blueprint, sinon
`subscribe`/`cancel` perdraient la protection CSRF). Create `src/subscriptions/setup.py` :

```python
import os

from flask import Flask

from src.subscriptions import db
from src.utils import logger

_REQUIRED_ENV = (
    "FRISBII_API_KEY",
    "FRISBII_WEBHOOK_SECRET",
    "FRISBII_PLAN_SIMPLE",
    "FRISBII_PLAN_SOUTIEN",
)


def init_subscriptions(app: Flask) -> None:
    db.init_schema()

    from src.subscriptions.routes import subscriptions_bp, webhook

    app.register_blueprint(subscriptions_bp)

    # Le webhook reçoit des POST externes : pas de jeton CSRF possible.
    from src.auth.setup import _csrf as _auth_csrf

    if _auth_csrf is not None:
        _auth_csrf.exempt(webhook)  # exempte la seule vue webhook

    missing = [name for name in _REQUIRED_ENV if not os.getenv(name)]
    if missing:
        logger.warning(
            "Variables Frisbii manquantes (%s) : les abonnements échoueront. "
            "Définissez-les dans .env (voir .template.env).",
            ", ".join(missing),
        )
```

- [ ] **Step 6: Câbler dans `src/app.py`**

Dans `src/app.py`, juste après le bloc `init_api(app.server)` (vers la ligne 91), ajouter :

```python
from src.subscriptions.setup import init_subscriptions  # noqa: E402

init_subscriptions(app.server)
```

- [ ] **Step 7: Documenter les variables dans `.template.env`**

Ajouter à la fin de `.template.env` :

```bash
# Frisbii — gestion des abonnements (https://docs.frisbii.com)
FRISBII_API_KEY=                 # clé PRIVÉE (priv_...), serveur uniquement
FRISBII_API_BASE_URL=            # base de l'API Frisbii (déf. https://api.reepay.com, à confirmer)
FRISBII_PLAN_SIMPLE=             # handle du plan "abonnement simple" (20 € HT/mois)
FRISBII_PLAN_SOUTIEN=            # handle du plan "abonnement de soutien" (50 € HT/mois)
FRISBII_WEBHOOK_SECRET=          # secret de signature des webhooks
```

- [ ] **Step 8: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/subscriptions/test_routes.py -v`
Expected: PASS (8 tests).

- [ ] **Step 9: Commit**

```bash
git add src/subscriptions/routes.py src/subscriptions/setup.py src/app.py .template.env tests/subscriptions/
git commit -m "feat(abonnement): routes subscribe/cancel/webhook + câblage app (#90)"
```

---

### Task 6: Page `/compte/abonnement` + câblage de l'accès

**Files:**

- Modify: `src/pages/compte_abonnement.py` (remplacer le placeholder)
- Modify: `src/pages/_compte_shell.py:41-43` (brancher `current_user_has_subscription`)
- Test: `tests/subscriptions/test_compte_abonnement.py`

**Interfaces:**

- Consumes: `src.subscriptions.db.has_active_subscription`, `src.subscriptions.db.get_by_user`, `src.subscriptions.plans.plan_meta`, `src.subscriptions.plans.trial_days`, `flask_login.current_user`.
- Produces: layout de page mis à jour ; `current_user_has_subscription()` réel.

- [ ] **Step 1: Écrire les tests (rendu logique, sans navigateur)**

Create `tests/subscriptions/test_compte_abonnement.py` :

```python
from src.subscriptions import plans


def test_plan_cards_present_when_no_subscription(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    from src.pages import compte_abonnement

    cards = compte_abonnement._plan_cards(trial_for=lambda key: 2)
    text = str(cards)
    assert "Abonnement simple" in text
    assert "Abonnement de soutien" in text
    assert "2 jours d'essai gratuit" in text


def test_plan_cards_no_trial_when_trial_used(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    from src.pages import compte_abonnement

    text = str(compte_abonnement._plan_cards(trial_used=True, trial_for=lambda key: 2))
    assert "Sans période d'essai" in text
    assert "2 jours d'essai gratuit" not in text


def test_active_view_shows_cancel(monkeypatch):
    from src.pages import compte_abonnement

    row = {"plan": "simple", "status": "active", "current_period_end": "2099-01-01T00:00:00+00:00"}
    view = compte_abonnement._active_view(row)
    assert "Résilier" in str(view)


def test_active_view_trial_banner(monkeypatch):
    from src.pages import compte_abonnement

    row = {"plan": "simple", "status": "trial", "current_period_end": "2099-01-01T00:00:00+00:00"}
    assert "Essai gratuit" in str(compte_abonnement._active_view(row))
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: FAIL (`_plan_cards` / `_active_view` absents).

- [ ] **Step 3: Réécrire `compte_abonnement.py`**

Replace le contenu de `src/pages/compte_abonnement.py` :

```python
import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell
from src.subscriptions import db, plans

register_page(
    __name__,
    path="/compte/abonnement",
    title="Abonnement | decp.info",
    name="Abonnement",
    description="Gestion de votre abonnement decp.info.",
)

_PLAN_KEYS = ("simple", "soutien")


def _csrf_input(index: str):
    return dcc.Input(
        type="hidden", id={"type": "csrf-input", "index": index}, name="csrf_token"
    )


def _plan_card(meta: dict, trial: int | None, trial_used: bool):
    if trial_used:
        badge = html.Div(
            "Sans période d'essai (déjà utilisée) — débit immédiat",
            className="text-muted mb-2",
        )
    elif trial:
        badge = html.Div(f"{trial} jours d'essai gratuit", className="text-success mb-2")
    else:
        badge = None
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4(meta["label"]),
                html.P(f"{meta['prix_ht']} € HT / mois"),
                html.P(meta["description"]),
                badge,
                html.Form(
                    method="POST",
                    action="/subscriptions/subscribe",
                    children=[
                        _csrf_input(f"subscribe-{meta['key']}"),
                        dcc.Input(type="hidden", name="plan", value=meta["key"]),
                        html.Button("S'abonner", type="submit", className="btn btn-primary"),
                    ],
                ),
            ]
        ),
        className="mb-3",
    )


def _plan_cards(trial_used=False, trial_for=plans.trial_days):
    cards = []
    for key in _PLAN_KEYS:
        meta = plans.plan_meta(key)
        if meta:
            cards.append(_plan_card(meta, trial_for(key), trial_used))
    return dbc.Row([dbc.Col(c, md=6) for c in cards])


def _explainer():
    return html.Div(
        [
            html.H4("À quoi servent les abonnements"),
            html.Ul(
                [
                    html.Li("Abonnement Frisbii (solution de paiement) : 50 €"),
                    html.Li("Serveur Scaleway : 40 €"),
                    html.Li("Espace de coworking : 250 €"),
                    html.Li("Salaire médian : 3 840 €"),
                ]
            ),
            html.H4("Ce que les abonnements de soutien permettraient"),
            html.Ul(
                [
                    html.Li(
                        "Rédaction d'études à partir des données, par exemple sur les "
                        "acheteurs dont les données sont introuvables et les raisons de "
                        "cette non-publication."
                    ),
                    html.Li(
                        "Coordination des bonnes volontés souhaitant militer pour une "
                        "législation plus exigeante sur la transparence de la commande "
                        "publique."
                    ),
                ]
            ),
        ]
    )


def _active_view(row):
    meta = plans.plan_meta(row["plan"]) or {"label": row["plan"]}
    end = row["current_period_end"]
    blocks = [html.H3(meta["label"]), html.P(f"Statut : {row['status']}")]
    if row["status"] == "trial":
        blocks.append(
            dbc.Alert(
                f"Essai gratuit jusqu'au {end}, puis débit automatique.", color="info"
            )
        )
    elif row["status"] == "cancelled":
        blocks.append(
            dbc.Alert(f"Abonnement résilié, actif jusqu'au {end}.", color="warning")
        )
    else:
        blocks.append(html.P(f"Prochain renouvellement : {end}"))
    if row["status"] in ("trial", "active"):
        blocks.append(
            html.Form(
                method="POST",
                action="/subscriptions/cancel",
                children=[
                    _csrf_input("cancel"),
                    html.Button("Résilier", type="submit", className="btn btn-outline-danger"),
                ],
            )
        )
    return html.Div(blocks)


def _feedback(query):
    msgs = {
        "succes": ("Merci, votre abonnement est en cours d'activation.", "success"),
        "annule": ("Paiement annulé.", "secondary"),
    }
    out = []
    if query.get("paiement") in msgs:
        text, color = msgs[query["paiement"]]
        out.append(dbc.Alert(text, color=color))
    if query.get("resiliation") == "ok":
        out.append(dbc.Alert("Votre abonnement a été résilié.", color="info"))
    if query.get("error") == "frisbii":
        out.append(dbc.Alert("Une erreur est survenue avec le service de paiement.", color="danger"))
    return out


def layout(**query):
    guard = account_guard("/compte/abonnement", require_subscription=False)
    if guard is not None:
        return guard

    row = db.get_by_user(current_user.id) if current_user.is_authenticated else None
    has_access = db.has_active_subscription(current_user.id) if current_user.is_authenticated else False

    trial_used = (
        db.has_used_trial(current_user.id) if current_user.is_authenticated else False
    )

    body = [html.H2("Abonnement"), *_feedback(query)]
    if has_access and row is not None:
        body.append(_active_view(row))
    else:
        body.extend([_plan_cards(trial_used=trial_used), html.Hr(), _explainer()])

    return account_shell("abonnement", html.Div(body))
```

- [ ] **Step 4: Brancher `current_user_has_subscription` dans `_compte_shell.py`**

Dans `src/pages/_compte_shell.py`, remplacer la fonction stub (lignes ~41-43) :

```python
def current_user_has_subscription() -> bool:
    """Stub : à brancher sur la facturation (issue #73)."""
    return False
```

par :

```python
def current_user_has_subscription() -> bool:
    from src.subscriptions import db

    if not current_user.is_authenticated:
        return False
    return db.has_active_subscription(current_user.id)
```

(L'import `from flask_login import current_user` existe déjà en tête de fichier.)

- [ ] **Step 5: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Lancer toute la suite abonnements + vérifs de non-régression compte**

Run: `uv run pytest tests/subscriptions tests/test_compte_pages.py tests/test_compte_shell.py -v`
Expected: PASS (aucune régression sur l'espace compte).

- [ ] **Step 7: Commit**

```bash
git add src/pages/compte_abonnement.py src/pages/_compte_shell.py tests/subscriptions/test_compte_abonnement.py
git commit -m "feat(abonnement): page /compte/abonnement + accès premium réel (#90)"
```

---

## Notes d'intégration (hors code, à faire en environnement de test)

À valider lors du branchement réel sur Frisbii (non bloquant pour le code/tests) :

1. **Base URL & endpoints** : confirmer `FRISBII_API_BASE_URL` et les chemins
   (`/v1/customer`, `/v1/session/subscription`, `/v1/subscription/{h}/cancel`,
   `/v1/subscription/{h}`, `/v1/plan/{h}`) dans la doc Frisbii.
2. **Schéma de signature webhook** : confirmer `HMAC-SHA256(secret, timestamp + id)`
   et ajuster `webhooks.verify_signature` si différent.
3. **Noms de champs subscription** (`state`, `trial_end`, `expires`, `is_cancelled`,
   `next_period_start`) : confirmer et ajuster `webhooks.map_subscription`.
4. **Dashboard Frisbii** : créer les deux plans mensuels (mois glissants, essai 2 j,
   carte collectée à la souscription) et configurer le webhook vers
   `{APP_BASE_URL}/frisbii/webhook`.

## Hors périmètre (rappel spec)

Changement de plan en self-service, montant de soutien libre, réconciliation cron,
historique de factures dans l'UI.
