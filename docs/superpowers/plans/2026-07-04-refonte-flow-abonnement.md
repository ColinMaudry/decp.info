# Refonte du tunnel d'abonnement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre l'offre d'abonnement visible aux visiteurs non connectés et raccourcir le tunnel d'inscription/abonnement.

**Architecture:** Les composants « cards » d'abonnement quittent la page authentifiée `/compte/abonnement` pour la page publique `/a-propos/abonnement`, complétés d'un unique bouton « Je m'abonne » dont la cible dépend de l'état de connexion. Le choix du plan (simple/soutien) migre dans le formulaire `mes-infos`. La validation d'email connecte automatiquement l'utilisateur et le dépose dans `mes-infos`.

**Tech Stack:** Dash 3.4, Dash Bootstrap Components, Flask + Flask-Login, SQLite (users.sqlite), pytest.

## Global Constraints

- Interface et libellés **en français**.
- Imports du code applicatif toujours préfixés `src.` (ex. `src.pages.compte.abonnement`).
- Lancer les tests avec `uv run pytest` (l'activation de venv via Bash n'est pas fiable ici).
- **Soumission de formulaire native** : seul un `dcc.Input`/`dbc.Input` portant un
  attribut `name` est soumis dans le POST d'un `html.Form`. Un `dcc.RadioItems` n'est
  **pas** soumis nativement — le relier à un `dcc.Input(type="hidden", name=...)` via
  callback. `html.Input` n'existe pas en Dash 3.4.
- Boutons : classes Bootstrap existantes (`btn btn-primary`, `btn btn-outline-danger`…), cohérentes avec le reste du site.
- Chaque commit doit passer `uv run pytest` (au minimum les tests touchés).

---

### Task 1 : `linkedin_button` paramétrable + inscription vers le tunnel

Le bouton LinkedIn est réutilisé par `/connexion` et `/inscription`. On lui ajoute un
paramètre `next_url` optionnel pour que l'inscription via LinkedIn finisse dans
`mes-infos` (au lieu du fallback `/compte/admin`).

**Files:**

- Modify: `src/pages/connexion.py` (fonction `linkedin_button`, lignes 31-37)
- Modify: `src/pages/inscription.py` (appel `linkedin_button()`, ligne 73)
- Test: `tests/test_linkedin_button.py` (créer)

**Interfaces:**

- Produces: `linkedin_button(next_url: str | None = None) -> html.A`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# tests/test_linkedin_button.py
def test_linkedin_button_default_has_no_next():
    from src.pages.connexion import linkedin_button

    html_str = str(linkedin_button())
    assert "href='/auth/linkedin'" in html_str
    assert "next=" not in html_str


def test_linkedin_button_with_next_appends_query():
    from src.pages.connexion import linkedin_button

    html_str = str(linkedin_button("/compte/abonnement/mes-infos"))
    assert "/auth/linkedin?next=/compte/abonnement/mes-infos" in html_str


def test_inscription_linkedin_targets_mes_infos():
    from src.pages import inscription

    assert "/auth/linkedin?next=/compte/abonnement/mes-infos" in str(
        inscription.layout()
    )
```

- [ ] **Step 2 : Lancer le test pour vérifier l'échec**

Run: `uv run pytest tests/test_linkedin_button.py -v`
Expected: FAIL (`linkedin_button()` prend 0 argument / le `next` n'est pas présent)

- [ ] **Step 3 : Implémenter**

Dans `src/pages/connexion.py`, remplacer la fonction `linkedin_button` :

```python
def linkedin_button(next_url: str | None = None):
    href = "/auth/linkedin"
    if next_url:
        href += f"?next={next_url}"
    return html.A(
        "Connexion avec LinkedIn",
        href=href,
        className="btn w-100 mb-2",
        style={"backgroundColor": "rgb(10, 102, 194)", "color": "white"},
    )
```

Dans `src/pages/inscription.py`, ligne 73, remplacer `linkedin_button(),` par :

```python
            linkedin_button("/compte/abonnement/mes-infos"),
```

- [ ] **Step 4 : Lancer le test pour vérifier le succès**

Run: `uv run pytest tests/test_linkedin_button.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5 : Commit**

