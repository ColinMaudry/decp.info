# Configurer son abonnement (#109) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un·e abonné·e `active`, `trial` ou `pending` de changer de formule (simple ↔ soutien) et de mettre à jour ses infos de facturation depuis `/compte/abonnement`, et afficher le prix (HT + TTC) de la formule courante.

**Architecture:** On réutilise la page `/compte/abonnement/mes-infos` en la « flexibilisant » via un `mode` dérivé de l'état de l'abonnement (`configure` vs `subscribe`), plutôt que de créer une page dupliquée (impossible de partager les `id` de composants Dash entre deux pages). Un nouveau bouton « Configurer mon abonnement » sur `/compte/abonnement` y renvoie. Le changement de formule passe par une nouvelle route `/subscriptions/update` qui appelle `update_customer` puis, si la formule change, un nouvel endpoint client `change_subscription` (`PUT /v1/subscription/{handle}`), sans redirection vers un checkout.

**Tech Stack:** Dash 3.4, Dash Bootstrap Components, Flask (blueprint `subscriptions`), httpx (client Frisbii/Reepay), pytest.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `src.subscriptions.client`), jamais `subscriptions.client`.
- `suppress_callback_exceptions=True` est déjà activé (`src/app.py:88`) : les composants rendus conditionnellement (cases à cocher absentes en mode `configure`) ne cassent pas les callbacks — un callback dont un `Input` n'existe pas ne se déclenche simplement pas.
- TVA France = 20 % : prix TTC = `round(prix_ht * 1.2, 2)`, formaté avec `:g` pour éviter les artefacts flottants (ex. `28.8`, pas `28.799999999999997`).
- Effet du changement de formule : `timing="renewal"` (prochaine échéance) pour `active`/`trial` ; `timing="immediate"` pour `pending` (pas d'échéance à laquelle rattacher un renouvellement).
- Avant `git add`/`git commit`, exécuter `pre-commit` (ruff formate ; prettier reformate le markdown). Terminer chaque message de commit par `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Lancer les tests avec `uv run pytest` (l'activation du venv dans le shell n'est pas fiable ici). Chaque tâche ne lance QUE son fichier de test ; la suite complète (`uv run pytest`, sans chemin) uniquement à la toute fin.

---

### Task 1: Endpoint client `change_subscription`

**Files:**

- Modify: `src/subscriptions/client.py` (ajouter la fonction en fin de fichier)
- Test: `tests/subscriptions/test_client.py`

**Interfaces:**

- Produces: `client.change_subscription(sub_handle: str, plan_handle: str, timing: str = "renewal") -> dict` — appelle `PUT /v1/subscription/{sub_handle}` avec le corps `{"timing": timing, "plan": plan_handle}`.

- [ ] **Step 1: Write the failing test**

Ajouter dans `tests/subscriptions/test_client.py` :

```python
def test_change_subscription_sends_timing_and_plan(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "abo-1-1"}))
    client.change_subscription("abo-1-1", "plan_soutien", timing="renewal")
    call = fake_httpx["calls"][0]
    assert call["method"] == "PUT"
    assert call["url"] == "https://api.test/v1/subscription/abo-1-1"
    assert call["json"] == {"timing": "renewal", "plan": "plan_soutien"}


def test_change_subscription_immediate_timing(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "abo-1-2"}))
    client.change_subscription("abo-1-2", "plan_simple", timing="immediate")
    assert fake_httpx["calls"][0]["json"]["timing"] == "immediate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/subscriptions/test_client.py::test_change_subscription_sends_timing_and_plan -v`
Expected: FAIL with `AttributeError: module 'src.subscriptions.client' has no attribute 'change_subscription'`

- [ ] **Step 3: Write minimal implementation**

Ajouter en fin de `src/subscriptions/client.py` :

```python
def change_subscription(
    sub_handle: str, plan_handle: str, timing: str = "renewal"
) -> dict:
    return _call(
        "PUT",
        f"/v1/subscription/{sub_handle}",
        json={"timing": timing, "plan": plan_handle},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/subscriptions/test_client.py -v`
