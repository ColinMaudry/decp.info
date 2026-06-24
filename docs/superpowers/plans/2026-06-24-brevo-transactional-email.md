# Migration des emails transactionnels vers Brevo — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le transport SMTP/Flask-Mail des emails transactionnels (vérification d'adresse, reset de mot de passe) par l'API Brevo et ses templates hébergés, sans changer l'interface publique du mailer.

**Architecture:** `src/auth/mailer.py` est réécrit pour construire un client `Brevo` (SDK v5) et envoyer via `client.transactional_emails.send_transac_email(template_id, params, sender, to)`. Les deux fonctions publiques (`send_verification_email`, `send_reset_email`) gardent leur signature, donc `src/auth/routes.py` n'est pas touché. Seul l'appel d'init dans `setup.py` change (`init_mailer()` sans `app`).

**Tech Stack:** Python, Flask, SDK `brevo-python` v5 (`5.0.0rc1`), pytest, monkeypatch.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex: `from src.utils import logger`).
- SDK épinglé strictement : `brevo-python==5.0.0rc1` (pré-release ; un specifier qui pointe exactement une rc autorise pip à l'installer sans `--pre` global).
- API v5 vérifiée par introspection :
  - `from brevo import Brevo, SendTransacEmailRequestSender, SendTransacEmailRequestToItem`
  - `from brevo.core.api_error import ApiError`
  - `Brevo(api_key: str, headers: dict | None = None)`
  - `client.transactional_emails.send_transac_email(template_id=int, params=dict, sender=SendTransacEmailRequestSender, to=[SendTransacEmailRequestToItem], headers=dict|None)`
  - `SendTransacEmailRequestSender(email=..., name=...)`, `SendTransacEmailRequestToItem(email=..., name=...)`
- Tests unitaires hermétiques : aucun appel réseau (le client est monkeypatché).
- Commits fréquents, un par tâche.
- Lancer les tests avec `uv run pytest` (pas `source .venv/bin/activate`).
- Le hook pre-commit (prettier/ruff) peut reformater des fichiers : si un commit échoue pour cause de reformatage, `git add` les fichiers modifiés et recommitter.

---

## File Structure

| Fichier                                 | Responsabilité                             | Action                                    |
| --------------------------------------- | ------------------------------------------ | ----------------------------------------- |
| `pyproject.toml`                        | Dépendances                                | Modifier (swap flask-mail → brevo-python) |
| `src/auth/mailer.py`                    | Envoi des emails transactionnels via Brevo | Réécrire                                  |
| `src/auth/setup.py`                     | Initialisation du blueprint auth           | Modifier (1 ligne)                        |
| `tests/auth/test_mailer.py`             | Tests unitaires du mailer (mock)           | Réécrire                                  |
| `tests/auth/test_mailer_integration.py` | Test d'intégration sandbox optionnel       | Créer                                     |
| `.template.env`                         | Documentation des variables d'env          | Modifier                                  |
| `src/auth/templates/emails/*`           | Anciens templates Jinja                    | Supprimer                                 |

---

### Task 1: Basculer la dépendance vers le SDK Brevo

**Files:**

- Modify: `pyproject.toml:25`

**Interfaces:**

- Consumes: (rien)
- Produces: le paquet `brevo` importable dans l'environnement.

- [ ] **Step 1: Remplacer la dépendance dans `pyproject.toml`**

Remplacer la ligne 25 :

```toml
"flask-mail",
```

par :

```toml
"brevo-python==5.0.0rc1",
```

- [ ] **Step 2: Réinstaller les dépendances du projet**

Run: `uv pip install -e . --group=dev`
Expected: installation réussie, `brevo-python 5.0.0rc1` installé, `flask-mail` retiré.

- [ ] **Step 3: Vérifier que le SDK s'importe avec les symboles attendus**

Run:

```bash
uv run python -c "from brevo import Brevo, SendTransacEmailRequestSender, SendTransacEmailRequestToItem; from brevo.core.api_error import ApiError; print('brevo v5 OK')"
```

Expected: affiche `brevo v5 OK` sans erreur.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build(brevo): remplacer flask-mail par brevo-python v5 (#87)"
```

---

### Task 2: Réécrire le mailer pour utiliser l'API Brevo (TDD)

**Files:**

- Test: `tests/auth/test_mailer.py` (réécriture complète)
- Modify: `src/auth/mailer.py` (réécriture complète)
- Modify: `src/auth/setup.py:39`

**Interfaces:**

- Consumes: `brevo.Brevo`, `brevo.SendTransacEmailRequestSender`, `brevo.SendTransacEmailRequestToItem`, `brevo.core.api_error.ApiError`, `src.utils.logger`.
- Produces (interface publique, inchangée pour `routes.py`) :
  - `init_mailer() -> None`
  - `send_verification_email(email: str, token: str) -> None`
  - `send_reset_email(email: str, token: str) -> None`
- Variables d'env lues : `BREVO_API_KEY`, `BREVO_SANDBOX`, `BREVO_TEMPLATE_VERIFY_ID`, `BREVO_TEMPLATE_RESET_ID`, `MAIL_FROM`, `MAIL_FROM_NAME`, `APP_BASE_URL`.

- [ ] **Step 1: Réécrire le test du mailer (mock du client Brevo)**

Remplacer **tout** le contenu de `tests/auth/test_mailer.py` par :

```python
import pytest

from src.auth import mailer


class _FakeTransac:
    def __init__(self):
        self.calls = []

    def send_transac_email(self, **kwargs):
        self.calls.append(kwargs)


class _FakeClient:
    def __init__(self):
        self.transactional_emails = _FakeTransac()


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(mailer, "_client", client)
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("BREVO_TEMPLATE_VERIFY_ID", "11")
    monkeypatch.setenv("BREVO_TEMPLATE_RESET_ID", "22")
    monkeypatch.setenv("MAIL_FROM", "noreply@decp.info")
    monkeypatch.setenv("MAIL_FROM_NAME", "decp.info")
    return client


def test_send_verification_email(fake_client):
    mailer.send_verification_email("a@b.c", "TOKEN123")
    calls = fake_client.transactional_emails.calls
    assert len(calls) == 1
    call = calls[0]
    assert call["template_id"] == 11
    assert call["to"][0].email == "a@b.c"
    assert call["sender"].email == "noreply@decp.info"
    assert "/auth/verify-email?token=TOKEN123" in call["params"]["link"]


def test_send_reset_email(fake_client):
    mailer.send_reset_email("a@b.c", "RESET456")
    calls = fake_client.transactional_emails.calls
    assert len(calls) == 1
    call = calls[0]
    assert call["template_id"] == 22
    assert "reinitialiser-mot-de-passe?token=RESET456" in call["params"]["link"]


def test_init_mailer_builds_client(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.delenv("BREVO_SANDBOX", raising=False)
    monkeypatch.setattr(mailer, "_client", None)
    mailer.init_mailer()
    assert mailer._client is not None


def test_send_without_init_raises(monkeypatch):
    monkeypatch.setattr(mailer, "_client", None)
    monkeypatch.setenv("BREVO_TEMPLATE_VERIFY_ID", "11")
    with pytest.raises(AssertionError):
        mailer.send_verification_email("a@b.c", "TOKEN123")
```

- [ ] **Step 2: Lancer les tests pour les voir échouer**

Run: `uv run pytest tests/auth/test_mailer.py -v`
Expected: FAIL — l'ancien `mailer.py` importe `flask_mail` (désinstallé en Task 1) et n'expose pas `_client` ; erreurs d'import / d'attribut.

- [ ] **Step 3: Réécrire `src/auth/mailer.py`**

Remplacer **tout** le contenu de `src/auth/mailer.py` par :

```python
import os

from brevo import (
    Brevo,
    SendTransacEmailRequestSender,
    SendTransacEmailRequestToItem,
)
from brevo.core.api_error import ApiError

from src.utils import logger

_client: Brevo | None = None


def init_mailer() -> None:
    """Construit le client Brevo à partir des variables d'environnement."""
    global _client
    api_key = os.getenv("BREVO_API_KEY", "")
    sandbox = os.getenv("BREVO_SANDBOX", "").lower() == "true"
    headers = {"X-Sib-Sandbox": "drop"} if sandbox else None
    _client = Brevo(api_key=api_key, headers=headers)


def _base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8050").rstrip("/")


def _sender() -> SendTransacEmailRequestSender:
    return SendTransacEmailRequestSender(
        email=os.getenv("MAIL_FROM", "noreply@decp.info"),
        name=os.getenv("MAIL_FROM_NAME", "decp.info"),
    )


def _template_id(env_var: str) -> int:
    raw = os.getenv(env_var, "")
    if not raw:
        raise RuntimeError(f"{env_var} non défini (template Brevo)")
    return int(raw)


def _send_template(template_id: int, recipient: str, params: dict) -> None:
    assert _client is not None, "Mailer non initialisé (init_mailer() non appelé)"
    try:
        _client.transactional_emails.send_transac_email(
            template_id=template_id,
            params=params,
            sender=_sender(),
            to=[SendTransacEmailRequestToItem(email=recipient)],
        )
    except ApiError:
        logger.exception(
            "Échec d'envoi Brevo (template %s) à %s", template_id, recipient
        )
        raise


def send_verification_email(email: str, token: str) -> None:
    link = f"{_base_url()}/auth/verify-email?token={token}"
    _send_template(
        _template_id("BREVO_TEMPLATE_VERIFY_ID"), email, {"link": link}
    )


def send_reset_email(email: str, token: str) -> None:
    link = f"{_base_url()}/reinitialiser-mot-de-passe?token={token}"
    _send_template(
        _template_id("BREVO_TEMPLATE_RESET_ID"), email, {"link": link}
    )
```

- [ ] **Step 4: Mettre à jour l'appel d'init dans `setup.py`**

Dans `src/auth/setup.py`, ligne 39, remplacer :

```python
    mailer.init_mailer(app)
```

par :

```python
    mailer.init_mailer()
```

- [ ] **Step 5: Lancer les tests du mailer pour les voir passer**

Run: `uv run pytest tests/auth/test_mailer.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Lancer toute la suite auth pour vérifier l'absence de régression**

Run: `uv run pytest tests/auth/ -v`
Expected: PASS (aucune dépendance résiduelle à flask-mail ; `routes.py` inchangé fonctionne).

- [ ] **Step 7: Commit**

```bash
git add src/auth/mailer.py src/auth/setup.py tests/auth/test_mailer.py
git commit -m "feat(brevo): envoyer les emails transactionnels via l'API Brevo v5 (#87)"
```

---

### Task 3: Nettoyer la configuration et les templates Jinja

**Files:**

- Modify: `.template.env`
- Delete: `src/auth/templates/emails/verify_email.html`, `verify_email.txt`, `reset_password.html`, `reset_password.txt` (tout le dossier `src/auth/templates/`)

**Interfaces:**

- Consumes: (rien — `mailer.py` n'utilise plus de templates locaux après Task 2)
- Produces: (rien)

- [ ] **Step 1: Vérifier que les variables legacy ne sont pas utilisées ailleurs**

Run: `grep -rn "SENDER_SERVER_DOMAIN\|LOGIN_EMAIL\|FROM_EMAIL\|TO_EMAIL" . --include=*.py`
Expected: aucun résultat. (Si des résultats apparaissent hors `.template.env`, NE PAS supprimer ces variables et le signaler.)

- [ ] **Step 2: Mettre à jour `.template.env`**

Dans la section SMTP de `.template.env`, supprimer les lignes :

```
SENDER_SERVER_DOMAIN="mail.example.com" # serveur SMTP
LOGIN_EMAIL="connect@example.fr"        # adresse utilisée pour se connecter au serveur SMTP
FROM_EMAIL="from@example.com"           # adresse d'envoi des emails (From)
TO_EMAIL="to@example.com"               # adresse de destination des emails (To)
# SMTP pour envoi d'emails (vérification email, reset mot de passe)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=True
MAIL_SUPPRESS_SEND=  # laisser vide pour hériter de DEVELOPMENT ; mettre false pour forcer l'envoi en mode dev
```

et les remplacer par :

```
# Brevo — envoi des emails transactionnels (vérification email, reset mot de passe)
BREVO_API_KEY=                       # clé API transactionnelle Brevo
BREVO_TEMPLATE_VERIFY_ID=            # ID numérique du template "vérification d'adresse"
BREVO_TEMPLATE_RESET_ID=            # ID numérique du template "réinitialisation mot de passe"
BREVO_SANDBOX=                       # mettre "true" pour valider sans délivrer (dev / intégration)
MAIL_FROM=noreply@decp.info          # expéditeur (doit être un expéditeur vérifié dans Brevo)
MAIL_FROM_NAME=decp.info             # nom d'expéditeur
```

Conserver la variable `APP_BASE_URL` si elle est déjà présente ailleurs dans le fichier ; sinon l'ajouter :

```
APP_BASE_URL=http://localhost:8050   # base des liens dans les emails
```

- [ ] **Step 3: Supprimer les templates Jinja d'email devenus inutiles**

Run: `git rm -r src/auth/templates`
Expected: les 4 fichiers `emails/*.{html,txt}` sont supprimés.

- [ ] **Step 4: Vérifier qu'aucun code ne référence encore ces templates**

Run: `grep -rn "verify_email\|reset_password\|render_template\|jinja_loader\|MAIL_SUPPRESS_SEND\|flask_mail" src/ tests/ --include=*.py`
Expected: aucun résultat.

- [ ] **Step 5: Relancer la suite auth complète**

Run: `uv run pytest tests/auth/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .template.env src/auth/templates
git commit -m "chore(brevo): retirer la config SMTP et les templates Jinja d'email (#87)"
```

---

### Task 4: Test d'intégration sandbox optionnel

**Files:**

- Create: `tests/auth/test_mailer_integration.py`

**Interfaces:**

- Consumes: interface publique `mailer.init_mailer()`, `mailer.send_verification_email(email, token)`.
- Produces: un test `@pytest.mark.integration` skippé sauf si `BREVO_API_KEY` est défini.

- [ ] **Step 1: Créer le test d'intégration**

Créer `tests/auth/test_mailer_integration.py` :

```python
import os

import pytest

from src.auth import mailer

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("BREVO_API_KEY"),
    reason="BREVO_API_KEY absent — test d'intégration Brevo ignoré",
)
def test_send_verification_email_sandbox(monkeypatch):
    # Force le mode sandbox : Brevo valide la requête sans délivrer.
    monkeypatch.setenv("BREVO_SANDBOX", "true")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    mailer.init_mailer()
    # Ne doit pas lever : l'API Brevo accepte la requête en sandbox.
    mailer.send_verification_email(
        os.getenv("MAIL_FROM", "noreply@decp.info"), "INTEGRATION_TOKEN"
    )
```

- [ ] **Step 2: Enregistrer le marker `integration` (si absent)**

Vérifier la présence du marker dans `pyproject.toml` :

Run: `grep -n "integration" pyproject.toml`

Si aucune section `[tool.pytest.ini_options]` avec `markers` ne déclare `integration`, l'ajouter. Exemple à insérer/compléter dans `pyproject.toml` :

```toml
[tool.pytest.ini_options]
markers = [
    "integration: tests touchant des services externes (Brevo) ; skippés par défaut en CI",
]
```

(Si la section existe déjà, n'ajouter que la ligne `integration: ...` dans la liste `markers` existante, sans dupliquer la section.)

- [ ] **Step 3: Vérifier que le test est bien collecté puis skippé sans clé**

Run: `uv run pytest tests/auth/test_mailer_integration.py -v`
Expected: 1 test SKIPPED (motif « BREVO_API_KEY absent »), aucun appel réseau.

- [ ] **Step 4: Vérifier que la suite par défaut reste verte**

Run: `uv run pytest tests/auth/ -v`
Expected: PASS, avec le test d'intégration SKIPPED.

- [ ] **Step 5: Commit**

```bash
git add tests/auth/test_mailer_integration.py pyproject.toml
git commit -m "test(brevo): test d'intégration sandbox optionnel (#87)"
```

---

## Notes de vérification finale (manuel, hors CI)

Avant de merger, vérification manuelle réelle :

1. Renseigner `.env` avec `BREVO_API_KEY`, `BREVO_TEMPLATE_VERIFY_ID`, `BREVO_TEMPLATE_RESET_ID`, `MAIL_FROM` (expéditeur vérifié Brevo) et `BREVO_SANDBOX=true`.
2. Lancer `python run.py`, déclencher une inscription, vérifier dans les logs Brevo (tableau de bord) que la requête est reçue (sandbox = acceptée, non délivrée).
3. Passer `BREVO_SANDBOX=` (vide), refaire une inscription avec une vraie adresse, confirmer la réception et que `{{ params.link }}` est correctement substitué dans le template.
4. Confirmer la valeur du header sandbox (`X-Sib-Sandbox: drop`) si le comportement diffère de l'attendu.