```bash
git add src/pages/connexion.py src/pages/inscription.py tests/test_linkedin_button.py
git commit -m "feat(abonnement): linkedin_button paramétrable par next, inscription vers mes-infos"
```

---

### Task 2 : Auto-login à la validation d'email

`verify_email` doit connecter automatiquement l'utilisateur et le rediriger vers
`mes-infos` au lieu de `/connexion?verified=1`.

**Files:**

- Modify: `src/auth/routes.py` (fonction `verify_email`, lignes 92-101)
- Test: `tests/auth/test_verify_email.py` (modifier le test du token valide)

**Interfaces:**

- Consumes: `db.get_user_by_id`, `db.set_email_verified`, `tokens.consume_verification_token`, `User`, `login_user` (déjà importés dans le module).

- [ ] **Step 1 : Adapter le test pour qu'il échoue**

Dans `tests/auth/test_verify_email.py`, remplacer `test_verify_email_valid_token_marks_user_verified` par :

```python
def test_verify_email_valid_token_logs_in_and_redirects_to_mes_infos(
    client, users_db_path
):
    db.init_schema()
    uid = db.create_user("a@b.c", "hash")
    token = tokens.create_verification_token(uid)

    resp = client.get(f"/auth/verify-email?token={token}")
    assert resp.status_code == 302
    assert "/compte/abonnement/mes-infos" in resp.headers["Location"]
    assert db.get_user_by_id(uid)["email_verified"] == 1
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == str(uid)
```

- [ ] **Step 2 : Lancer le test pour vérifier l'échec**

Run: `uv run pytest tests/auth/test_verify_email.py -v`
Expected: FAIL (Location vaut encore `/connexion?verified=1`, session vide)

- [ ] **Step 3 : Implémenter**

Dans `src/auth/routes.py`, dans `verify_email`, remplacer les deux dernières lignes
(`db.set_email_verified(user_id)` + `return redirect("/connexion?verified=1")`) par :

```python
    db.set_email_verified(user_id)
    login_user(User(db.get_user_by_id(user_id)), remember=True)
    return redirect("/compte/abonnement/mes-infos")
```

- [ ] **Step 4 : Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/auth/test_verify_email.py -v`
Expected: PASS (4 tests — les 3 autres restent inchangés)

- [ ] **Step 5 : Commit**

```bash
git add src/auth/routes.py tests/auth/test_verify_email.py
git commit -m "feat(auth): auto-login à la validation d'email, redirection vers mes-infos"
```

---

### Task 3 : Page publique `/a-propos/abonnement` (cards + bouton « Je m'abonne »)

On installe dans la page publique : les cards informatives (sans bouton par card),
l'explainer, et le bouton unique conditionnel. On retire la sous-section
« Fonctionnalités incluses » des CGU (doublon avec l'explainer).

**Files:**

- Modify: `src/pages/a_propos/abonnement.py`
- Test: `tests/test_abonnement_public.py` (créer)

**Interfaces:**

- Produces:

  - `_plan_card(meta: dict, trial: int | None) -> dbc.Card`
  - `_plan_cards(trial_for=plans.trial_days) -> dbc.Row`
  - `_explainer() -> dbc.Row`
  - `_subscribe_button(authenticated: bool, has_active_subscription: bool, tous_abonnes: bool) -> html.Div`
  - `abonnement_features` et `subscription_terms` restent exportés (déjà consommés par `compte/abonnement_mes_infos.py`).

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# tests/test_abonnement_public.py
import pytest


@pytest.fixture(autouse=True)
def _plan_env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")


def test_plan_cards_informative_no_button():
    from src.pages.a_propos import abonnement as page

    text = str(page._plan_cards(trial_for=lambda key: 2))
    assert "Abonnement" in text
    assert "Abonnement de soutien" in text
    assert "2 jours d'essai gratuit" in text
    assert "S'abonner" not in text


def test_subscribe_button_visitor_goes_to_inscription():
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(False, False, False))
    assert "Je m'abonne" in text
    assert "href='/inscription'" in text


def test_subscribe_button_authenticated_no_sub_goes_to_mes_infos():
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(True, False, False))
    assert "href='/compte/abonnement/mes-infos'" in text


def test_subscribe_button_active_sub_manages():
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(True, True, False))
    assert "Gérer mon abonnement" in text
    assert "href='/compte/abonnement'" in text


def test_subscribe_button_disabled_when_tous_abonnes():
    from src.pages.a_propos import abonnement as page

    text = str(page._subscribe_button(False, False, True))
    assert "disabled" in text


def test_cgu_terms_trimmed_of_features_section():
    from src.pages.a_propos import abonnement as page

    text = str(page.subscription_terms)
    assert "Fonctionnalités incluses" not in text
    assert "Résiliation" in text
    assert "Tarifs" in text
```