Expected: PASS (tous, dont les deux nouveaux)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/subscriptions/client.py tests/subscriptions/test_client.py
git add src/subscriptions/client.py tests/subscriptions/test_client.py
git commit -m "feat(abonnement): client.change_subscription (PUT /v1/subscription) (#109)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Route `/subscriptions/update`

**Files:**

- Modify: `src/subscriptions/routes.py` (ajouter la route après `change_payment_method`, avant `cancel`)
- Test: `tests/subscriptions/test_routes.py`

**Interfaces:**

- Consumes: `client.change_subscription(...)` (Task 1), `client.update_customer`, `db.get_current`, `plans.resolve_handle`, `auth_db.set_siret`.
- Produces: route `POST /subscriptions/update` — met à jour le customer Frisbii et, si la formule diffère, appelle `change_subscription` ; redirige `303` vers `/compte/abonnement?maj=succes`.

Comportement : valide d'abord le plan (400 si inconnu), puis vérifie l'abonnement (400 si aucun), met à jour les infos de facturation, change la formule seulement si le handle diffère. `timing="immediate"` si `status == "pending"`, sinon `"renewal"`.

- [ ] **Step 1: Write the failing tests**

Ajouter dans `tests/subscriptions/test_routes.py` :

```python
def test_update_changes_plan_and_redirects(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})
    captured = {}

    def fake_change(sub_handle, plan_handle, timing="renewal"):
        captured.update(sub_handle=sub_handle, plan_handle=plan_handle, timing=timing)
        return {}

    monkeypatch.setattr(frisbii_client, "change_subscription", fake_change)
    resp = client.post("/subscriptions/update", data={"plan": "soutien"})
    assert resp.status_code == 303
    assert "maj=succes" in resp.headers["Location"]
    assert captured["sub_handle"] == handle
    assert captured["plan_handle"] == "plan_soutien"
    assert captured["timing"] == "renewal"


def test_update_pending_uses_immediate_timing(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})
    captured = {}
    monkeypatch.setattr(
        frisbii_client,
        "change_subscription",
        lambda sub_handle, plan_handle, timing="renewal": captured.update(timing=timing),
    )
    resp = client.post("/subscriptions/update", data={"plan": "soutien"})
    assert resp.status_code == 303
    assert captured["timing"] == "immediate"


def test_update_same_plan_skips_change_subscription(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    called = []
    monkeypatch.setattr(frisbii_client, "update_customer", lambda h, d: {})
    monkeypatch.setattr(
        frisbii_client,
        "change_subscription",
        lambda *a, **k: called.append(a),
    )
    resp = client.post("/subscriptions/update", data={"plan": "simple"})
    assert resp.status_code == 303
    assert "maj=succes" in resp.headers["Location"]
    assert called == [], "formule inchangée : change_subscription ne doit pas être appelé"


def test_update_without_subscription_returns_400(logged_in_client):
    client, _ = logged_in_client
    resp = client.post("/subscriptions/update", data={"plan": "simple"})
    assert resp.status_code == 400


def test_update_unknown_plan_returns_400(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")
    resp = client.post("/subscriptions/update", data={"plan": "bidon"})
    assert resp.status_code == 400


def test_update_api_error_redirects(logged_in_client, monkeypatch):
    client, uid = logged_in_client
    handle, _ = db.create_pending(uid, "colibre-%d" % uid, "simple")
    db.update_from_webhook(handle, "active", "2099-01-01T00:00:00+00:00")

    def boom(h, d):
        raise frisbii_client.FrisbiiError(500, "boom")

    monkeypatch.setattr(frisbii_client, "update_customer", boom)
    resp = client.post("/subscriptions/update", data={"plan": "soutien"})
    assert resp.status_code == 302
    assert "error=frisbii" in resp.headers["Location"]


def test_update_requires_login(sub_app):
    resp = sub_app.test_client().post("/subscriptions/update", data={"plan": "simple"})
    assert resp.status_code in (302, 401)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/subscriptions/test_routes.py::test_update_changes_plan_and_redirects -v`
