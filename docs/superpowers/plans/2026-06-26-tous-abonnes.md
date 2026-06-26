# Accès gratuit pour tous (`TOUS_ABONNES`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un drapeau d'environnement `TOUS_ABONNES` qui ouvre gratuitement les fonctionnalités réservées aux abonnés à tout utilisateur connecté, affiche un bandeau d'info sur `/compte/abonnement` et y grise les boutons « S'abonner ».

**Architecture:** L'accès est déjà centralisé dans `src/pages/_compte_shell.py::current_user_has_subscription()` (pilote menu + `account_guard`). On y branche le drapeau. La page `/compte/abonnement` lit le même drapeau pour afficher un bandeau et désactiver les boutons. Le contrôle bas-niveau `db.has_active_subscription()` reste inchangé (vrai abonnement payant), donc la redirection post-login et l'anti-double-abonnement gardent leur comportement.

**Tech Stack:** Python, Dash 3.4, Dash Bootstrap Components, pytest.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `src.utils`, `src.pages._compte_shell`).
- Convention drapeau booléen : `os.getenv("NOM", "False").lower() == "true"` (cf. `DEVELOPMENT` dans `src/utils/__init__.py`).
- Drapeau lu via `from src.utils import TOUS_ABONNES` **dans le corps** des fonctions (lecture paresseuse → testable par `monkeypatch.setattr`).
- Quand `TOUS_ABONNES` est absent / `false`, comportement actuel strictement inchangé.
- Texte exact du bandeau (verbatim) : « Les fonctionnalités normalement accessibles contre un abonnement de 20 € HT par mois sont accessibles à tous et toutes en attendant la validation de mon dossier pour recevoir des paiements. »
- Tests lancés avec `uv run pytest`.
- Messages de commit en français, terminés par la ligne `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: Déblocage de l'accès via `TOUS_ABONNES`

**Files:**

- Modify: `src/utils/__init__.py` (ajouter la constante près de `DEVELOPMENT`, ligne ~33)
- Modify: `src/pages/_compte_shell.py:41-46` (`current_user_has_subscription`)
- Modify: `.template.env` (documenter la variable)
- Test: `tests/test_compte_shell.py`

**Interfaces:**

- Consumes: rien (première tâche).
- Produces:

  - `src.utils.TOUS_ABONNES: bool` — constante module, défaut `False`.
  - `src.pages._compte_shell.current_user_has_subscription() -> bool` — renvoie `True` si l'utilisateur est authentifié **et** `TOUS_ABONNES`, sinon le comportement DB existant ; toujours `False` si non authentifié.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/test_compte_shell.py` :

```python
from unittest.mock import patch


def _fake_user(authenticated: bool):
    user = type("U", (), {})()
    user.is_authenticated = authenticated
    user.id = 1
    return user


def test_has_subscription_true_for_authenticated_when_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    with patch("src.pages._compte_shell.current_user", _fake_user(True)):
        assert shell.current_user_has_subscription() is True


def test_has_subscription_false_for_anonymous_even_with_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    with patch("src.pages._compte_shell.current_user", _fake_user(False)):
        assert shell.current_user_has_subscription() is False


def test_has_subscription_uses_db_when_flag_off(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    with patch("src.pages._compte_shell.current_user", _fake_user(True)), patch(
        "src.subscriptions.db.has_active_subscription", return_value=False
    ) as mocked:
        assert shell.current_user_has_subscription() is False
        mocked.assert_called_once_with(1)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_compte_shell.py -v`
Expected: les 3 nouveaux tests ÉCHOUENT (`test_has_subscription_true_...` échoue car `current_user_has_subscription` ne consulte pas encore `TOUS_ABONNES` ; `monkeypatch.setattr("src.utils.TOUS_ABONNES", True)` réussit seulement si l'attribut existe — sinon `AttributeError`, ce qui confirme aussi qu'il faut créer la constante).

- [ ] **Step 3: Ajouter la constante dans `src/utils/__init__.py`**

Juste après la ligne `DEVELOPMENT = os.getenv("DEVELOPMENT", "False").lower() == "true"` (ligne ~33) :

```python
# Accès gratuit temporaire à toutes les fonctionnalités d'abonné, le temps que
# la plateforme de paiement Frisbii valide la réception de paiements.
TOUS_ABONNES = os.getenv("TOUS_ABONNES", "False").lower() == "true"
```

- [ ] **Step 4: Brancher le drapeau dans `current_user_has_subscription`**

Remplacer la fonction (`src/pages/_compte_shell.py:41-46`) par :

```python
def current_user_has_subscription() -> bool:
    from src.subscriptions import db
    from src.utils import TOUS_ABONNES

    if not current_user.is_authenticated:
        return False
    if TOUS_ABONNES:
        return True
    return db.has_active_subscription(current_user.id)
```

- [ ] **Step 5: Documenter la variable dans `.template.env`**

Ajouter une ligne (par ex. à la suite du bloc abonnement/Frisbii) :

```
TOUS_ABONNES=false   # true = ouvre gratuitement les fonctionnalités d'abonné à tout compte
```

- [ ] **Step 6: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_compte_shell.py -v`
Expected: les 8 tests PASSENT (5 existants + 3 nouveaux).

- [ ] **Step 7: Commit**

```bash
git add src/utils/__init__.py src/pages/_compte_shell.py .template.env tests/test_compte_shell.py
git commit -m "$(cat <<'EOF'
Ajoute le drapeau TOUS_ABONNES pour l'accès gratuit

Ouvre les fonctionnalités d'abonné à tout utilisateur connecté tant que
Frisbii n'a pas validé la réception de paiements.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Bandeau d'info et boutons « S'abonner » désactivés sur `/compte/abonnement`