- [ ] **Step 2 : Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/test_abonnement_public.py -v`
Expected: FAIL (`_plan_cards`/`_subscribe_button` inexistants ; « Fonctionnalités incluses » encore présent)

- [ ] **Step 3 : Implémenter**

Dans `src/pages/a_propos/abonnement.py` :

3a. Ajouter les imports en tête :

```python
import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask_login import current_user

from src.pages._apropos_shell import apropos_shell
from src.subscriptions import db as sub_db
from src.subscriptions import plans
from src.utils import TOUS_ABONNES
from src.utils.seo import META_CONTENT
```

3b. Ajouter les composants cards (avant `subscription_terms`) :

```python
def _plan_card(meta: dict, trial: int | None):
    badge = (
        html.Div(f"{trial} jours d'essai gratuit", className="mb-3") if trial else None
    )
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4(meta["label"], className="mb-1"),
                html.P(
                    f"{meta['prix_ht']} € HT / mois "
                    f"({str(int(meta['prix_ht']) * 1.2).replace('.0', '')} € TTC)",
                    className="text-muted mb-3",
                ),
                html.P(meta["description"], className="mb-3"),
                badge,
            ],
            className="p-4",
        ),
        className="h-100",
    )


def _plan_cards(trial_for=plans.trial_days):
    cards = []
    for key in ("simple", "soutien"):
        meta = plans.plan_meta(key)
        if meta:
            cards.append(_plan_card(meta, trial_for(key)))
    return dbc.Row([dbc.Col(c, md=6) for c in cards], className="g-4 mb-4")


def _explainer():
    col_left = dbc.Col(
        [html.H4("Fonctionnalités réservées aux abonné·es :"), abonnement_features],
        md=6,
        style={
            "borderRight": "1px solid var(--bs-border-color)",
            "paddingRight": "2rem",
        },
    )
    col_right = dbc.Col(
        [
            html.H4("Ce que les abonnements permettent"),
            html.Ul(
                [
                    html.Li(
                        "passer plus de temps à développer colibre et moins de temps "
                        "à chercher des missions"
                    ),
                    html.Li(
                        "rédaction d'études à partir des données, par exemple sur les "
                        "acheteurs dont les données sont introuvables et les raisons "
                        "de cette non-publication."
                    ),
                    html.Li(
                        "fédération des bonnes volontés souhaitant militer pour une "
                        "législation plus ambitieuse sur la transparence de la "
                        "commande publique."
                    ),
                ]
            ),
        ],
        md=6,
        style={"paddingLeft": "2rem"},
    )
    return dbc.Row([col_left, col_right], className="align-items-start pt-2 mb-4")


def _subscribe_button(
    authenticated: bool, has_active_subscription: bool, tous_abonnes: bool
):
    if tous_abonnes:
        return html.Div(
            [
                dbc.Alert(
                    "Les fonctionnalités normalement accessibles contre un abonnement "
                    "de 20 € HT par mois sont accessibles à tous et toutes en attendant "
                    "la validation de mon dossier pour recevoir des paiements.",
                    color="info",
                ),
                html.A(
                    "Je m'abonne",
                    href="#",
                    className="btn btn-secondary disabled",
                ),
            ],
            className="text-center my-4",
        )
    if authenticated and has_active_subscription:
        label, href = "Gérer mon abonnement", "/compte/abonnement"
    elif authenticated:
        label, href = "Je m'abonne", "/compte/abonnement/mes-infos"
    else:
        label, href = "Je m'abonne", "/inscription"
    return html.Div(
        html.A(label, href=href, className="btn btn-primary btn-lg"),
        className="text-center my-4",
    )