Expected: FAIL avec `404` (route inexistante)

- [ ] **Step 3: Write the route**

Dans `src/subscriptions/routes.py`, insérer après la fonction `change_payment_method` (avant `cancel`) :

```python
@subscriptions_bp.route("/subscriptions/update", methods=["POST"])
@login_required
def update():
    new_plan_key = request.form.get("plan") or ""
    new_handle = plans.resolve_handle(new_plan_key)
    if new_handle is None:
        return "Plan inconnu", 400

    row = db.get_current(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement à mettre à jour", 400

    cust = _customer_handle(current_user.id)
    siret = (request.form.get("siret") or "").strip()
    billing: dict = {
        "email": current_user.email,
        "first_name": request.form.get("first_name", ""),
        "last_name": request.form.get("last_name", ""),
        "address": request.form.get("address", ""),
        "city": request.form.get("city", ""),
        "postal_code": request.form.get("postal_code", ""),
        "country": request.form.get("country", "FR"),
    }
    if request.form.get("address2"):
        billing["address2"] = request.form["address2"]
    if request.form.get("company"):
        billing["company"] = request.form["company"]

    try:
        if siret:
            auth_db.set_siret(current_user.id, siret)
        client.update_customer(cust, billing)
        if new_handle != plans.resolve_handle(row["plan"]):
            timing = "immediate" if row["status"] == "pending" else "renewal"
            client.change_subscription(
                row["frisbii_subscription_handle"], new_handle, timing
            )
    except client.FrisbiiError:
        logger.exception("Échec de mise à jour de l'abonnement Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    return redirect("/compte/abonnement?maj=succes", code=303)
```

(Aucun import à ajouter : `client`, `db`, `plans`, `auth_db`, `logger`, `current_user`, `request`, `redirect` sont déjà importés dans ce fichier.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/subscriptions/test_routes.py -v`
Expected: PASS (tous)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/subscriptions/routes.py tests/subscriptions/test_routes.py
git add src/subscriptions/routes.py tests/subscriptions/test_routes.py
git commit -m "feat(abonnement): route /subscriptions/update (maj formule + facturation) (#109)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Page `/compte/abonnement` — prix, bouton « Configurer », message de succès

**Files:**

- Modify: `src/pages/compte/abonnement.py` (`_active_view`, `_feedback`, + nouveau helper `_price_text`)
- Test: `tests/subscriptions/test_compte_abonnement.py`

**Interfaces:**

- Produces: `_price_text(meta: dict) -> str | None` ; `_active_view` affiche le prix sous le libellé et un lien « Configurer mon abonnement » (statuts `pending`/`trial`/`active`) ; `_feedback` gère `maj=succes`.

- [ ] **Step 1: Write the failing tests**

Ajouter dans `tests/subscriptions/test_compte_abonnement.py` :

```python
def test_price_text_rounds_ttc():
    from src.pages.compte import abonnement as compte_abonnement

    assert compte_abonnement._price_text({"prix_ht": 20}) == "20 € HT / mois (24 € TTC)"
    assert compte_abonnement._price_text({"prix_ht": 50}) == "50 € HT / mois (60 € TTC)"
    assert compte_abonnement._price_text({"label": "x"}) is None


def test_active_view_shows_price():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "24 € TTC" in str(compte_abonnement._active_view(row))


def test_active_view_shows_configure_button_for_active():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    text = str(compte_abonnement._active_view(row))
    assert "Configurer mon abonnement" in text
    assert "href='/compte/abonnement/mes-infos'" in text


def test_active_view_shows_configure_button_for_pending():
    from src.pages.compte import abonnement as compte_abonnement

    row = {"plan": "simple", "status": "pending", "current_period_end": None}
    assert "Configurer mon abonnement" in str(compte_abonnement._active_view(row))


def test_active_view_hides_configure_button_for_cancelled():
    from src.pages.compte import abonnement as compte_abonnement

    row = {
        "plan": "simple",
        "status": "cancelled",
        "current_period_end": "2099-01-01T00:00:00+00:00",
    }
    assert "Configurer mon abonnement" not in str(compte_abonnement._active_view(row))


def test_feedback_maj_succes():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._feedback({"maj": "succes"}))
    assert "Votre abonnement a été mis à jour." in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py::test_price_text_rounds_ttc -v`
Expected: FAIL avec `AttributeError: ... has no attribute '_price_text'`

- [ ] **Step 3a: Add `_price_text` helper**

Dans `src/pages/compte/abonnement.py`, ajouter avant `_active_view` :

```python
def _price_text(meta: dict) -> str | None:
    ht = meta.get("prix_ht")
    if ht is None:
        return None
    return f"{ht} € HT / mois ({round(ht * 1.2, 2):g} € TTC)"
