# Changer de méthode de paiement (issue #108) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un·e abonné·e en essai ou actif de changer sa carte bancaire depuis `/compte/abonnement`, via la page hébergée Frisbii dédiée (`hosted_page_links.payment_info` de l'objet subscription).

**Architecture:** Une fonction client Frisbii récupère l'abonnement et construit l'URL de la page hébergée avec `accept_url`/`cancel_url`. Une route Flask (symétrique à `/subscriptions/add-payment` et `/subscriptions/cancel`) sert de point d'entrée POST et redirige (303) vers cette URL. Un bouton sur `/compte/abonnement` déclenche cette route ; les retours (`?carte=succes`/`?carte=annule`) affichent un message dans `_feedback()`.

**Tech Stack:** Python, Flask, Dash + Dash Bootstrap Components, httpx (déjà en place dans `src/subscriptions/client.py`), pytest + monkeypatch pour les tests.

## Global Constraints

- Le bouton n'apparaît que pour `row["status"] in ("trial", "active")` — pas `pending` (garde son bouton "Ajouter une méthode de paiement" existant), pas `cancelled` (rien à facturer, chemin logique = reprendre un abonnement).
- Réutiliser `client.get_subscription` déjà existant (`src/subscriptions/client.py:136`), ne pas dupliquer l'appel HTTP.
- Suivre le pattern CSRF + `html.Form` POST déjà utilisé pour "Me désabonner" / "Ajouter une méthode de paiement" dans `src/pages/compte/abonnement.py`.
- Aucun nouveau webhook/callback : Frisbii associe la nouvelle méthode de paiement à l'abonnement de son côté.

---

### Task 1: `client.get_payment_info_url`

**Files:**

- Modify: `src/subscriptions/client.py`
- Test: `tests/subscriptions/test_client.py`

**Interfaces:**

- Consumes: `get_subscription(subscription_handle: str) -> dict` (déjà défini à `src/subscriptions/client.py:136`), qui retourne le JSON brut de `GET /v1/subscription/{handle}` — notamment `hosted_page_links: {"payment_info": "<url>"}`.
- Produces: `get_payment_info_url(sub_handle: str, accept_url: str, cancel_url: str) -> str`, utilisé par la route du Task 2.

- [ ] **Step 1: Write the failing test**

Ajouter à la fin de `tests/subscriptions/test_client.py` :

```python
def test_get_payment_info_url_appends_query_params(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "handle": "abo-1-1",
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/#/subscription/pay/en_GB/x/abo-1-1"
                },
            },
        )
    )
    url = client.get_payment_info_url(
        "abo-1-1", "https://app/compte/abonnement?carte=succes",
        "https://app/compte/abonnement?carte=annule",
    )
    assert url.startswith(
        "https://checkout.reepay.com/#/subscription/pay/en_GB/x/abo-1-1"
    )
    assert "accept_url=https%3A%2F%2Fapp%2Fcompte%2Fabonnement%3Fcarte%3Dsucces" in url
    assert "cancel_url=https%3A%2F%2Fapp%2Fcompte%2Fabonnement%3Fcarte%3Dannule" in url


def test_get_payment_info_url_merges_existing_query_string(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "handle": "abo-1-2",
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/pay/abo-1-2?locale=fr"
                },
            },
        )
    )
    url = client.get_payment_info_url("abo-1-2", "https://app/ok", "https://app/ko")
    assert "locale=fr" in url
    assert "accept_url=https%3A%2F%2Fapp%2Fok" in url
    assert "cancel_url=https%3A%2F%2Fapp%2Fko" in url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/subscriptions/test_client.py -k payment_info_url -v`
Expected: FAIL with `AttributeError: module 'src.subscriptions.client' has no attribute 'get_payment_info_url'`

- [ ] **Step 3: Write minimal implementation**

Dans `src/subscriptions/client.py`, ajouter l'import en haut du fichier (avec les autres imports) :

```python
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
```

Puis, juste après `get_subscription` (après la ligne `return _call("GET", f"/v1/subscription/{subscription_handle}")`) :