```

3c. Dans `subscription_terms`, **supprimer** le bloc « Fonctionnalités incluses »
(le `html.H4("Fonctionnalités incluses")`, les deux `dcc.Markdown` qui l'entourent
et l'insertion de `abonnement_features`). Garder `abonnement_features` **défini** au
niveau module (il sert à `_explainer`). Le reste des CGU est inchangé.

3d. Remplacer `layout` :

```python
def layout(**_):
    authenticated = current_user.is_authenticated
    has_active = authenticated and sub_db.has_active_subscription(current_user.id)
    body = html.Div(
        [
            _plan_cards(),
            _explainer(),
            _subscribe_button(authenticated, has_active, TOUS_ABONNES),
            subscription_terms,
        ]
    )
    return apropos_shell("abonnement", body)
```

- [ ] **Step 4 : Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/test_abonnement_public.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5 : Commit**

```bash
git add src/pages/a_propos/abonnement.py tests/test_abonnement_public.py
git commit -m "feat(abonnement): page publique avec cards et bouton Je m'abonne conditionnel"
```

---

### Task 4 : `/compte/abonnement` non-abonné → bouton « M'abonner » / « Me réabonner »

La branche non-abonné n'affiche plus de cards mais un bouton dont le libellé dépend de
`has_used_trial`. On supprime les composants cards devenus inutilisés ici et on migre
les tests obsolètes.

**Files:**

- Modify: `src/pages/compte/abonnement.py`
- Modify: `tests/subscriptions/test_compte_abonnement.py`

**Interfaces:**

- Consumes: `db.has_used_trial(user_id) -> bool` (existant).
- Produces: `_reabo_button(has_used_trial: bool) -> html.Div`

- [ ] **Step 1 : Écrire / migrer les tests**

Dans `tests/subscriptions/test_compte_abonnement.py`, **supprimer** ces 4 tests
(devenus obsolètes : les cards et leurs boutons ont quitté ce module) :
`test_plan_cards_present_when_no_subscription`, `test_plan_cards_no_trial_when_trial_used`,
`test_subscribe_buttons_disabled_when_tous_abonnes`, `test_subscribe_buttons_active_when_flag_off`.

**Ajouter** :

```python
def test_reabo_button_never_subscribed():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._reabo_button(has_used_trial=False))
    assert "M'abonner" in text
    assert "Me réabonner" not in text
    assert "href='/a-propos/abonnement'" in text


def test_reabo_button_former_subscriber():
    from src.pages.compte import abonnement as compte_abonnement

    text = str(compte_abonnement._reabo_button(has_used_trial=True))
    assert "Me réabonner" in text
    assert "href='/a-propos/abonnement'" in text
```

- [ ] **Step 2 : Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: FAIL (`_reabo_button` inexistant)

- [ ] **Step 3 : Implémenter**

Dans `src/pages/compte/abonnement.py` :

3a. Supprimer l'import `from src.pages.a_propos.abonnement import abonnement_features`.

3b. Supprimer les fonctions `_plan_card`, `_plan_cards`, `_explainer` (devenues
inutilisées ici — elles vivent désormais dans `a_propos/abonnement.py`).

3c. Ajouter :

```python
def _reabo_button(has_used_trial: bool):
    label = "Me réabonner" if has_used_trial else "M'abonner"
    return html.Div(
        [
            html.P(
                "Abonnez-vous pour accéder aux fonctionnalités réservées "
                "aux abonné·es.",
                className="mb-3",
            ),
            html.A(
                label,
                href="/a-propos/abonnement",
                className="btn btn-primary",
            ),
        ],
        className="mb-4",
    )
```

3d. Dans `layout`, la branche `else` (celle qui faisait
`body.extend([_plan_cards(trial_used=trial_used), _explainer()])`) devient :

```python
    else:
        if row is not None and row["status"] == "expired":
            body.append(
                dbc.Alert(
                    "Votre abonnement a expiré.", color="warning", className="mb-4"
                )
            )
        body.append(_reabo_button(db.has_used_trial(current_user.id)))