```

- [ ] **Step 3b: Show price in `_active_view`**

Dans `_active_view`, remplacer :

```python
    meta = plans.plan_meta(row["plan"]) or {"label": row["plan"]}
    end = format_date_french(row["current_period_end"])
    blocks = [html.H3(meta["label"], className="mb-3")]
```

par :

```python
    meta = plans.plan_meta(row["plan"]) or {"label": row["plan"]}
    end = format_date_french(row["current_period_end"])
    blocks = [html.H3(meta["label"], className="mb-1")]
    price = _price_text(meta)
    if price:
        blocks.append(html.P(price, className="text-muted mb-3"))
```

- [ ] **Step 3c: Add « Configurer mon abonnement » button**

Toujours dans `_active_view`, juste avant le bloc `if row["status"] in ("trial", "active"):` (celui du formulaire « Changer de méthode de paiement »), insérer :

```python
    if row["status"] in ("pending", "trial", "active"):
        blocks.append(
            html.A(
                "Configurer mon abonnement",
                href="/compte/abonnement/mes-infos",
                className="btn btn-outline-primary mt-3 me-2",
            )
        )

```

- [ ] **Step 3d: Handle `maj=succes` in `_feedback`**

Dans `_feedback`, ajouter avant `return out` :

```python
    if query.get("maj") == "succes":
        out.append(dbc.Alert("Votre abonnement a été mis à jour.", color="success"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: PASS (tous, y compris les tests existants qui doivent rester verts)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/compte/abonnement.py tests/subscriptions/test_compte_abonnement.py
git add src/pages/compte/abonnement.py tests/subscriptions/test_compte_abonnement.py
git commit -m "feat(abonnement): prix + bouton Configurer sur /compte/abonnement (#109)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `mes-infos` — mode configure/subscribe

**Files:**

- Modify: `src/pages/compte/abonnement_mes_infos.py`
- Test: `tests/subscriptions/test_mes_infos_plan.py`

**Interfaces:**

- Produces:

  - `_mode_for(row) -> str` — `"configure"` si `row` et `row["status"]` ∈ {active, trial, pending}, sinon `"subscribe"`.
  - `_submit_button(mode: str) -> html.Button` — `id="inf-submit"`, libellé + `disabled` selon le mode.
  - `_selectable_cards(trial_for, selected=None)` — la card dont la clé == `selected` reçoit la classe `selected`.
  - `_consent_checklists() -> list` et `_legal_note()` — extraits de l'ancien bloc `checkboxes`.
  - `layout()` rend un `dcc.Store(id="inf-sub-info")` et un `html.Div(id="inf-change-hint")` dans les deux modes (Task 5 s'en sert).

- [ ] **Step 1: Write the failing tests**

Ajouter dans `tests/subscriptions/test_mes_infos_plan.py` :

```python
def test_mode_for_derives_from_status():
    from src.pages.compte import abonnement_mes_infos as m

    for status in ("active", "trial", "pending"):
        assert m._mode_for({"status": status}) == "configure"
    assert m._mode_for({"status": "cancelled"}) == "subscribe"
    assert m._mode_for({"status": "expired"}) == "subscribe"
    assert m._mode_for(None) == "subscribe"


def test_submit_button_subscribe_mode():
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m._submit_button("subscribe"))
    assert "Ajouter une carte de paiement" in text
    assert "disabled" in text


def test_submit_button_configure_mode():
    from src.pages.compte import abonnement_mes_infos as m

    btn = m._submit_button("configure")
    text = str(btn)
    assert "Mettre à jour mon abonnement" in text
    assert btn.disabled is False


def test_selectable_cards_preselects_current_plan():
    from src.pages.compte import abonnement_mes_infos as m

    text = str(m._selectable_cards(trial_for=lambda key: None, selected="soutien"))
    # la card soutien est marquée sélectionnée, pas la card simple
    assert "plan-selectable selected" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/subscriptions/test_mes_infos_plan.py::test_mode_for_derives_from_status -v`
Expected: FAIL avec `AttributeError: ... has no attribute '_mode_for'`

- [ ] **Step 3a: Add import + helpers**

En haut de `src/pages/compte/abonnement_mes_infos.py`, ajouter l'import :

```python
from src.utils.frontend import format_date_french
```

Ajouter ces helpers (par ex. après `_trial_for`) :

```python
def _mode_for(row) -> str:
    if row is not None and row["status"] in ("active", "trial", "pending"):
        return "configure"
    return "subscribe"


def _submit_button(mode: str):
    label = (
        "Mettre à jour mon abonnement"
        if mode == "configure"
        else "Ajouter une carte de paiement"
    )
    return html.Button(
        label,
        id="inf-submit",
        type="submit",
        className="btn btn-primary",
        disabled=(mode == "subscribe"),
    )
```

- [ ] **Step 3b: Add `selected` param to `_selectable_cards`**

Remplacer la signature et le corps de `_selectable_cards` :

```python
def _selectable_cards(trial_for, selected=None):
    cols = []
    for key in ("simple", "soutien"):
        meta = plans.plan_meta(key)
        if not meta:
            continue
        base = "plan-selectable selected" if key == selected else "plan-selectable"
        cols.append(
            dbc.Col(
                html.Div(
                    _plan_card(meta, trial_for(key)),
                    id=f"plan-card-{key}",
                    n_clicks=0,
                    className=base,
                ),
                md=6,
            )
        )
    return dbc.Row(cols, className="g-4 mb-2")
```

- [ ] **Step 3c: Extract legal note + consent checklists**

Remplacer le bloc `checkboxes = html.Div([...])` (dans `layout`) par deux helpers au niveau module :

```python
def _legal_note():
    return dcc.Markdown(
        """\\* Champ obligatoire

 Si vous préférez régler par virement bancaire et une facturation annuelle plutôt qu'un réglement mensuel automatique par carte bancaire, [contactez-moi](/a-propos/contact)."""
    )


def _consent_checklists():
    return [
        dcc.Checklist(
            id="inf-cb-retractation",
            options=[
                {
                    "label": "Je renonce à mon droit de rétractation légal de 14 jours.",
                    "value": "ok",
                }
            ],
            value=[],
            className="mb-2",
        ),
        dcc.Checklist(
            id="inf-cb-cgu",
            options=[
                {
                    "label": [
                        "J'ai lu et accepte les ",
                        html.A(
                            "conditions générales d'utilisation du service",
                            href="#",
                            id="inf-cgu-link",
                            style={"cursor": "pointer"},
                        ),
                        ".",
                    ],
                    "value": "ok",
                }
            ],
            value=[],
            className="mb-4",
        ),
    ]
```

- [ ] **Step 3d: Rewire `layout()`**

Au début de `layout`, après le `guard`, calculer le mode et les valeurs dérivées :

```python
    row = sub_db.get_current(current_user.id)
    mode = _mode_for(row)
    selected = row["plan"] if mode == "configure" else None
    echeance = (
        format_date_french(row["current_period_end"])
        if mode == "configure" and row["current_period_end"]
        else None
    )
    sub_info = (
        {"current_plan": selected, "status": row["status"], "echeance": echeance}
        if mode == "configure"
        else {}
    )
```

Remplacer le `html.Form(...)` existant par :

```python
    form = html.Form(
        method="POST",
        action="/subscriptions/subscribe"
        if mode == "subscribe"
        else "/subscriptions/update",
        children=[
            _csrf_input(),
            html.Div(
                "Choisissez votre formule :"
                if mode == "subscribe"
                else "Votre formule :",
                id="inf-plan-invite",
                className="fw-bold mb-2",
            ),
            _selectable_cards(_trial_for(current_user.id), selected=selected),
            html.Div(id="inf-change-hint", className="d-none"),
            dcc.Store(id="inf-sub-info", data=sub_info),
            dcc.Input(
                type="hidden", id="inf-plan-hidden", name="plan", value=selected or ""
            ),
            dbc.Row([col1, col2], className="g-4 mb-4"),
            _legal_note(),
            *(_consent_checklists() if mode == "subscribe" else []),
            _submit_button(mode),
        ],
    )
```

Enfin, ne rendre la modale CGU qu'en mode `subscribe`. Remplacer le `return account_shell(...)` final par :

```python
    return account_shell(
        "abonnement",
        html.Div(
            [
                html.H2("Mes informations de facturation", className="mb-4"),
                dbc.Alert(
                    "Informations récupérées depuis le prestataire de paiement, vous pouvez les modifier si besoin.",
                    color="info",
                    className="mb-4",
                )
                if prefill
                else None,
                form,
                _cgu_modal() if mode == "subscribe" else None,
            ]
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/subscriptions/test_mes_infos_plan.py -v`
Expected: PASS (nouveaux + existants `test_selectable_cards_render_both_plans`, `test_selection_state_*`, `test_submit_disabled_without_plan`)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/compte/abonnement_mes_infos.py tests/subscriptions/test_mes_infos_plan.py
git add src/pages/compte/abonnement_mes_infos.py tests/subscriptions/test_mes_infos_plan.py
git commit -m "feat(abonnement): mode configure sur mes-infos (formule préactivée, sans cases) (#109)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `mes-infos` — hint « prochaine échéance »

**Files:**

- Modify: `src/pages/compte/abonnement_mes_infos.py` (`_change_hint` + callback `_select_plan`)
- Test: `tests/subscriptions/test_mes_infos_plan.py`

**Interfaces:**

- Consumes: `dcc.Store(id="inf-sub-info")` et `html.Div(id="inf-change-hint")` rendus en Task 4.
- Produces: `_change_hint(selected: str, sub_info: dict | None) -> tuple[str, str]` — `(className, children)` du hint ; le callback `_select_plan` renvoie désormais 6 sorties (les 4 existantes + className/children du hint).

Règles : affiché uniquement si `sub_info` a un `current_plan`, `status` ∈ {active, trial}, et `selected != current_plan`. Sinon masqué (`d-none`, texte vide). `pending` → toujours masqué.

- [ ] **Step 1: Write the failing tests**

Ajouter dans `tests/subscriptions/test_mes_infos_plan.py` :

```python
def test_change_hint_shown_when_plan_differs():
    from src.pages.compte import abonnement_mes_infos as m

    cls, txt = m._change_hint(
        "soutien",
        {"current_plan": "simple", "status": "active", "echeance": "1er janvier"},
    )
    assert cls != "d-none"
    assert "prochaine échéance : 1er janvier" in txt


def test_change_hint_hidden_when_same_plan():
    from src.pages.compte import abonnement_mes_infos as m

    cls, txt = m._change_hint(
        "simple",
        {"current_plan": "simple", "status": "active", "echeance": "1er janvier"},
    )
    assert cls == "d-none"
    assert txt == ""


def test_change_hint_hidden_for_pending():
    from src.pages.compte import abonnement_mes_infos as m

    cls, _ = m._change_hint(
        "soutien",
        {"current_plan": "simple", "status": "pending", "echeance": None},
    )
    assert cls == "d-none"


def test_change_hint_hidden_in_subscribe_mode():
    from src.pages.compte import abonnement_mes_infos as m

    cls, _ = m._change_hint("soutien", {})
    assert cls == "d-none"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/subscriptions/test_mes_infos_plan.py::test_change_hint_shown_when_plan_differs -v`
Expected: FAIL avec `AttributeError: ... has no attribute '_change_hint'`

- [ ] **Step 3a: Add `_change_hint` helper**

Dans `src/pages/compte/abonnement_mes_infos.py`, ajouter :

```python
def _change_hint(selected: str, sub_info: dict | None) -> tuple[str, str]:
    sub_info = sub_info or {}
    current = sub_info.get("current_plan")
    if (
        not current
        or sub_info.get("status") not in ("active", "trial")
        or selected == current
    ):
        return "d-none", ""
    echeance = sub_info.get("echeance")
    return (
        "text-muted mt-2",
        f"Le changement d'abonnement sera appliqué à la prochaine échéance : {echeance}.",
    )
```

- [ ] **Step 3b: Extend the `_select_plan` callback**

Remplacer le callback `_select_plan` et son décorateur par :

```python
@callback(
    Output("inf-plan-hidden", "value"),
    Output("plan-card-simple", "className"),
    Output("plan-card-soutien", "className"),
    Output("inf-plan-invite", "className"),
    Output("inf-change-hint", "className"),
    Output("inf-change-hint", "children"),
    Input("plan-card-simple", "n_clicks"),
    Input("plan-card-soutien", "n_clicks"),
    State("inf-sub-info", "data"),
    prevent_initial_call=True,
)
def _select_plan(_n_simple, _n_soutien, sub_info):
    selected = "simple" if ctx.triggered_id == "plan-card-simple" else "soutien"
    value, cls_simple, cls_soutien, cls_invite = _selection_state(selected)
    hint_cls, hint_txt = _change_hint(selected, sub_info)
    return value, cls_simple, cls_soutien, cls_invite, hint_cls, hint_txt
```

(`State` est déjà importé depuis `dash` en tête de fichier.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/subscriptions/test_mes_infos_plan.py -v`
Expected: PASS (tous)

- [ ] **Step 5: Commit**

```bash
pre-commit run --files src/pages/compte/abonnement_mes_infos.py tests/subscriptions/test_mes_infos_plan.py
git add src/pages/compte/abonnement_mes_infos.py tests/subscriptions/test_mes_infos_plan.py
git commit -m "feat(abonnement): message 'changement à la prochaine échéance' sous les cards (#109)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Vérification finale

- [ ] **Step 1: Run the whole subscriptions test suite**

Run: `uv run pytest tests/subscriptions/ -v`
Expected: PASS (aucune régression)

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest`
Expected: PASS (les tests Selenium nécessitent Chrome/Chromium ; si l'environnement n'en a pas, noter les échecs Selenium comme non liés et confirmer que `tests/subscriptions/` est vert).

- [ ] **Step 3: Sanity-check manuel (optionnel mais recommandé)**

Lancer l'app (`uv run run.py`), se connecter avec un compte ayant un abonnement `active`, aller sur `/compte/abonnement` : vérifier le prix affiché et le bouton « Configurer mon abonnement ». Cliquer → `/compte/abonnement/mes-infos` : formule courante présélectionnée, pas de cases à cocher, bouton « Mettre à jour mon abonnement ». Cliquer sur l'autre formule → le message « … prochaine échéance : {date} » apparaît.

---

## Notes d'implémentation

- **Pourquoi `inf-change-hint` et `inf-sub-info` sont rendus dans les deux modes** : le callback `_select_plan` est enregistré une seule fois et référence ces `id` en sortie/état. Les rendre toujours (vides en mode `subscribe`) évite tout souci de composant manquant et garde le callback identique quel que soit le mode.
- **Pourquoi `_toggle_submit` n'est pas modifié** : ses `Input` (`inf-cb-retractation`, `inf-cb-cgu`) n'existent pas en mode `configure`, donc le callback ne se déclenche pas et le bouton conserve son `disabled=False` défini par `_submit_button("configure")`. En mode `subscribe`, comportement inchangé.
- **Timing facturation** : `update_customer` prend effet immédiatement (adresse/SIRET), tandis que le changement de formule est différé à l'échéance (`renewal`) — d'où le message de succès générique « Votre abonnement a été mis à jour. ».
