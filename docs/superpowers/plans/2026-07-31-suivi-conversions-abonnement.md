# Suivi des conversions et consolidation Matomo — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Émettre trois événements Matomo (compte créé, essai démarré, abonnement payant) après avoir unifié la configuration Matomo du projet sur une convention unique.

**Architecture :** Un helper `tracking_enabled()` dans `src/utils/matomo.py` devient l'interrupteur unique des quatre points d'émission. Les deux événements attribuables partent du navigateur via un paramètre de query string posé sur une redirection ; le troisième part du serveur depuis le webhook Frisbii, dans un thread daemon.

**Tech Stack :** Python 3, Flask, Dash, httpx, SQLite, pytest.

Spec de référence : `docs/superpowers/specs/2026-07-31-suivi-conversions-abonnement-design.md`.

## Global Constraints

- Convention d'environnement unique : `MATOMO_URL`, `MATOMO_SITE_ID`, `MATOMO_TRACKING_ENABLED`. Les variables `MATOMO_DOMAIN`, `MATOMO_ID_SITE`, `MATOMO_TOKEN` et `MATOMO_BASE_URL` sont supprimées du code et des gabarits.
- Aucun `token_auth` n'est envoyé à Matomo. Les POST utilisent `data=`, jamais `params=`.
- Aucun émetteur ne lève jamais d'exception : une panne Matomo ne doit casser ni une requête utilisateur, ni un webhook.
- `pyproject.toml:56` pinne `DEVELOPMENT=true` et `:67` pinne `MATOMO_TRACKING_ENABLED=false` pour toute la suite. Tout test attendant une émission doit lever **les deux** verrous.
- Commandes de test : `uv run pytest <chemin>` (l'activation du venv dans un shell ne suffit pas ici). **Chaque tâche se limite aux chemins que ses propres étapes nomment** — son fichier de test, plus le répertoire voisin quand une étape le demande explicitement comme contrôle de non-régression. La suite complète (`uv run pytest` sans chemin) n'est lancée qu'à la tâche 11. Ne jamais élargir de sa propre initiative : un échec ailleurs dans la suite n'appartient pas à la tâche en cours.
- Baseline de référence sur cette branche avant toute modification : **948 passés, 21 désélectionnés**. Tout écart doit être expliqué par la tâche en cours.
- Avant tout `git add`, exécuter `pre-commit` : prettier reformate les `.md`/`.js` et ruff les `.py`. Si un hook modifie un fichier, le ré-ajouter avant de commiter.
- Les clés de plan valides sont `simple` et `soutien` (`src/subscriptions/plans.py:8-23`).

---

## File Structure

| Fichier                       | Responsabilité                                              | Tâches |
| ----------------------------- | ----------------------------------------------------------- | ------ |
| `src/utils/matomo.py`         | Garde unique, configuration, fragment `<script>` navigateur | 1, 2   |
| `src/api/tracking.py`         | Suivi de l'API — consomme la garde                          | 3      |
| `src/utils/tracking.py`       | Émetteurs serveur : recherches, MCP, conversions            | 4, 6   |
| `.template.env`               | Gabarit d'environnement                                     | 5      |
| `src/subscriptions/db.py`     | Émission de `subscription_active` sur transition de statut  | 7      |
| `src/subscriptions/routes.py` | Discriminant `souscription` sur l'`accept_url`              | 8      |
| `src/auth/routes.py`          | Discriminant `compte_cree` sur les deux inscriptions        | 9, 10  |
| `src/assets/goals.js`         | Émission navigateur des deux événements attribuables        | 11     |

---

### Task 1 : garde unique et avertissement de configuration

**Files:**

- Modify: `src/utils/matomo.py` (ajouts en tête de module)
- Test: `tests/test_matomo.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  - `tracking_enabled() -> bool`
  - `matomo_config() -> tuple[str, str] | None` — `(url, site_id)`, ou `None` si l'une des deux variables manque
  - `avertir_si_config_incomplete() -> None`

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à la fin de `tests/test_matomo.py` :

```python
def test_tracking_enabled_faux_en_development(monkeypatch):
    """Protection de test.colibre.fr : DEVELOPMENT prime sur le drapeau."""
    from src.utils.matomo import tracking_enabled

    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    assert tracking_enabled() is False


def test_tracking_enabled_faux_sans_drapeau(monkeypatch):
    from src.utils.matomo import tracking_enabled

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.delenv("MATOMO_TRACKING_ENABLED", raising=False)
    assert tracking_enabled() is False


def test_tracking_enabled_vrai_hors_development(monkeypatch):
    from src.utils.matomo import tracking_enabled

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    assert tracking_enabled() is True


def test_matomo_config_none_si_incomplete(monkeypatch):
    from src.utils.matomo import matomo_config

    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.delenv("MATOMO_SITE_ID", raising=False)
    assert matomo_config() is None


def test_matomo_config_retourne_le_couple(monkeypatch):
    from src.utils.matomo import matomo_config

    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
    assert matomo_config() == ("https://matomo.example/matomo.php", "42")


def test_avertissement_si_active_mais_incomplet(monkeypatch, caplog):
    import logging

    from src.utils.matomo import avertir_si_config_incomplete

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.delenv("MATOMO_URL", raising=False)
    monkeypatch.setenv("MATOMO_SITE_ID", "14")

    with caplog.at_level(logging.WARNING, logger="colibre"):
        avertir_si_config_incomplete()

    assert "MATOMO_URL" in caplog.text
    assert "MATOMO_SITE_ID" not in caplog.text


def test_pas_d_avertissement_si_suivi_desactive(monkeypatch, caplog):
    import logging

    from src.utils.matomo import avertir_si_config_incomplete

    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.delenv("MATOMO_URL", raising=False)

    with caplog.at_level(logging.WARNING, logger="colibre"):
        avertir_si_config_incomplete()

    assert caplog.text == ""
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_matomo.py -v`
Expected: FAIL — `ImportError: cannot import name 'tracking_enabled' from 'src.utils.matomo'`

- [ ] **Step 3 : implémenter**

Dans `src/utils/matomo.py`, remplacer l'en-tête `import os` par :

```python
import json
import os

from src.utils import logger
```

Puis insérer, avant `def build_tracker_script()` :

```python
def tracking_enabled() -> bool:
    """Interrupteur unique de tout le suivi Matomo du projet.

    `DEVELOPMENT` prime sur `MATOMO_TRACKING_ENABLED` : c'est ce qui empêche
    test.colibre.fr et les instances de développement d'alimenter le Matomo de
    production, sans dépendre d'un `.env` correctement rempli sur le serveur.

    La lecture se fait à l'appel et non via la constante `DEVELOPMENT` de
    `src/utils/__init__.py:33`, figée au premier import : `pyproject.toml:56`
    pinne `DEVELOPMENT=true` pour toute la suite de tests, donc une garde
    reposant sur la constante rendrait intestable le chemin « traqueur émis
    quand il est activé » — précisément celui que l'incident #128 avait laissé
    passer.
    """
    if os.getenv("DEVELOPMENT", "False").lower() == "true":
        return False
    return os.getenv("MATOMO_TRACKING_ENABLED", "false").lower() == "true"


def matomo_config() -> tuple[str, str] | None:
    """(url de la Tracking API, id du site), ou None si l'un des deux manque."""
    url = os.getenv("MATOMO_URL")
    site_id = os.getenv("MATOMO_SITE_ID")
    if not url or not site_id:
        return None
    return url, site_id


def avertir_si_config_incomplete() -> None:
    """Rend bruyante une configuration Matomo incomplète.

    Le suivi de l'API est resté muet en production pendant des mois parce que
    `MATOMO_URL`/`MATOMO_SITE_ID` manquaient au `.env` et que le code se
    contentait d'un retour anticipé silencieux.
    """
    if not tracking_enabled() or matomo_config() is not None:
        return
    manquantes = [n for n in ("MATOMO_URL", "MATOMO_SITE_ID") if not os.getenv(n)]
    logger.warning(
        "Matomo : suivi activé mais configuration incomplète, variable(s) "
        "manquante(s) : %s. Aucun événement ne sera émis.",
        ", ".join(manquantes),
    )


avertir_si_config_incomplete()
```

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_matomo.py -v`
Expected: PASS (les tests préexistants du fichier restent verts, `build_tracker_script` n'ayant pas encore changé)

- [ ] **Step 5 : commiter**

```bash
pre-commit run --files src/utils/matomo.py tests/test_matomo.py
git add src/utils/matomo.py tests/test_matomo.py
git commit -m "Ajoute la garde unique tracking_enabled et l'avertissement de config Matomo"
```

---

### Task 2 : le fragment navigateur cesse de coder le serveur en dur

**Files:**

- Modify: `src/utils/matomo.py:18-40` (corps de `build_tracker_script`)
- Test: `tests/test_matomo.py`

**Interfaces:**

- Consumes: `tracking_enabled()`, `matomo_config()` (tâche 1).
- Produces: `build_tracker_script() -> str` — signature inchangée, comportement étendu.

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à `tests/test_matomo.py` :

```python
def test_script_vide_si_config_incomplete(monkeypatch):
    """La garde passe mais l'URL manque : pas de script muet à moitié valide."""
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.delenv("MATOMO_URL", raising=False)
    monkeypatch.setenv("MATOMO_SITE_ID", "14")
    assert build_tracker_script() == ""


def test_script_utilise_les_variables_d_environnement(monkeypatch):
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")

    script = build_tracker_script()

    assert "https://matomo.example/" in script
    assert '"42"' in script
    # Les anciennes constantes ont disparu du fragment.
    assert "analytics.maudry.com" not in script
    assert "'14'" not in script


def test_script_vide_en_development(monkeypatch):
    """Régression : test.colibre.fr ne doit rien émettre vers le site prod."""
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
    assert build_tracker_script() == ""
```

Modifier aussi les tests existants du fichier qui attendent un script non vide, en levant les deux verrous. Dans `test_active_rend_le_script_trackpageview` (`tests/test_matomo.py:22`), ajouter avant l'appel :

```python
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
```

Et dans `test_page_dash_emet_le_script_matomo_quand_actif` (`tests/test_matomo.py:38`), remplacer la construction de l'environnement du sous-processus par :

```python
    env = {
        **os.environ,
        "MATOMO_TRACKING_ENABLED": "true",
        "DEVELOPMENT": "false",
        "MATOMO_URL": "https://matomo.example/matomo.php",
        "MATOMO_SITE_ID": "42",
    }
```

Deux autres fichiers attendent un traqueur non vide et cassent pour la même raison. Dans `tests/test_seo.py:130` (`test_matomo_present_sur_une_page_seo_ssr_quand_active`) et `tests/test_linkedin_consent.py:174` (`test_page_seo_conserve_matomo`), ajouter à la suite du `monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")` déjà présent :

```python
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
```

Ces deux pages sont rendues côté serveur et appellent `build_tracker_script()` par requête via le `context_processor` de `src/seo/routes.py:65` : `monkeypatch.setenv` y est donc effectif, contrairement au cas Dash qui exige un sous-processus.

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_matomo.py -v`
Expected: FAIL — `test_script_utilise_les_variables_d_environnement` échoue sur `assert "https://matomo.example/" in script` (le fragment porte encore `analytics.maudry.com`)

- [ ] **Step 3 : implémenter**

Remplacer entièrement le corps de `build_tracker_script` dans `src/utils/matomo.py` :

```python
def build_tracker_script() -> str:
    """Bloc <script> du traqueur Matomo, ou chaîne vide si désactivé."""
    if not tracking_enabled():
        return ""
    config = matomo_config()
    if config is None:
        return ""
    url, site_id = config
    # `MATOMO_URL` pointe la Tracking API (…/matomo.php) ; le loader JS veut la
    # racine, à laquelle il recolle lui-même `matomo.php` et `matomo.js`.
    base = url[: -len("matomo.php")] if url.endswith("matomo.php") else url
    if not base.endswith("/"):
        base += "/"
    # json.dumps plutôt qu'une interpolation : une apostrophe ou un guillemet
    # dans la variable produit un littéral JS valide au lieu de casser le script.
    return """<script type="application/javascript">
            var _paq = window._paq = window._paq || [];
            /* tracker methods like "setCustomDimension" should be called before "trackPageView" */
            _paq.push(['trackPageView']);
            _paq.push(['enableLinkTracking']);
            (function() {
                var u=__BASE__;
                _paq.push(['setTrackerUrl', u+'matomo.php']);
                _paq.push(['setSiteId', __SITE_ID__]);
                var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0];
                g.async=true; g.src=u+'matomo.js'; s.parentNode.insertBefore(g,s);
            })();
        </script>""".replace("__BASE__", json.dumps(base)).replace(
        "__SITE_ID__", json.dumps(site_id)
    )
```

Mettre à jour le docstring de module (`src/utils/matomo.py:9-12`) : la mention « Gardé derrière `MATOMO_TRACKING_ENABLED` » devient « Gardé derrière `tracking_enabled()`, qui combine `DEVELOPMENT` et `MATOMO_TRACKING_ENABLED` ».

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_matomo.py -v`
Expected: PASS — tous les tests du fichier, y compris le sous-processus

- [ ] **Step 5 : commiter**

```bash
pre-commit run --files src/utils/matomo.py tests/test_matomo.py
git add src/utils/matomo.py tests/test_matomo.py
git commit -m "Dérive le traqueur Matomo de l'environnement au lieu de constantes"
```

---

### Task 3 : le suivi de l'API consomme la garde partagée

**Files:**

- Modify: `src/api/tracking.py:47-67`
- Test: `tests/api/test_tracking.py`

**Interfaces:**

- Consumes: `tracking_enabled()`, `matomo_config()` (tâche 1).
- Produces: `enqueue_matomo_event(...)` — signature inchangée.

- [ ] **Step 1 : écrire le test qui échoue**

Ajouter à `tests/api/test_tracking.py` :

```python
def test_matomo_muet_en_development(monkeypatch, api_client, valid_token_header):
    """Régression : une instance de test ne doit pas alimenter le Matomo prod."""
    from src.api import tracking

    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")

    envois = []
    monkeypatch.setattr(tracking, "_post_matomo", lambda **kw: envois.append(kw))

    tracking.start_worker(":memory:")
    try:
        tracking.enqueue_matomo_event(1, "/v1/marches", "", 200, "pytest")
        tracking.flush()
    finally:
        tracking.stop_worker()

    assert envois == []
```

Adapter aussi `test_matomo_disabled_skips_call` et le test voisin (`tests/api/test_tracking.py:41,58`) en ajoutant `monkeypatch.setenv("DEVELOPMENT", "false")` là où une émission est attendue.

- [ ] **Step 2 : lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/api/test_tracking.py -v`
Expected: FAIL — `assert envois == []` échoue, un envoi a été enfilé malgré `DEVELOPMENT=true`

- [ ] **Step 3 : implémenter**

Dans `src/api/tracking.py`, ajouter à la liste d'imports :

```python
from src.utils.matomo import matomo_config, tracking_enabled
```

Puis remplacer les lignes 56-67 (le commentaire et les deux gardes) par :

```python
    # Garde commune aux quatre points d'émission Matomo du projet
    # (src/utils/matomo.py) : elle combine DEVELOPMENT et
    # MATOMO_TRACKING_ENABLED. La couper éteint toute l'analytique du site,
    # pas seulement celle de l'API.
    if not tracking_enabled():
        return
    config = matomo_config()
    if config is None:
        return
    url, site_id = config
```

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/api/test_tracking.py -v`
Expected: PASS

- [ ] **Step 5 : commiter**

```bash
pre-commit run --files src/api/tracking.py tests/api/test_tracking.py
git add src/api/tracking.py tests/api/test_tracking.py
git commit -m "Branche le suivi de l'API sur la garde Matomo partagée"
```

---

### Task 4 : migration des émetteurs recherche et MCP

**Files:**

- Modify: `src/utils/tracking.py` (réécriture complète)
- Test: `tests/mcp/test_tracking.py`

**Interfaces:**

- Consumes: `tracking_enabled()`, `matomo_config()` (tâche 1).
- Produces:

  - `_envoyer(params: dict) -> None` — POST best-effort, ajoute `idsite`, ne lève jamais
  - `_horodatage() -> dict` — `rand`, `apiv`, `h`, `m`, `s` (réutilisé par la tâche 6)
  - `track_search(query, category) -> None` — signature inchangée
  - `track_mcp_tool(tool_name: str, query: str | None = None) -> None` — signature inchangée

- [ ] **Step 1 : réécrire les tests**

Remplacer entièrement `tests/mcp/test_tracking.py` :

```python
import src.utils.tracking as tracking


def _activer(monkeypatch):
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "1")


def test_track_mcp_tool_sends_action_and_dimension(monkeypatch):
    captured = {}

    def fake_post(url, data):
        captured["url"] = url
        captured["data"] = data

    _activer(monkeypatch)
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_mcp_tool("rechercher_marches", query="informatique")

    assert captured["url"] == "https://matomo.example/matomo.php"
    assert captured["data"]["idsite"] == "1"
    assert captured["data"]["action_name"] == "MCP / rechercher_marches"
    assert captured["data"]["dimension1"] == "rechercher_marches"
    assert captured["data"]["search"] == "informatique"


def test_aucun_token_auth_envoye(monkeypatch):
    """Le token n'est requis que pour cip/cdt/géoloc, et fuitait dans les logs."""
    captured = {}

    _activer(monkeypatch)
    monkeypatch.setenv("MATOMO_TOKEN", "ne-doit-pas-etre-envoye")
    monkeypatch.setattr(tracking, "post", lambda url, data: captured.update(data))

    tracking.track_mcp_tool("stats_acheteur")

    assert "token_auth" not in captured


def test_track_mcp_tool_muet_en_development(monkeypatch):
    called = False

    def fake_post(url, data):
        nonlocal called
        called = True

    _activer(monkeypatch)
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_mcp_tool("stats_acheteur")

    assert called is False


def test_track_mcp_tool_muet_si_config_incomplete(monkeypatch):
    called = False

    def fake_post(url, data):
        nonlocal called
        called = True

    _activer(monkeypatch)
    monkeypatch.delenv("MATOMO_URL", raising=False)
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_mcp_tool("stats_acheteur")

    assert called is False


def test_track_mcp_tool_n_exceptionne_pas(monkeypatch):
    """Une panne Matomo ne doit jamais casser l'appel de l'outil."""

    def fake_post(url, data):
        raise RuntimeError("matomo est tombé")

    _activer(monkeypatch)
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_mcp_tool("stats_acheteur")  # ne lève pas


def test_track_search_ignore_les_requetes_courtes(monkeypatch):
    called = False

    def fake_post(url, data):
        nonlocal called
        called = True

    _activer(monkeypatch)
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_search("abc", "home_page_search")

    assert called is False


def test_track_search_envoie_la_requete(monkeypatch):
    captured = {}

    _activer(monkeypatch)
    monkeypatch.setattr(tracking, "post", lambda url, data: captured.update(data))

    tracking.track_search("informatique", "home_page_search")

    assert captured["search"] == "informatique"
    assert captured["action_name"] == "search"
    assert captured["search_cat"] == "home_page_search"
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/mcp/test_tracking.py -v`
Expected: FAIL — `fake_post` est appelé avec `params=` et non `data=`, donc `TypeError: fake_post() got an unexpected keyword argument 'params'`

- [ ] **Step 3 : implémenter**

Remplacer entièrement `src/utils/tracking.py` :

```python
import uuid
from time import localtime

from httpx import post

from src.utils.matomo import matomo_config, tracking_enabled


def _envoyer(params: dict) -> None:
    """POST best-effort vers la Tracking API Matomo. Ne lève jamais.

    `data=` et non `params=` : la charge utile passe dans le corps de la requête
    plutôt que dans la query string, où elle atterrirait dans les journaux
    d'accès du serveur Matomo.

    Aucun `token_auth` : l'endpoint matomo.php est public par construction —
    c'est celui qu'appelle le matomo.js de chaque visiteur. Le token n'est
    requis que pour les paramètres privilégiés (cip, cdt au-delà de ~24 h,
    country/region/city/lat/long), qu'aucun émetteur du projet n'utilise.
    """
    if not tracking_enabled():
        return
    config = matomo_config()
    if config is None:
        return
    url, site_id = config
    try:
        post(url=url, data={**params, "idsite": site_id})
    except Exception:  # noqa: BLE001
        pass


def _horodatage() -> dict:
    maintenant = localtime()
    return {
        "rand": uuid.uuid4().hex,
        "apiv": "1",
        "h": maintenant.tm_hour,
        "m": maintenant.tm_min,
        "s": maintenant.tm_sec,
    }


def track_search(query, category):
    """Enregistre une recherche dans Matomo (best-effort)."""
    if len(query) < 4:
        return
    _envoyer(
        {
            "rec": "1",
            "url": "https://colibre.fr",
            "action_name": "search" if category == "home_page_search" else "filter",
            "search_cat": category,
            "search": query,
            **_horodatage(),
        }
    )


def track_mcp_tool(tool_name: str, query: str | None = None) -> None:
    """Enregistre un appel d'outil MCP dans Matomo (best-effort).

    `action_name="MCP / <tool>"`, `dimension1=<tool>`. Si l'outil porte une
    requête texte, elle est envoyée en `search`. Nécessite un Custom Dimension
    slot 1 (scope Action) configuré côté Matomo — sinon `dimension1` est ignoré.
    """
    params = {
        "rec": "1",
        "url": "https://colibre.fr/_mcp",
        "action_name": f"MCP / {tool_name}",
        "dimension1": tool_name,
        **_horodatage(),
    }
    if query:
        params["search"] = query
        params["search_cat"] = "mcp"
    _envoyer(params)
```

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/mcp/test_tracking.py -v`
Expected: PASS

- [ ] **Step 5 : vérifier qu'aucun appelant ne casse**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS — `src/utils/search.py:22` appelle `track_search`, sa signature est inchangée

- [ ] **Step 6 : commiter**

```bash
pre-commit run --files src/utils/tracking.py tests/mcp/test_tracking.py
git add src/utils/tracking.py tests/mcp/test_tracking.py
git commit -m "Migre les émetteurs recherche et MCP sur la convention Matomo unique"
```

---

### Task 5 : nettoyage du gabarit d'environnement

**Files:**

- Modify: `.template.env:45-48`
- Modify: `CLAUDE.md` (section Environment)

**Interfaces:**

- Consumes: rien.
- Produces: rien (fichiers de configuration et documentation).

- [ ] **Step 1 : vérifier qu'aucune de ces variables n'est encore lue**

Run:

```bash
grep -rn "MATOMO_DOMAIN\|MATOMO_ID_SITE\|MATOMO_TOKEN\|MATOMO_BASE_URL" --include=*.py src/ tests/
```

Expected: aucune sortie. Si une occurrence subsiste, elle relève d'une tâche précédente non terminée — la corriger avant de continuer.

- [ ] **Step 2 : supprimer les variables mortes du gabarit**

Dans `.template.env`, supprimer les quatre lignes 45-48 :

```
# Matomo
MATOMO_ID_SITE=
MATOMO_BASE_URL=
MATOMO_TOKEN=
```

Les lignes 63-65 (`MATOMO_URL`, `MATOMO_SITE_ID`, `MATOMO_TRACKING_ENABLED`) sont conservées telles quelles. Y ajouter au-dessus le commentaire :

```
# Matomo. Les trois variables sont requises ensemble : si MATOMO_TRACKING_ENABLED
# vaut true et que l'une des deux autres manque, l'app le signale au démarrage.
# DEVELOPMENT=true neutralise tout le suivi, quelle que soit leur valeur.
```

- [ ] **Step 3 : documenter la garde dans CLAUDE.md**

Dans la section `### Environment` de `CLAUDE.md`, sous la ligne `DEVELOPMENT=true enables debug logging…`, ajouter :

```markdown
- `DEVELOPMENT=true` désactive aussi tout le suivi Matomo (`tracking_enabled()`
  dans `src/utils/matomo.py`), pour que les instances de test n'alimentent pas
  le site de production
```

- [ ] **Step 4 : vérifier que le gabarit reste chargeable**

Run: `uv run pytest tests/test_matomo.py -v`
Expected: PASS

- [ ] **Step 5 : commiter**

```bash
pre-commit run --files .template.env CLAUDE.md
git add .template.env CLAUDE.md
git commit -m "Retire les variables Matomo mortes du gabarit d'environnement"
```

---

### Task 6 : émetteur des conversions d'abonnement

**Files:**

- Modify: `src/utils/tracking.py` (ajout en fin de fichier)
- Test: `tests/test_tracking_goals.py` (créer)

**Interfaces:**

- Consumes: `_envoyer(params)` (tâche 4).
- Produces:
  - `_envoyer_async(params: dict) -> threading.Thread` — lance `_envoyer` en thread daemon et retourne le thread
  - `track_subscription_goal(action: str, plan: str | None = None, revenue: float | None = None) -> None`

Aucun émetteur serveur n'est écrit pour `account_created` : cet événement est purement navigateur (tâche 11).

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `tests/test_tracking_goals.py` :

```python
import src.utils.tracking as tracking


def _capturer(monkeypatch):
    """Remplace l'envoi asynchrone par une capture synchrone."""
    envois = []
    monkeypatch.setattr(tracking, "_envoyer_async", lambda params: envois.append(params))
    return envois


def test_evenement_abonnement_payant(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    envois = _capturer(monkeypatch)

    tracking.track_subscription_goal("subscription_active", "simple", 20)

    assert len(envois) == 1
    params = envois[0]
    assert params["e_c"] == "Abonnement"
    assert params["e_a"] == "subscription_active"
    assert params["e_n"] == "simple"
    assert params["e_v"] == 20
    assert "token_auth" not in params


def test_evenement_sans_revenu(monkeypatch):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    envois = _capturer(monkeypatch)

    tracking.track_subscription_goal("subscription_trial", "soutien")

    assert "e_v" not in envois[0]
    assert envois[0]["e_n"] == "soutien"


def test_muet_sous_tous_abonnes(monkeypatch):
    """Sous TOUS_ABONNES il n'y a pas d'abonnement réel à comptabiliser."""
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    envois = _capturer(monkeypatch)

    tracking.track_subscription_goal("subscription_active", "simple", 20)

    assert envois == []


def test_envoyer_async_appelle_envoyer(monkeypatch):
    recu = {}
    monkeypatch.setattr(tracking, "_envoyer", lambda params: recu.update(params))

    thread = tracking._envoyer_async({"e_a": "subscription_active"})
    thread.join(timeout=5.0)

    assert recu["e_a"] == "subscription_active"


def test_n_exceptionne_pas_si_envoi_echoue(monkeypatch):
    """Une panne Matomo ne doit pas faire répondre 502 au webhook Frisbii."""
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)

    def fake_post(url, data):
        raise RuntimeError("matomo est tombé")

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "1")
    monkeypatch.setattr(tracking, "post", fake_post)

    tracking.track_subscription_goal("subscription_active", "simple", 20)
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_tracking_goals.py -v`
Expected: FAIL — `AttributeError: module 'src.utils.tracking' has no attribute '_envoyer_async'`

- [ ] **Step 3 : implémenter**

Ajouter `import threading` en tête de `src/utils/tracking.py`, puis à la fin du fichier :

```python
def _envoyer_async(params: dict) -> threading.Thread:
    """Envoie en tâche de fond et retourne le thread (pour que les tests joignent).

    Un POST synchrone retarderait de plusieurs secondes la réponse 200 au
    webhook Frisbii, qui pourrait alors considérer la livraison en échec et
    réessayer — donc émettre l'événement en double.
    """
    thread = threading.Thread(target=_envoyer, args=(params,), daemon=True)
    thread.start()
    return thread


def track_subscription_goal(
    action: str, plan: str | None = None, revenue: float | None = None
) -> None:
    """Événement de conversion d'abonnement (`subscription_trial`/`_active`).

    Sous TOUS_ABONNES, l'accès est offert et la souscription payante est
    désactivée : aucun essai ni abonnement ne doit être comptabilisé. L'import
    est fait dans le corps de la fonction, comme dans src/subscriptions/db.py:347 —
    la constante est figée à l'import de src.utils, donc seul l'import différé
    rend effectif le monkeypatch.setattr("src.utils.TOUS_ABONNES", …) des tests.
    """
    from src.utils import TOUS_ABONNES

    if TOUS_ABONNES:
        return
    params = {
        "rec": "1",
        "url": "https://colibre.fr/compte/abonnement",
        "e_c": "Abonnement",
        "e_a": action,
        **_horodatage(),
    }
    if plan:
        params["e_n"] = plan
    if revenue is not None:
        params["e_v"] = revenue
    _envoyer_async(params)
```

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_tracking_goals.py -v`
Expected: PASS

- [ ] **Step 5 : commiter**

```bash
pre-commit run --files src/utils/tracking.py tests/test_tracking_goals.py
git add src/utils/tracking.py tests/test_tracking_goals.py
git commit -m "Ajoute l'émetteur des conversions d'abonnement, muet sous TOUS_ABONNES"
```

---

### Task 7 : `subscription_active` sur la transition de statut

**Files:**

- Modify: `src/subscriptions/db.py:265-287`
- Test: `tests/subscriptions/test_db.py`

**Interfaces:**

- Consumes: `track_subscription_goal(action, plan, revenue)` (tâche 6).
- Produces: `update_from_webhook(...)` — signature inchangée, effet de bord ajouté.

- [ ] **Step 1 : écrire les tests qui échouent**

Ajouter à `tests/subscriptions/test_db.py`. Les fixtures et helpers de création d'abonnement du fichier sont réutilisés — si le fichier expose déjà un helper de création, l'utiliser plutôt que `create_pending` en direct.

```python
def test_evenement_emis_sur_trial_vers_active(users_db_path, monkeypatch):
    from src.subscriptions import db

    appels = []
    monkeypatch.setattr(
        db.tracking,
        "track_subscription_goal",
        lambda action, plan=None, revenue=None: appels.append((action, plan, revenue)),
    )

    handle, sub_id = db.create_pending(1, "cust-1", "simple", 20)
    db.update_from_webhook(handle, "trial", "2026-08-05T00:00:00Z")
    appels.clear()

    db.update_from_webhook(handle, "active", "2026-09-05T00:00:00Z")

    assert appels == [("subscription_active", "simple", 20)]


def test_evenement_emis_sur_pending_vers_active(users_db_path, monkeypatch):
    """Souscription directe sans essai (no_trial) : même événement."""
    from src.subscriptions import db

    appels = []
    monkeypatch.setattr(
        db.tracking,
        "track_subscription_goal",
        lambda action, plan=None, revenue=None: appels.append((action, plan, revenue)),
    )

    handle, _ = db.create_pending(2, "cust-2", "soutien", 50)
    db.update_from_webhook(handle, "active", "2026-09-05T00:00:00Z")

    assert appels == [("subscription_active", "soutien", 50)]


def test_pas_d_evenement_sur_redelivrance(users_db_path, monkeypatch):
    """Frisbii peut redélivrer un webhook : pas de double comptage."""
    from src.subscriptions import db

    appels = []
    monkeypatch.setattr(
        db.tracking,
        "track_subscription_goal",
        lambda action, plan=None, revenue=None: appels.append(action),
    )

    handle, _ = db.create_pending(3, "cust-3", "simple", 20)
    db.update_from_webhook(handle, "active", "2026-09-05T00:00:00Z")
    db.update_from_webhook(handle, "active", "2026-09-05T00:00:00Z")

    assert appels == ["subscription_active"]


def test_pas_d_evenement_sur_annulation(users_db_path, monkeypatch):
    from src.subscriptions import db

    appels = []
    monkeypatch.setattr(
        db.tracking,
        "track_subscription_goal",
        lambda action, plan=None, revenue=None: appels.append(action),
    )

    handle, _ = db.create_pending(4, "cust-4", "simple", 20)
    db.update_from_webhook(handle, "trial", "2026-08-05T00:00:00Z")
    db.update_from_webhook(handle, "cancelled", "2026-08-05T00:00:00Z")

    assert appels == []
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_db.py -v`
Expected: FAIL — `AttributeError: module 'src.subscriptions.db' has no attribute 'tracking'`

- [ ] **Step 3 : implémenter**

Ajouter aux imports de `src/subscriptions/db.py` :

```python
from src.utils import tracking
```

Le module entier est importé (et non la fonction) pour que `monkeypatch.setattr(db.tracking, …)` soit opérant.

Puis, dans `update_from_webhook`, compléter le bloc de la ligne 286 :

```python
    if prev["status"] != "active" and status == "active":
        freeze_votes_cursor(prev["user_id"])
        # Couvre trial → active (transformation d'un essai) et pending → active
        # (souscription directe d'un utilisateur ayant déjà consommé son essai).
        # La condition rend l'émission idempotente : un webhook redélivré trouve
        # prev["status"] déjà à "active" et ne repasse pas ici.
        tracking.track_subscription_goal(
            "subscription_active", prev["plan"], prev["prix_ht"]
        )
```

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_db.py -v`
Expected: PASS

- [ ] **Step 5 : commiter**

```bash
pre-commit run --files src/subscriptions/db.py tests/subscriptions/test_db.py
git add src/subscriptions/db.py tests/subscriptions/test_db.py
git commit -m "Émet subscription_active sur le passage en abonnement payant"
```

---

### Task 8 : discriminant `souscription` sur l'URL de retour du checkout

**Files:**

- Modify: `src/subscriptions/routes.py:30-78`
- Test: `tests/subscriptions/test_routes_accept_url.py` (créer)

**Interfaces:**

- Consumes: rien.
- Produces: l'`accept_url` transmise à `client.create_subscription_session` porte `&souscription=trial&plan=<clé>` quand un essai démarre.

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `tests/subscriptions/test_routes_accept_url.py` :

```python
"""L'URL de retour du checkout porte le discriminant qui déclenche l'événement
`subscription_trial` côté navigateur (src/assets/goals.js)."""

import pytest

from src.subscriptions import client, db, routes


@pytest.fixture
def capture_accept(monkeypatch):
    """Intercepte l'URL d'acceptation transmise à Frisbii."""
    captured = {}

    def fake_session(plan_handle, handle, accept_url, cancel_url, **kwargs):
        captured["accept_url"] = accept_url
        captured["no_trial"] = kwargs.get("no_trial")
        return "https://checkout.example/session"

    monkeypatch.setattr(client, "create_subscription_session", fake_session)
    monkeypatch.setattr(client, "update_customer", lambda handle, data: {})
    return captured


def test_discriminant_present_pour_un_premier_essai(
    logged_in_client, capture_accept, monkeypatch
):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    monkeypatch.setattr(db, "has_used_trial", lambda user_id: False)

    logged_in_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert "souscription=trial" in capture_accept["accept_url"]
    assert "plan=simple" in capture_accept["accept_url"]


def test_pas_de_discriminant_si_essai_deja_consomme(
    logged_in_client, capture_accept, monkeypatch
):
    """no_trial : souscription directe en payant, comptée côté serveur."""
    monkeypatch.setattr("src.utils.TOUS_ABONNES", False)
    monkeypatch.setattr(db, "has_used_trial", lambda user_id: True)

    logged_in_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert "souscription=" not in capture_accept["accept_url"]


def test_pas_de_discriminant_sous_tous_abonnes(
    logged_in_client, capture_accept, monkeypatch
):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    monkeypatch.setattr(db, "has_used_trial", lambda user_id: False)

    logged_in_client.post("/subscriptions/subscribe", data={"plan": "simple"})

    assert "souscription=" not in capture_accept["accept_url"]
```

La fixture `logged_in_client` est définie en `tests/subscriptions/conftest.py:96` et `users_db_path` en `:32` — aucune fixture à créer.

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/subscriptions/test_routes_accept_url.py -v`
Expected: FAIL — `assert "souscription=trial" in ...` échoue, l'URL vaut `…?paiement=succes`

- [ ] **Step 3 : implémenter**

Dans `src/subscriptions/routes.py`, fonction `subscribe`, remplacer la ligne 31 et les deux appels à `create_subscription_session` (lignes 58-78) par :

```python
        from src.utils import TOUS_ABONNES

        no_trial = db.has_used_trial(current_user.id)
        # Le discriminant déclenche l'événement `subscription_trial` côté
        # navigateur (src/assets/goals.js). Il est posé ici, où `no_trial` est
        # déjà connu : aucune lecture en base au retour, donc aucune course avec
        # le webhook Frisbii, qui peut ne pas être encore arrivé. Sous
        # TOUS_ABONNES, aucun abonnement réel n'est à comptabiliser.
        accept_url = f"{base}/compte/abonnement?paiement=succes"
        if not no_trial and not TOUS_ABONNES:
            accept_url += f"&souscription=trial&plan={plan_key}"
        cancel_url = f"{base}/compte/abonnement?paiement=annule"
```

puis, dans les deux branches, remplacer les deux littéraux d'URL par `accept_url` et `cancel_url` :

```python
        if customer_exists:
            url = client.create_subscription_session(
                plan_handle,
                sub_handle,
                accept_url,
                cancel_url,
                customer_handle=cust,
                no_trial=no_trial,
            )
        else:
            create_customer = {"handle": cust, **billing}
            if siret:
                create_customer["metadata"] = {"siret": siret}
            url = client.create_subscription_session(
                plan_handle,
                sub_handle,
                accept_url,
                cancel_url,
                create_customer=create_customer,
                no_trial=no_trial,
            )
```

`plan_key` provient de `request.form` mais a déjà été validé par `plans.resolve_handle` en ligne 17-19, qui retourne 400 pour toute clé inconnue : sa valeur est donc nécessairement `simple` ou `soutien` à ce stade.

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/subscriptions/test_routes_accept_url.py -v`
Expected: PASS

- [ ] **Step 5 : vérifier la non-régression du parcours d'abonnement**

Run: `uv run pytest tests/subscriptions/ -v`
Expected: PASS

- [ ] **Step 6 : commiter**

```bash
pre-commit run --files src/subscriptions/routes.py tests/subscriptions/test_routes_accept_url.py
git add src/subscriptions/routes.py tests/subscriptions/test_routes_accept_url.py
git commit -m "Pose le discriminant d'essai sur l'URL de retour du checkout"
```

---

### Task 9 : `compte_cree=email` sur l'inscription par formulaire

**Files:**

- Modify: `src/auth/routes.py:89`
- Test: `tests/auth/test_signup_tracking.py` (créer)

**Interfaces:**

- Consumes: rien.
- Produces: la redirection de `signup()` porte `&compte_cree=email` en cas de succès.

- [ ] **Step 1 : écrire les tests qui échouent**

Créer `tests/auth/test_signup_tracking.py` :

```python
"""Le paramètre `compte_cree` déclenche l'événement `account_created` côté
navigateur (src/assets/goals.js). Il n'est posé qu'en cas de succès complet."""

import pytest

from src.auth import mailer


@pytest.fixture
def _schema(users_db_path):
    from src.auth import db

    db.init_schema()


def test_redirection_porte_le_discriminant(client, _schema, monkeypatch):
    monkeypatch.setattr(mailer, "send_verification_email", lambda email, token: None)

    reponse = client.post(
        "/signup",
        data={
            "email": "nouveau@example.com",
            "password": "password12",
            "password_confirm": "password12",
        },
    )

    assert reponse.status_code == 302
    assert "compte_cree=email" in reponse.headers["Location"]
    assert "pending_verification=1" in reponse.headers["Location"]


def test_pas_de_discriminant_si_l_envoi_du_mail_echoue(client, _schema, monkeypatch):
    """routes.py:86 supprime le compte : il ne doit pas être comptabilisé."""

    def envoi_casse(email, token):
        raise RuntimeError("SMTP indisponible")

    monkeypatch.setattr(mailer, "send_verification_email", envoi_casse)

    reponse = client.post(
        "/signup",
        data={
            "email": "perdu@example.com",
            "password": "password12",
            "password_confirm": "password12",
        },
    )

    assert "compte_cree" not in reponse.headers["Location"]
    assert "error=email_send_failed" in reponse.headers["Location"]


def test_pas_de_discriminant_si_email_deja_pris(client, _schema, monkeypatch):
    from werkzeug.security import generate_password_hash

    from src.auth import db

    db.create_user("pris@example.com", generate_password_hash("password12"))

    reponse = client.post(
        "/signup",
        data={
            "email": "pris@example.com",
            "password": "password12",
            "password_confirm": "password12",
        },
    )

    assert "compte_cree" not in reponse.headers["Location"]
```

Les fixtures `client` et `users_db_path` sont définies en `tests/auth/conftest.py:32` et `:5` — aucune fixture à créer.

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/auth/test_signup_tracking.py -v`
Expected: FAIL — `assert "compte_cree=email" in ...`, la redirection vaut `/connexion?pending_verification=1`

- [ ] **Step 3 : implémenter**

Dans `src/auth/routes.py`, remplacer la ligne 89 :

```python
    # `compte_cree` déclenche l'événement `account_created` côté navigateur
    # (src/assets/goals.js). Posé ici et non sur `db.create_user` ligne 80 :
    # l'échec d'envoi du mail supprime le compte trois lignes plus haut, un
    # événement posé plus tôt compterait des comptes qui n'existent plus.
    return redirect("/connexion?pending_verification=1&compte_cree=email")
```

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/auth/test_signup_tracking.py -v`
Expected: PASS

- [ ] **Step 5 : commiter**

```bash
pre-commit run --files src/auth/routes.py tests/auth/test_signup_tracking.py
git add src/auth/routes.py tests/auth/test_signup_tracking.py
git commit -m "Marque la redirection d'inscription par formulaire"
```

---

### Task 10 : `compte_cree=linkedin` sur la création de compte OAuth

**Files:**

- Modify: `src/auth/routes.py:34-50` (`resolve_oauth_user`), `:309-313` (callback), ajout d'un helper
- Test: `tests/auth/test_oauth_resolve.py`

**Interfaces:**

- Consumes: rien.
- Produces:

  - `resolve_oauth_user(provider, subject, email, email_verified) -> tuple[User, bool]` — le booléen vaut `True` uniquement quand un compte vient d'être créé
  - `_avec_param(url: str, cle: str, valeur: str) -> str`

- [ ] **Step 1 : adapter les tests existants et en ajouter**

Dans `tests/auth/test_oauth_resolve.py`, dépaqueter les cinq appels et assertionner le booléen :

```python
def test_creates_new_user_when_unknown(users_db_path):
    db.init_schema()
    user, cree = resolve_oauth_user("linkedin", "sub-1", "new@example.com", True)
    assert cree is True
    assert isinstance(user, User)
    row = db.get_user_by_id(int(user.get_id()))
    assert row["email"] == "new@example.com"
    assert row["password_hash"] is None
    assert row["email_verified"] == 1
    assert db.get_oauth_identity("linkedin", "sub-1")["user_id"] == row["id"]


def test_links_to_existing_email_account(users_db_path):
    db.init_schema()
    uid = db.create_user("alice@example.com", generate_password_hash("password12"))
    db.set_email_verified(uid)

    user, cree = resolve_oauth_user("linkedin", "sub-2", "alice@example.com", True)
    # Rattachement d'une identité à un compte existant : pas une inscription.
    assert cree is False
    assert int(user.get_id()) == uid
    assert db.get_oauth_identity("linkedin", "sub-2")["user_id"] == uid
    # Le compte garde son mot de passe.
    assert db.get_user_by_id(uid)["password_hash"] is not None


def test_links_and_verifies_unverified_existing_account(users_db_path):
    db.init_schema()
    uid = db.create_user("bob@example.com", generate_password_hash("password12"))
    assert db.get_user_by_id(uid)["email_verified"] == 0

    _, cree = resolve_oauth_user("linkedin", "sub-3", "bob@example.com", True)
    assert cree is False
    assert db.get_user_by_id(uid)["email_verified"] == 1


def test_returns_same_user_for_known_identity(users_db_path):
    db.init_schema()
    first, cree_premier = resolve_oauth_user(
        "linkedin", "sub-4", "carol@example.com", True
    )
    second, cree_second = resolve_oauth_user(
        "linkedin", "sub-4", "carol@example.com", True
    )
    assert cree_premier is True
    # Une reconnexion n'est pas une inscription.
    assert cree_second is False
    assert first.get_id() == second.get_id()
    # Pas de doublon d'identité.
    count = (
        db.get_conn()
        .execute(
            "SELECT COUNT(*) FROM oauth_identities WHERE provider='linkedin' AND subject='sub-4'"
        )
        .fetchone()[0]
    )
    assert count == 1
```

Ajouter à la fin du même fichier les tests du helper d'URL :

```python
def test_avec_param_sur_url_sans_query():
    from src.auth.routes import _avec_param

    assert (
        _avec_param("/compte/abonnement", "compte_cree", "linkedin")
        == "/compte/abonnement?compte_cree=linkedin"
    )


def test_avec_param_preserve_la_query_existante():
    """La cible du callback OAuth est variable et peut déjà porter des paramètres."""
    from src.auth.routes import _avec_param

    resultat = _avec_param("/tableau?filtre=abc", "compte_cree", "linkedin")

    assert "filtre=abc" in resultat
    assert "compte_cree=linkedin" in resultat
    assert resultat.count("?") == 1
```

- [ ] **Step 2 : lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/auth/test_oauth_resolve.py -v`
Expected: FAIL — `TypeError: cannot unpack non-sequence User` sur le premier test

- [ ] **Step 3 : implémenter**

Dans `src/auth/routes.py`, ajouter aux imports :

```python
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
```

Remplacer `resolve_oauth_user` (lignes 34-50) :

```python
def resolve_oauth_user(
    provider: str, subject: str, email: str, email_verified: bool
) -> tuple[User, bool]:
    """Retourne (utilisateur, compte_vient_d_etre_cree).

    Le booléen distingue la seule branche qui crée réellement un compte. Sans
    lui, chaque connexion LinkedIn — et chaque rattachement d'identité à un
    compte existant — serait comptée comme une inscription.
    """
    identity = db.get_oauth_identity(provider, subject)
    if identity is not None:
        return User(db.get_user_by_id(identity["user_id"])), False

    row = db.get_user_by_email(email)
    if row is not None:
        db.link_oauth_identity(provider, subject, row["id"])
        if email_verified and not row["email_verified"]:
            db.set_email_verified(row["id"])
        return User(db.get_user_by_id(row["id"])), False

    user_id = db.create_oauth_user(email)
    db.link_oauth_identity(provider, subject, user_id)
    return User(db.get_user_by_id(user_id)), True


def _avec_param(url: str, cle: str, valeur: str) -> str:
    """Ajoute un paramètre à une URL, en préservant sa query string.

    Le callback OAuth redirige vers une cible variable (`safe_next`), qui peut
    déjà porter des paramètres : la concaténation naïve produirait deux `?`.
    """
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    params.append((cle, valeur))
    return urlunsplit(parts._replace(query=urlencode(params)))
```

Puis remplacer les lignes 309-313 (le callback) :

```python
    user, compte_cree = resolve_oauth_user(
        "linkedin", subject, email, bool(userinfo.get("email_verified"))
    )
    login_user(user, remember=True)
    dest = safe_next(oauth_next, fallback=_post_login_url(user.id))
    if compte_cree:
        # Déclenche `account_created` côté navigateur (src/assets/goals.js).
        dest = _avec_param(dest, "compte_cree", "linkedin")
    return redirect(dest)
```

- [ ] **Step 4 : lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/auth/test_oauth_resolve.py -v`
Expected: PASS

- [ ] **Step 5 : vérifier qu'aucun autre appelant ne casse**

Run: `uv run pytest tests/auth/ -v`
Expected: PASS. `resolve_oauth_user` n'a qu'un seul appelant applicatif (`src/auth/routes.py:309`) ; si un test échoue sur un dépaquetage manqué, corriger l'appel.

- [ ] **Step 6 : commiter**

```bash
pre-commit run --files src/auth/routes.py tests/auth/test_oauth_resolve.py
git add src/auth/routes.py tests/auth/test_oauth_resolve.py
git commit -m "Distingue la création de compte LinkedIn de la simple connexion"
```

---

### Task 11 : asset navigateur et validation finale

**Files:**

- Create: `src/assets/goals.js`
- Test: `tests/test_goals_asset.py` (créer)

**Interfaces:**

- Consumes: les paramètres `compte_cree` (tâches 9, 10) et `souscription`/`plan` (tâche 8).
- Produces: rien (code navigateur terminal).

- [ ] **Step 1 : écrire le test de l'asset**

Le fragment n'est pas testé par Selenium — le harnais `dash_duo` a des angles morts et l'asset est volontairement mince. Le test vérifie sa présence, son chargement par Dash et ses invariants de contenu.

Créer `tests/test_goals_asset.py` :

```python
"""L'asset est servi automatiquement par Dash (tout .js de src/assets/)."""

from pathlib import Path

ASSET = Path(__file__).resolve().parents[1] / "src" / "assets" / "goals.js"


def test_asset_present():
    assert ASSET.is_file()


def test_valide_les_valeurs_avant_emission():
    """Une valeur arbitraire de query string ne doit pas atterrir dans Matomo."""
    contenu = ASSET.read_text(encoding="utf-8")
    assert '"email"' in contenu and '"linkedin"' in contenu
    assert '"simple"' in contenu and '"soutien"' in contenu


def test_garde_sur_paq_et_nettoyage_de_l_url():
    contenu = ASSET.read_text(encoding="utf-8")
    assert "window._paq" in contenu
    # Sans replaceState, un F5 recompterait la conversion.
    assert "replaceState" in contenu


def test_emet_les_deux_evenements():
    contenu = ASSET.read_text(encoding="utf-8")
    assert "account_created" in contenu
    assert "subscription_trial" in contenu
```

- [ ] **Step 2 : lancer le test pour vérifier qu'il échoue**

Run: `uv run pytest tests/test_goals_asset.py -v`
Expected: FAIL — `assert ASSET.is_file()`

- [ ] **Step 3 : écrire l'asset**

Créer `src/assets/goals.js` :

```javascript
// Émission des deux événements de conversion attribuables à une campagne.
//
// Le serveur pose un paramètre sur l'URL de redirection (src/auth/routes.py
// pour l'inscription, src/subscriptions/routes.py pour le retour de checkout) ;
// ce script le consomme et le retire. Les événements alimentent deux objectifs
// Matomo configurés sur « Send an event » avec correspondance exacte sur
// l'Event Action.
//
// L'événement `subscription_active` n'est PAS émis ici : il vient du webhook
// Frisbii (src/subscriptions/db.py), sans navigateur, donc sans attribution.
//
// Chargé automatiquement par Dash sur ses pages (tout .js de src/assets/).
// /connexion et /compte/abonnement sont des pages Dash, donc aucune référence
// explicite n'est nécessaire dans le gabarit SEO SSR — contrairement à
// consent_pub.js.
(function () {
  var METHODES = ["email", "linkedin"];
  var PLANS = ["simple", "soutien"];

  function retirerParams(cles) {
    var url = new URL(window.location.href);
    var modifie = false;
    cles.forEach(function (cle) {
      if (url.searchParams.has(cle)) {
        url.searchParams.delete(cle);
        modifie = true;
      }
    });
    // Sans ce nettoyage, un rechargement (F5) recompterait la conversion.
    if (modifie) window.history.replaceState({}, "", url.toString());
  }

  function emettre() {
    // `_paq` est absent quand le traqueur est désactivé (tracking_enabled()
    // dans src/utils/matomo.py) : il n'y a alors rien à faire.
    if (!window._paq) return;

    var params = new URLSearchParams(window.location.search);

    var methode = params.get("compte_cree");
    if (methode && METHODES.indexOf(methode) !== -1) {
      window._paq.push(["trackEvent", "Compte", "account_created", methode]);
      retirerParams(["compte_cree"]);
    }

    var plan = params.get("plan");
    if (params.get("souscription") === "trial" && PLANS.indexOf(plan) !== -1) {
      window._paq.push([
        "trackEvent",
        "Abonnement",
        "subscription_trial",
        plan,
      ]);
      retirerParams(["souscription", "plan"]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", emettre);
  } else {
    emettre();
  }
})();
```

- [ ] **Step 4 : lancer le test pour vérifier qu'il passe**

Run: `uv run pytest tests/test_goals_asset.py -v`
Expected: PASS

- [ ] **Step 5 : lancer la suite complète**

C'est la seule tâche qui lance la suite entière, une fois toutes les pièces en place.

Run: `uv run pytest`
Expected: PASS. Les quatre fichiers de test attendant un traqueur non vide ont été traités en tâche 2 (`tests/test_matomo.py`, `tests/test_seo.py`, `tests/test_linkedin_consent.py`). En cas d'échec ici, la cause la plus probable reste un test qui pose `MATOMO_TRACKING_ENABLED=true` sans lever `DEVELOPMENT` : le repérer avec `grep -rn "MATOMO_TRACKING_ENABLED.*true" tests/`.

- [ ] **Step 6 : commiter**

```bash
pre-commit run --files src/assets/goals.js tests/test_goals_asset.py
git add src/assets/goals.js tests/test_goals_asset.py
git commit -m "Émet les événements de conversion attribuables côté navigateur"
```

---

## Après l'implémentation — hors code

Ces étapes ne sont pas automatisables et conditionnent le fonctionnement réel de la mesure.

**1. Créer les trois objectifs dans l'interface Matomo.** Tous déclenchés par « Send an event », _Event Action_ en correspondance **exacte** :

| Nom               | Motif                 | Revenu                            |
| ----------------- | --------------------- | --------------------------------- |
| Compte créé       | `account_created`     | non                               |
| Essai démarré     | `subscription_trial`  | non                               |
| Abonnement payant | `subscription_active` | utiliser la valeur de l'événement |

**2. Mettre à jour le `.env` de production** — c'est le point de risque du déploiement. Sans ces deux lignes, les recherches et les appels d'outils MCP, qui fonctionnent aujourd'hui, s'éteignent :

```
MATOMO_URL=https://analytics.maudry.com/matomo.php
MATOMO_SITE_ID=14
```

Les clés `MATOMO_DOMAIN`, `MATOMO_ID_SITE`, `MATOMO_TOKEN` et `MATOMO_BASE_URL` peuvent être retirées dans la foulée.

**3. Révoquer `MATOMO_TOKEN` côté Matomo.** Il n'est plus lu par le code, mais il a été exposé en clair pendant la conception et donne accès à l'API de reporting.

**4. Vérifier après mise en ligne**, dans cet ordre :

1. le journal de démarrage ne contient pas l'avertissement `Matomo : suivi activé mais configuration incomplète` ;
2. le rapport _Visiteurs_ reçoit toujours des pages vues et le rapport _Recherches_ de nouvelles requêtes — c'est ce qui prouve que la migration n'a pas éteint l'existant ;
3. le suivi de l'API, muet jusqu'ici, produit enfin des hits.

Rien n'est validable sur test.colibre.fr : la garde `DEVELOPMENT` y interdit toute émission, par conception.