```

La ligne `trial_used = db.has_used_trial(...)` en tête de `layout` n'est plus utilisée
que… nulle part → **la supprimer** (lignes ~290-292 : la variable `trial_used`).

- [ ] **Step 4 : Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: PASS (les tests `_active_view`, `_tous_abonnes_banner`, `_show_active_view` + les 2 nouveaux)

- [ ] **Step 5 : Vérifier l'absence de régression d'import**

Run: `uv run pytest tests/test_compte_pages.py tests/subscriptions/ -v`
Expected: PASS (aucun module ne référence plus `compte.abonnement._plan_cards`)

- [ ] **Step 6 : Commit**

```bash
git add src/pages/compte/abonnement.py tests/subscriptions/test_compte_abonnement.py
git commit -m "feat(abonnement): /compte/abonnement non-abonné affiche M'abonner/Me réabonner"
```

---

### Task 5 : CTA de `/connexion` vers l'offre d'abonnement

Le bouton du bas de `/connexion` pointe vers `/a-propos/abonnement` au lieu de
`/inscription`.

**Files:**

- Modify: `src/pages/connexion.py` (bloc final du `layout`, lignes 91-96)
- Test: `tests/test_connexion_page.py` (créer)

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# tests/test_connexion_page.py
def test_connexion_cta_points_to_abonnement():
    from src.pages import connexion

    text = str(connexion.layout())
    assert "/a-propos/abonnement" in text
    assert "Voir les abonnements" in text
```

- [ ] **Step 2 : Lancer le test pour vérifier l'échec**

Run: `uv run pytest tests/test_connexion_page.py -v`
Expected: FAIL (le CTA pointe encore vers `/inscription`)

- [ ] **Step 3 : Implémenter**

Dans `src/pages/connexion.py`, remplacer le dernier bloc du `layout` (le
`html.A("Créer un compte avec mon adresse email", href="/inscription", ...)`) par :

```python
            html.A(
                "Pas encore de compte ? Voir les abonnements",
                href="/a-propos/abonnement",
                className="btn btn-primary w-100",
            ),
```

- [ ] **Step 4 : Lancer le test pour vérifier le succès**

Run: `uv run pytest tests/test_connexion_page.py -v`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add src/pages/connexion.py tests/test_connexion_page.py
git commit -m "feat(abonnement): CTA connexion vers /a-propos/abonnement"
```

---

### Task 6 : Sélecteur de formule dans `mes-infos`

Le formulaire `mes-infos` n'exige plus de paramètre `?plan=` : la formule se choisit
via un `dcc.RadioItems` relié à un champ caché natif soumis dans le POST.

**Files:**

- Modify: `src/pages/compte/abonnement_mes_infos.py`
- Test: `tests/subscriptions/test_mes_infos_plan.py` (créer)

**Interfaces:**

- Produces:

  - `_plan_choices() -> list[dict]` (options `{"label", "value"}` pour « simple » et « soutien »)
  - `_sync_plan(value: str | None) -> str` (callback : recopie la formule choisie, défaut « simple »)

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# tests/subscriptions/test_mes_infos_plan.py
import pytest


@pytest.fixture(autouse=True)
def _plan_env(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")


def test_plan_choices_lists_both_with_prices():
    from src.pages.compte import abonnement_mes_infos as m

    choices = m._plan_choices()
    assert [c["value"] for c in choices] == ["simple", "soutien"]
    assert any("20" in c["label"] for c in choices)
    assert any("50" in c["label"] for c in choices)


def test_sync_plan_returns_selection():
    from src.pages.compte import abonnement_mes_infos as m

    assert m._sync_plan("soutien") == "soutien"


def test_sync_plan_defaults_to_simple_when_empty():
    from src.pages.compte import abonnement_mes_infos as m

    assert m._sync_plan(None) == "simple"
```