**Files:**

- Modify: `src/pages/compte_abonnement.py` (`_plan_card` ~25-57, ajout `_tous_abonnes_banner`, `layout` ~198-221)
- Test: `tests/subscriptions/test_compte_abonnement.py`

**Interfaces:**

- Consumes: `src.utils.TOUS_ABONNES` (Task 1).
- Produces:

  - `compte_abonnement._tous_abonnes_banner()` — renvoie un `dbc.Alert` (color `info`) contenant le texte verbatim si `TOUS_ABONNES`, sinon `None`.
  - `_plan_card` rend un bouton désactivé (`className="btn btn-secondary disabled"`, `disabled=True`) quand `TOUS_ABONNES`, sinon le bouton primaire actuel.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/subscriptions/test_compte_abonnement.py` :

```python
def test_subscribe_buttons_disabled_when_tous_abonnes(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    from src.pages import compte_abonnement

    text = str(compte_abonnement._plan_cards(trial_for=lambda key: 2))
    assert "btn-secondary disabled" in text
    assert "btn-primary" not in text


def test_subscribe_buttons_active_when_flag_off(monkeypatch):
    monkeypatch.setenv("FRISBII_PLAN_SIMPLE", "plan_simple")
    monkeypatch.setenv("FRISBII_PLAN_SOUTIEN", "plan_soutien")
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    from src.pages import compte_abonnement

    text = str(compte_abonnement._plan_cards(trial_for=lambda key: 2))
    assert "btn-primary" in text


def test_banner_present_when_tous_abonnes(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    from src.pages import compte_abonnement

    text = str(compte_abonnement._tous_abonnes_banner())
    assert "accessibles à tous et toutes" in text


def test_banner_absent_when_flag_off(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    from src.pages import compte_abonnement

    assert compte_abonnement._tous_abonnes_banner() is None
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: les 4 nouveaux tests ÉCHOUENT (`_tous_abonnes_banner` n'existe pas → `AttributeError` ; le bouton reste `btn-primary`).

- [ ] **Step 3: Désactiver le bouton dans `_plan_card`**

Dans `src/pages/compte_abonnement.py::_plan_card`, remplacer le bloc `html.Button("S'abonner", ...)` (lignes ~48-50) par une lecture du drapeau. Ajouter en tête de fonction puis le bouton conditionnel :

```python
def _plan_card(meta: dict, trial: int | None, trial_used: bool):
    from src.utils import TOUS_ABONNES

    if trial_used:
```

et remplacer le `html.Button(...)` par :

```python
                        html.Button(
                            "S'abonner",
                            type="submit",
                            className=(
                                "btn btn-secondary disabled"
                                if TOUS_ABONNES
                                else "btn btn-primary"
                            ),
                            disabled=TOUS_ABONNES,
                        ),
```

- [ ] **Step 4: Ajouter le helper `_tous_abonnes_banner`**

Dans `src/pages/compte_abonnement.py`, ajouter (par ex. juste avant `def layout`) :

```python
def _tous_abonnes_banner():
    from src.utils import TOUS_ABONNES

    if not TOUS_ABONNES:
        return None
    return dbc.Alert(
        "Les fonctionnalités normalement accessibles contre un abonnement de "
        "20 € HT par mois sont accessibles à tous et toutes en attendant la "
        "validation de mon dossier pour recevoir des paiements.",
        color="info",
    )
```

- [ ] **Step 5: Insérer le bandeau dans `layout`**

Dans `src/pages/compte_abonnement.py::layout`, remplacer la construction de `body` (ligne ~214) par une version qui place le bandeau en tête quand présent :

```python
    body = [html.H2("Abonnement", className="mb-4")]
    banner = _tous_abonnes_banner()
    if banner is not None:
        body.append(banner)
    body.extend(_feedback(query))
    if has_access and row is not None:
        body.append(_active_view(row))
    else:
        body.extend([_plan_cards(trial_used=trial_used), _explainer()])
```

- [ ] **Step 6: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_compte_abonnement.py -v`
Expected: tous les tests PASSENT (4 existants + 4 nouveaux).

- [ ] **Step 7: Lancer la suite des tests d'abonnement et du shell**

Run: `uv run pytest tests/subscriptions/ tests/test_compte_shell.py -v`
Expected: PASS (aucune régression).

- [ ] **Step 8: Commit**

```bash
git add src/pages/compte_abonnement.py tests/subscriptions/test_compte_abonnement.py
git commit -m "$(cat <<'EOF'
Bandeau TOUS_ABONNES et boutons S'abonner désactivés

Affiche un bandeau d'info sur /compte/abonnement et grise les boutons
S'abonner quand l'accès gratuit pour tous est activé.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage :**

- Drapeau d'env `TOUS_ABONNES` → Task 1, Steps 3 & 5.
- Accès aux fonctionnalités d'abonné pour tout connecté → Task 1, Step 4 (`current_user_has_subscription`, qui pilote menu + `account_guard`).
- Bandeau sur `/compte/abonnement` → Task 2, Steps 4-5.
- Boutons « S'abonner » désactivés et gris → Task 2, Step 3.
- `db.has_active_subscription` inchangé / redirection post-login inchangée → aucun changement (couvert par l'architecture ; non gating ailleurs vérifié dans la spec).
- Comportement inchangé si drapeau off → tests `_flag_off` dans les deux tâches.

**Placeholder scan :** aucun TODO/TBD ; tout le code et toutes les commandes sont explicites.

**Type consistency :** `current_user_has_subscription() -> bool`, `_tous_abonnes_banner() -> dbc.Alert | None`, `TOUS_ABONNES: bool` utilisés de façon cohérente entre tâches et tests.