```python
def get_payment_info_url(sub_handle: str, accept_url: str, cancel_url: str) -> str:
    sub = get_subscription(sub_handle)
    url = sub["hosted_page_links"]["payment_info"]
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["accept_url"] = accept_url
    query["cancel_url"] = cancel_url
    return urlunsplit(parts._replace(query=urlencode(query)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/subscriptions/test_client.py -k payment_info_url -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full client test file to check no regression**

Run: `uv run pytest tests/subscriptions/test_client.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/subscriptions/client.py tests/subscriptions/test_client.py
git commit -m "feat(abonnement): client.get_payment_info_url pour le changement de carte Frisbii"
```

---

### Task 2: Route `POST /subscriptions/change-payment-method`

**Files:**

- Modify: `src/subscriptions/routes.py`
- Test: `tests/subscriptions/test_routes.py`

**Interfaces:**

- Consumes: `client.get_payment_info_url(sub_handle, accept_url, cancel_url) -> str` (Task 1) ; `db.get_current(user_id) -> sqlite3.Row | None` (déjà existant, colonne `frisbii_subscription_handle`) ; `client.FrisbiiError` (déjà existant).
- Produces: route Flask `POST /subscriptions/change-payment-method`, utilisée par le bouton du Task 3. Redirige (303) vers l'URL Frisbii en cas de succès, 400 si pas d'abonnement, redirect 302 vers `/compte/abonnement?error=frisbii` en cas d'erreur API.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `tests/subscriptions/test_routes.py` :

```python
def test_change_payment_method_redirects_to_hosted_url(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(
        frisbii_client,
        "get_payment_info_url",
        lambda h, accept_url, cancel_url: f"https://pay.test/{h}?a={accept_url}&c={cancel_url}",
    )
    resp = client.post("/subscriptions/change-payment-method")
    assert resp.status_code == 303
    assert resp.headers["Location"].startswith(f"https://pay.test/{handle}")
    assert "carte%3Dsucces" in resp.headers["Location"] or "carte=succes" in resp.headers["Location"]
    assert "carte%3Dannule" in resp.headers["Location"] or "carte=annule" in resp.headers["Location"]


def test_change_payment_method_without_subscription(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/subscriptions/change-payment-method")
    assert resp.status_code == 400


def test_change_payment_method_api_error_redirects(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")

    def boom(h, accept_url, cancel_url):
        raise frisbii_client.FrisbiiError(500, "boom")

    monkeypatch.setattr(frisbii_client, "get_payment_info_url", boom)
    resp = client.post("/subscriptions/change-payment-method")
    assert resp.status_code == 302
    assert "error=frisbii" in resp.headers["Location"]


def test_change_payment_method_requires_login(sub_app):
    resp = sub_app.test_client().post("/subscriptions/change-payment-method")
    assert resp.status_code in (302, 401)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/subscriptions/test_routes.py -k change_payment_method -v`
Expected: FAIL — `test_change_payment_method_without_subscription` gets a 404 (route doesn't exist yet) instead of 400, others fail similarly.

- [ ] **Step 3: Write minimal implementation**

Dans `src/subscriptions/routes.py`, ajouter la route juste après `add_payment_callback()` (avant `cancel()`) :

```python
@subscriptions_bp.route("/subscriptions/change-payment-method", methods=["POST"])
@login_required
def change_payment_method():
    base = os.getenv("APP_BASE_URL", "")
    row = db.get_current(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement actif", 400
    try:
        url = client.get_payment_info_url(
            row["frisbii_subscription_handle"],
            f"{base}/compte/abonnement?carte=succes",
            f"{base}/compte/abonnement?carte=annule",
        )
    except client.FrisbiiError:
        logger.exception("Échec de récupération du lien de paiement Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    return redirect(url, code=303)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/subscriptions/test_routes.py -k change_payment_method -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full routes test file to check no regression**

Run: `uv run pytest tests/subscriptions/test_routes.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/subscriptions/routes.py tests/subscriptions/test_routes.py
git commit -m "feat(abonnement): route /subscriptions/change-payment-method"
```

---

### Task 3: Bouton et messages de retour sur `/compte/abonnement`

**Files:**

- Modify: `src/pages/compte/abonnement.py`
- Test: `tests/subscriptions/test_compte_abonnement.py`

**Interfaces:**

- Consumes: rien de nouveau — utilise `_csrf_input()` déjà défini dans ce fichier (`src/pages/compte/abonnement.py:18`).
- Produces: `_active_view(row)` inclut désormais le bouton pour `status in ("trial", "active")` ; `_feedback(query)` gère `query.get("carte")`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `tests/subscriptions/test_compte_abonnement.py` :

```python
def test_active_view_shows_change_payment_method_for_active():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    text = str(compte_abonnement._active_view(row))
    assert "Changer de méthode de paiement" in text
    assert "/subscriptions/change-payment-method" in text


def test_active_view_shows_change_payment_method_for_trial():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "trial",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Changer de méthode de paiement" in str(
        compte_abonnement._active_view(row)
    )


def test_active_view_hides_change_payment_method_for_cancelled():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "cancelled",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Changer de méthode de paiement" not in str(
        compte_abonnement._active_view(row)
    )


def test_active_view_hides_change_payment_method_for_pending():
    from src.pages.compte import abonnement as compte_abonnement

    row = {"plan": "simple", "status": "pending", "current_period_end": None}
    text = str(compte_abonnement._active_view(row))
    assert "Changer de méthode de paiement" not in text
    assert "Ajouter une méthode de paiement" in text


def test_feedback_carte_succes():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._feedback({"carte": "succes"}))
    assert "Méthode de paiement mise à jour." in text


def test_feedback_carte_annule():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._feedback({"carte": "annule"}))
    assert "Modification annulée." in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: FAIL — the 6 new tests fail (button/messages absent), the 8 pre-existing tests in this file still PASS.

- [ ] **Step 3: Write minimal implementation**

Dans `src/pages/compte/abonnement.py`, modifier `_active_view` : remplacer le bloc

```python
    if row["status"] in ("pending", "trial", "active"):
        blocks.append(
            html.Button(
                "Me désabonner",
                id="resiliation-trigger",
                n_clicks=0,
                className="btn btn-outline-danger mt-3",
            )
        )

    return html.Div(blocks)
```

par :

```python
    if row["status"] in ("trial", "active"):
        blocks.append(
            html.Form(
                method="POST",
                action="/subscriptions/change-payment-method",
                children=[
                    _csrf_input(),
                    html.Button(
                        "Changer de méthode de paiement",
                        type="submit",
                        className="btn btn-outline-secondary mt-3 me-2",
                    ),
                ],
                style={"display": "inline-block"},
            )
        )

    if row["status"] in ("pending", "trial", "active"):
        blocks.append(
            html.Button(
                "Me désabonner",
                id="resiliation-trigger",
                n_clicks=0,
                className="btn btn-outline-danger mt-3",
            )
        )

    return html.Div(blocks)
```

Puis modifier `_feedback` : remplacer

```python
    if query.get("error") == "frisbii":
        out.append(
            dbc.Alert(
                "Une erreur est survenue avec le service de paiement.", color="primary"
            )
        )
    return out
```

par :

```python
    if query.get("carte") == "succes":
        out.append(dbc.Alert("Méthode de paiement mise à jour.", color="success"))
    if query.get("carte") == "annule":
        out.append(dbc.Alert("Modification annulée.", color="secondary"))
    if query.get("error") == "frisbii":
        out.append(
            dbc.Alert(
                "Une erreur est survenue avec le service de paiement.", color="primary"
            )
        )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: All 14 tests PASS (8 pre-existing + 6 new)

- [ ] **Step 5: Run the full subscriptions test suite to check no regression**

Run: `uv run pytest tests/subscriptions/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/pages/compte/abonnement.py tests/subscriptions/test_compte_abonnement.py
git commit -m "feat(abonnement): bouton changer de méthode de paiement sur /compte/abonnement"
```

---

### Task 4: Vérification manuelle en local

**Files:** aucun (vérification uniquement)

- [ ] **Step 1: Lancer l'app en local**

Run: `uv run run.py`

- [ ] **Step 2: Créer un abonnement actif de test et vérifier l'affichage du bouton**

Se connecter, créer un abonnement (trial ou active selon état de la base de test), aller sur `/compte/abonnement`, vérifier que le bouton "Changer de méthode de paiement" est visible, et absent une fois l'abonnement résilié (statut `cancelled`).

- [ ] **Step 3: Vérifier le clic (sans compte Frisbii réel si `FRISBII_API_KEY` n'est pas configurée en local)**

Si `FRISBII_API_KEY` n'est pas renseignée, le clic déclenchera une `FrisbiiError` (requête échouée) → vérifier la redirection vers `/compte/abonnement?error=frisbii` et l'affichage du message d'erreur existant. Si une clé de test Frisbii est disponible, vérifier la redirection réelle vers la page hébergée et le retour via `?carte=succes`/`?carte=annule`.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest`
Expected: All PASS

Pas de commit pour cette tâche (vérification uniquement).