- [ ] **Step 2 : Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/subscriptions/test_mes_infos_plan.py -v`
Expected: FAIL (`_plan_choices` / `_sync_plan` inexistants)

- [ ] **Step 3 : Implémenter**

Dans `src/pages/compte/abonnement_mes_infos.py` :

3a. Ajouter l'import `plans` et le callback en tête (à côté des imports existants) :

```python
from src.subscriptions import plans
```

3b. Ajouter les helpers + callback (par ex. juste après `_csrf_input`) :

```python
def _plan_choices():
    choices = []
    for key in ("simple", "soutien"):
        meta = plans.plan_meta(key)
        if meta:
            choices.append(
                {
                    "label": f" {meta['label']} — {meta['prix_ht']} € HT / mois",
                    "value": key,
                }
            )
    return choices


def _plan_selector(default="simple"):
    return html.Div(
        [
            dbc.Label("Formule *"),
            dcc.RadioItems(
                id="inf-plan",
                options=_plan_choices(),
                value=default,
                className="mb-3",
                labelStyle={"display": "block"},
            ),
            dcc.Input(
                type="hidden", id="inf-plan-hidden", name="plan", value=default
            ),
        ]
    )


@callback(
    Output("inf-plan-hidden", "value"),
    Input("inf-plan", "value"),
)
def _sync_plan(value):
    return value or "simple"
```

3c. Dans `layout`, **supprimer** la garde `?plan=` (lignes 53-55) :

```python
    plan = query.get("plan", "")
    if not plan:
        return dcc.Location(href="/compte/abonnement", id="inf-no-plan-redirect")
```

3d. Dans le `html.Form` (`children=`), **remplacer** la ligne
`dcc.Input(type="hidden", name="plan", value=plan),` par un appel au sélecteur en tête
de formulaire :

```python
        children=[
            _csrf_input(),
            _plan_selector(),
            dbc.Row([col1, col2], className="g-4 mb-4"),
            checkboxes,
            html.Button(
                "Ajout d'une carte de paiement",
                id="inf-submit",
                type="submit",
                className="btn btn-primary",
                disabled=True,
            ),
        ],
```

- [ ] **Step 4 : Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/subscriptions/test_mes_infos_plan.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5 : Vérifier qu'aucun test existant ne dépendait de la garde `?plan=`**

Run: `uv run pytest tests/subscriptions/ tests/test_page_loads.py -v`
Expected: PASS

- [ ] **Step 6 : Commit**

```bash
git add src/pages/compte/abonnement_mes_infos.py tests/subscriptions/test_mes_infos_plan.py
git commit -m "feat(abonnement): sélecteur de formule dans mes-infos, plus de param plan requis"
```

---

### Task 7 : Vérification de bout en bout

**Files:** aucun (validation).

- [ ] **Step 1 : Suite complète**

Run: `uv run pytest`
Expected: PASS (aucune régression). Si des tests Selenium échouent faute de Chrome,
les relever mais valider au moins les tests unitaires et de routes touchés.

- [ ] **Step 2 : Revue manuelle du parcours** (skill `verify` recommandé)

Dérouler : `/a-propos/abonnement` (déconnecté) → « Je m'abonne » → `/inscription` →
signup → lien email → auto-login → `mes-infos` (radios présents, défaut « simple »)
→ soumission → checkout. Puis, connecté sans abonnement : `/compte/abonnement`
montre « M'abonner ».

---

## Self-Review (auteur)

**Couverture spec :**

- §1 page publique cards/explainer/bouton/trim CGU → Task 3 ✓
- §2 bouton conditionnel (4 états) → Task 3 (`_subscribe_button`) ✓
- §3 `/compte/abonnement` M'abonner/Me réabonner via `has_used_trial` → Task 4 ✓
- §4 mes-infos sélecteur de formule + suppression garde `?plan=` → Task 6 ✓
- §5 `verify_email` auto-login → Task 2 ✓
- §6 CTA connexion → Task 5 ✓
- §7 `linkedin_button(next)` + inscription → Task 1 ✓

**Placeholders :** aucun ; tout le code est fourni.

**Cohérence des types :** `_subscribe_button(bool, bool, bool)`, `_reabo_button(bool)`,
`_plan_choices() -> list[dict]`, `_sync_plan(str|None) -> str`, `_plan_cards(trial_for)`
— noms et signatures cohérents entre tâches et tests.
