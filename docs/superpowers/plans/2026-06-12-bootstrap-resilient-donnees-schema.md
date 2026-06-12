# Bootstrap résilient des données et du schéma — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre le démarrage de decp.info résilient aux ressources externes KO (parquet, schéma, stats), pour que l'API partagée ne tombe plus à cause d'un déploiement défaillant.

**Architecture:** Trois invariants. (1) Le DuckDB est réutilisé si la reconstruction échoue. (2) Le schéma suit la chaîne `URL → cache → RuntimeError`, le dernier schéma distant fonctionnel étant persisté localement. (3) Les chargements de pages au boot ne lèvent jamais sur une ressource externe KO. Une tâche préalable répare le baseline de tests laissé rouge par le merge de `main`.

**Tech Stack:** Python, Polars, DuckDB, httpx, flask-caching, pytest (+ monkeypatch).

**Spec de référence:** `docs/superpowers/specs/2026-06-12-bootstrap-resilient-donnees-schema-design.md`

---

## Structure des fichiers

| Fichier                               | Responsabilité                           | Action                        |
| ------------------------------------- | ---------------------------------------- | ----------------------------- |
| `tests/test_db.py`                    | Tests bootstrap DuckDB                   | Modifier (réparer + ajouter)  |
| `tests/conftest.py`                   | Setup déterministe des tests             | Modifier (seed schéma)        |
| `tests/schema.fixture.json`           | Schéma complet figé pour tests (offline) | Créer (commité)               |
| `tests/test_schema.py`                | Tests résolution schéma                  | Créer                         |
| `tests/test_page_loads.py`            | Tests chargements best-effort (C/D)      | Créer                         |
| `src/utils/data.py`                   | Résolution schéma                        | Modifier                      |
| `src/db.py`                           | Bootstrap DuckDB                         | Modifier (`_ensure_database`) |
| `src/utils/__init__.py`               | Helper date MAJ best-effort              | Modifier (ajout fonction)     |
| `src/pages/tableau.py`                | Date MAJ au niveau module                | Modifier                      |
| `src/figures.py`                      | `get_sources_tables`                     | Modifier                      |
| `.template.env`, `.env`, `.gitignore` | Config                                   | Modifier                      |

---

## Task 1 : Réparer le baseline de tests `test_db.py`

Le merge de `main` a changé `build_database(db_path)` (1 arg, parquet lu via env) et memoïsé `get_last_modified` (besoin du contexte d'app). Trois corrections pour repartir au vert. **Aucune logique applicative ne change ici.**

**Files:**

- Modify: `tests/test_db.py`

- [ ] **Step 1 : Corriger la fixture `built_db` (signature `build_database`)**

Dans `tests/test_db.py`, remplacer :

```python
    from src.db import build_database

    build_database(db_path, parquet_path)
    return db_path
```

par :

```python
    from src.db import build_database

    build_database(db_path)
    return db_path
```

(L'env `DATA_FILE_PARQUET_PATH` est déjà posé juste au-dessus dans la fixture.)

- [ ] **Step 2 : Corriger `test_concurrent_build_serialized`**

Ajouter `monkeypatch` à la signature et poser l'env du parquet ; corriger l'appel `build_database`.

Remplacer la ligne de signature :

```python
def test_concurrent_build_serialized(tmp_path):
```

par :

```python
def test_concurrent_build_serialized(tmp_path, monkeypatch):
```

Juste après `df.write_parquet(parquet_path)`, ajouter :

```python
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", str(parquet_path))
```

Et dans `worker()`, remplacer :

```python
                    if db.should_rebuild(db_path, parquet_path):
                        db.build_database(db_path, parquet_path)
```

par :

```python
                    if db.should_rebuild(db_path, parquet_path):
                        db.build_database(db_path)
```

- [ ] **Step 3 : Corriger les 2 tests prod de `should_rebuild` (memoïsation)**

`should_rebuild` non-dev appelle `get_last_modified`, memoïsé et inutilisable hors contexte d'app en test. On le monkeypatche pour tester la logique de comparaison de dates.

Dans `test_should_rebuild_prod_when_parquet_newer`, juste avant l'`assert`, ajouter :

```python
    monkeypatch.setattr("src.db.get_last_modified", lambda p: parquet.stat().st_mtime)
```

Dans `test_should_not_rebuild_prod_when_parquet_older`, juste avant l'`assert`, ajouter la même ligne :

```python
    monkeypatch.setattr("src.db.get_last_modified", lambda p: parquet.stat().st_mtime)
```

- [ ] **Step 4 : Lancer les tests, vérifier le vert**

Run: `rtk proxy python -m pytest tests/test_db.py -q`
Expected: tous PASS (plus aucun `TypeError`/`AttributeError`).

- [ ] **Step 5 : Commit**

```bash
git add tests/test_db.py
git commit -m "test: réparer le baseline test_db cassé par le merge (#78)"
```

---

## Task 2 : Schéma résilient — chaîne `URL → cache → RuntimeError`

Réécrire `get_data_schema` avec helpers robustes et persistance du dernier schéma distant fonctionnel. Supprimer `DATA_SCHEMA_LOCAL` au profit de `DATA_SCHEMA_CACHE`.

**Files:**

- Create: `tests/schema.fixture.json`, `tests/test_schema.py`
- Modify: `tests/conftest.py`, `src/utils/data.py`, `.template.env`, `.env`, `.gitignore`

- [ ] **Step 1 : Créer le fixture schéma complet (offline, déterministe)**

Run:

```bash
cp ../decp-processing/dist/schema.json tests/schema.fixture.json
test -s tests/schema.fixture.json && python -c "import json;assert 'fields' in json.load(open('tests/schema.fixture.json'))" && echo OK
```

Expected: `OK` (le fixture contient bien une clé `fields`).

- [ ] **Step 2 : Rendre la résolution du schéma déterministe en test (conftest)**

Dans `tests/conftest.py`, ajouter `import json` en tête (avec les autres imports) puis, au niveau module **avant** toute logique existante (juste après la ligne `_DB_PATH = Path(...)`), ajouter :

```python
# Schéma déterministe et hors-ligne pour les tests : on pointe le cache sur un
# fixture commité et on désactive la récupération distante.
_SCHEMA_FIXTURE = Path(os.path.abspath("tests/schema.fixture.json"))
os.environ["DATA_SCHEMA_CACHE"] = str(_SCHEMA_FIXTURE)
os.environ.pop("DATA_SCHEMA_PATH", None)
```

- [ ] **Step 3 : Écrire les tests schéma (échouent d'abord)**

Créer `tests/test_schema.py` :

```python
import json

import httpx
import pytest

from src.utils import data as data_mod

VALID = {"fields": [{"name": "uid", "title": "UID"}, {"name": "objet"}]}


class FakeResp:
    def __init__(self, payload, ok=True, bad_json=False):
        self._payload = payload
        self._ok = ok
        self._bad_json = bad_json

    def raise_for_status(self):
        if not self._ok:
            raise httpx.HTTPError("boom")
        return self

    def json(self):
        if self._bad_json:
            raise json.JSONDecodeError("bad", "", 0)
        return self._payload


def test_remote_ok_returns_schema_and_writes_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.cache.json"
    monkeypatch.setenv("DATA_SCHEMA_PATH", "http://x")
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    monkeypatch.setattr(data_mod, "get", lambda *a, **k: FakeResp(VALID))
    result = data_mod.get_data_schema()
    assert "uid" in result
    assert json.loads(cache.read_text())["fields"][0]["name"] == "uid"


def test_remote_http_error_falls_back_to_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.cache.json"
    cache.write_text(json.dumps(VALID))
    monkeypatch.setenv("DATA_SCHEMA_PATH", "http://x")
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    monkeypatch.setattr(data_mod, "get", lambda *a, **k: FakeResp(None, ok=False))
    assert "uid" in data_mod.get_data_schema()


def test_remote_malformed_falls_back_to_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.cache.json"
    cache.write_text(json.dumps(VALID))
    monkeypatch.setenv("DATA_SCHEMA_PATH", "http://x")
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    monkeypatch.setattr(data_mod, "get", lambda *a, **k: FakeResp({"nope": 1}))
    assert "uid" in data_mod.get_data_schema()


def test_no_url_uses_cache(tmp_path, monkeypatch):
    cache = tmp_path / "schema.cache.json"
    cache.write_text(json.dumps(VALID))
    monkeypatch.delenv("DATA_SCHEMA_PATH", raising=False)
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    assert "uid" in data_mod.get_data_schema()


def test_no_source_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_SCHEMA_PATH", raising=False)
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(tmp_path / "missing.json"))
    with pytest.raises(RuntimeError):
        data_mod.get_data_schema()


def test_cache_write_failure_is_non_blocking(tmp_path, monkeypatch):
    # parent inexistant => l'écriture du cache échoue, mais le schéma est renvoyé
    cache = tmp_path / "nodir" / "schema.cache.json"
    monkeypatch.setenv("DATA_SCHEMA_PATH", "http://x")
    monkeypatch.setenv("DATA_SCHEMA_CACHE", str(cache))
    monkeypatch.setattr(data_mod, "get", lambda *a, **k: FakeResp(VALID))
    assert "uid" in data_mod.get_data_schema()
```

- [ ] **Step 4 : Lancer les tests, vérifier l'échec**

Run: `rtk proxy python -m pytest tests/test_schema.py -q`
Expected: FAIL (les helpers/comportements n'existent pas encore ; `get_data_schema` actuel plante différemment).

- [ ] **Step 5 : Réécrire `get_data_schema` + helpers**

Dans `src/utils/data.py`, remplacer entièrement la fonction `get_data_schema` (actuellement lignes ~68-95) par :

```python
def _validate_schema(raw) -> dict | None:
    if isinstance(raw, dict) and isinstance(raw.get("fields"), list) and raw["fields"]:
        return raw
    return None


def _fetch_remote_schema(url: str | None) -> dict | None:
    if not url:
        return None
    try:
        raw = get(url, follow_redirects=True).raise_for_status().json()
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        logger.error(f"Schéma distant indisponible ({url}) : {e}")
        return None
    return _validate_schema(raw)


def _load_schema_file(path: str) -> dict | None:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Schéma local illisible ({path}) : {e}")
        return None
    return _validate_schema(raw)


def _persist_schema_cache(raw: dict, path: str) -> None:
    if not path:
        return
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(raw, f)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning(f"Écriture du cache schéma échouée ({path}) : {e}")


def get_data_schema() -> dict:
    cache_path = os.getenv("DATA_SCHEMA_CACHE", "./schema.cache.json")
    raw = _fetch_remote_schema(os.getenv("DATA_SCHEMA_PATH"))
    if raw is not None:
        _persist_schema_cache(raw, cache_path)
    else:
        raw = _load_schema_file(cache_path)
    if raw is None:
        raise RuntimeError("Aucun schéma disponible (ni distant ni cache).")
    return OrderedDict((c["name"], c) for c in raw["fields"])
```

Vérifier que les imports en tête de `src/utils/data.py` couvrent : `json`, `os`, `OrderedDict`, `httpx`, `get` (déjà présents : `from httpx import HTTPError, get`). `HTTPError` peut devenir inutilisé — voir Step 7.

- [ ] **Step 6 : Lancer les tests, vérifier le vert**

Run: `rtk proxy python -m pytest tests/test_schema.py -q`
Expected: 6 PASS.

- [ ] **Step 7 : Nettoyer imports + config + gitignore**

Dans `src/utils/data.py`, si `HTTPError` n'est plus utilisé, remplacer `from httpx import HTTPError, get` par `from httpx import get` (garder `import httpx`). Vérifier avec :

Run: `rtk proxy python -m ruff check src/utils/data.py`
Expected: pas d'erreur F401.

Dans `.gitignore`, ajouter sous la ligne `**/decp.duckdb` :

```
**/schema.cache.json
```

Dans `.template.env`, supprimer la ligne `DATA_SCHEMA_PATH_LOCAL=...` et ajouter :

```
DATA_SCHEMA_CACHE=./schema.cache.json
```

Dans `.env` (local, non versionné), supprimer la ligne `DATA_SCHEMA_LOCAL=...` et ajouter `DATA_SCHEMA_CACHE=./schema.cache.json`.

- [ ] **Step 8 : Commit**

```bash
git add tests/schema.fixture.json tests/test_schema.py tests/conftest.py src/utils/data.py .template.env .gitignore
git commit -m "feat: schéma résilient URL→cache + suppression DATA_SCHEMA_LOCAL (#78)"
```

---

## Task 3 : Bootstrap DuckDB résilient

Ajouter le garde-fou `try/except` dans `_ensure_database` : réutiliser le DuckDB existant si la reconstruction échoue ; ne lever qu'en cold start.

**Files:**

- Modify: `src/db.py:117-128` (`_ensure_database`)
- Test: `tests/test_db.py`

- [ ] **Step 1 : Écrire les tests (échouent d'abord)**

Ajouter à la fin de `tests/test_db.py` :

```python
def _raise(*args, **kwargs):
    raise RuntimeError("boom")


def test_ensure_database_reuses_db_when_should_rebuild_raises(tmp_path, monkeypatch):
    import src.db as db

    dbf = tmp_path / "decp.duckdb"
    dbf.write_bytes(b"existing")
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", "http://unreachable")
    monkeypatch.setattr(db, "should_rebuild", _raise)
    result = db._ensure_database()  # ne doit pas lever
    assert result == dbf
    assert dbf.read_bytes() == b"existing"


def test_ensure_database_reuses_db_when_build_raises(tmp_path, monkeypatch):
    import src.db as db

    dbf = tmp_path / "decp.duckdb"
    dbf.write_bytes(b"existing")
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", "http://unreachable")
    monkeypatch.setattr(db, "should_rebuild", lambda *a, **k: True)
    monkeypatch.setattr(db, "build_database", _raise)
    db._ensure_database()  # ne doit pas lever
    assert dbf.read_bytes() == b"existing"


def test_ensure_database_raises_on_cold_start(tmp_path, monkeypatch):
    import src.db as db

    dbf = tmp_path / "decp.duckdb"  # n'existe pas
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", "http://unreachable")
    monkeypatch.setattr(db, "should_rebuild", lambda *a, **k: True)
    monkeypatch.setattr(db, "build_database", _raise)
    with pytest.raises(RuntimeError):
        db._ensure_database()


def test_ensure_database_builds_when_needed(tmp_path, monkeypatch):
    import src.db as db

    dbf = tmp_path / "decp.duckdb"
    dbf.write_bytes(b"old")
    monkeypatch.setenv("DUCKDB_PATH", str(dbf))
    monkeypatch.setenv("DATA_FILE_PARQUET_PATH", "http://x")
    called = {}
    monkeypatch.setattr(db, "should_rebuild", lambda *a, **k: True)
    monkeypatch.setattr(db, "build_database", lambda p: called.setdefault("built", p))
    db._ensure_database()
    assert called.get("built") == dbf
```

Ajouter `import pytest` en tête de `tests/test_db.py` s'il n'y est pas déjà (il y est).

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `rtk proxy python -m pytest tests/test_db.py -q -k ensure_database`
Expected: FAIL (le `try/except` n'existe pas ; les exceptions remontent).

- [ ] **Step 3 : Implémenter le garde-fou**

Dans `src/db.py`, remplacer `_ensure_database` (lignes ~117-128) par :

```python
def _ensure_database() -> Path:
    db_path = Path(os.getenv("DUCKDB_PATH", "./decp.duckdb"))
    parquet_path = os.getenv("DATA_FILE_PARQUET_PATH", "")
    lock_path = db_path.with_suffix(".duckdb.lock")
    db_exists = db_path.exists()

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            if should_rebuild(db_path, parquet_path):
                build_database(db_path)
            else:
                logger.debug("Base de données déjà disponible et à jour.")
        except Exception as e:
            if db_exists:
                logger.error(
                    f"Bootstrap données KO ({e}). "
                    f"Réutilisation du DuckDB existant : {db_path}"
                )
            else:
                logger.critical("Aucune base DuckDB et reconstruction impossible.")
                raise
    return db_path
```

- [ ] **Step 4 : Lancer, vérifier le vert**

Run: `rtk proxy python -m pytest tests/test_db.py -q`
Expected: tous PASS (anciens + 4 nouveaux).

- [ ] **Step 5 : Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "feat: réutiliser le DuckDB existant si le bootstrap échoue (#78)"
```

---

## Task 4 : Chargements de pages best-effort (C + D)

`tableau.py` (date MAJ via `get_last_modified`) et `a-propos.py` (stats via `get_sources_tables`) chargent au boot et peuvent tuer le démarrage. On les rend best-effort.

**Files:**

- Create: `tests/test_page_loads.py`
- Modify: `src/utils/__init__.py`, `src/pages/tableau.py`, `src/figures.py`

- [ ] **Step 1 : Écrire les tests (échouent d'abord)**

Créer `tests/test_page_loads.py` :

```python
import os


def test_update_timestamp_falls_back_to_db_mtime(tmp_path, monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(u, "get_last_modified", boom)
    fb = tmp_path / "decp.duckdb"
    fb.write_bytes(b"x")
    assert get_data_update_timestamp("http://x", str(fb)) == os.path.getmtime(str(fb))


def test_update_timestamp_none_when_all_fail(monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(u, "get_last_modified", boom)
    assert get_data_update_timestamp("http://x", None) is None


def test_update_timestamp_nominal(monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    monkeypatch.setattr(u, "get_last_modified", lambda p: 123.0)
    assert get_data_update_timestamp("http://x", None) == 123.0


def test_sources_tables_none_path():
    from src.figures import get_sources_tables

    div = get_sources_tables(None)
    assert "indisponible" in str(div.children).lower()


def test_sources_tables_missing_file():
    from src.figures import get_sources_tables

    div = get_sources_tables("/does/not/exist.csv")
    assert "indisponible" in str(div.children).lower()


def test_sources_tables_valid_csv(tmp_path):
    from dash import dash_table

    from src.figures import get_sources_tables

    csv = tmp_path / "s.csv"
    csv.write_text(
        "nom,organisation,nb_marchés,nb_acheteurs,code,url,unique\n"
        "Source A,Org A,5,2,XA,http://a,1\n"
    )
    div = get_sources_tables(str(csv))
    assert isinstance(div.children, dash_table.DataTable)
```

- [ ] **Step 2 : Lancer, vérifier l'échec**

Run: `rtk proxy python -m pytest tests/test_page_loads.py -q`
Expected: FAIL (`get_data_update_timestamp` n'existe pas ; `get_sources_tables(None)` plante).

- [ ] **Step 3 : Ajouter `get_data_update_timestamp` dans `src/utils/__init__.py`**

À la fin de `src/utils/__init__.py`, ajouter :

```python
def get_data_update_timestamp(
    parquet_path: str, fallback_path: str | None = None
) -> float | None:
    """Date de MAJ des données, best-effort, sans jamais lever (usage au boot)."""
    try:
        return get_last_modified(parquet_path)
    except Exception as e:
        logger.warning(f"Date de mise à jour des données indisponible ({e})")
    if fallback_path:
        try:
            return os.path.getmtime(fallback_path)
        except OSError:
            pass
    return None
```

(`os` et `logger` sont déjà disponibles dans ce module.)

- [ ] **Step 4 : Utiliser le helper dans `tableau.py`**

Dans `src/pages/tableau.py`, remplacer l'import ligne 24 :

```python
from src.utils import get_last_modified, logger
```

par :

```python
from src.utils import get_data_update_timestamp, logger
```

Et remplacer les lignes 36-38 :

```python
update_date_timestamp = get_last_modified(os.getenv("DATA_FILE_PARQUET_PATH", ""))
update_date = datetime.fromtimestamp(update_date_timestamp).strftime("%d/%m/%Y")
update_date_iso = datetime.fromtimestamp(update_date_timestamp).isoformat()
```

par :

```python
update_date_timestamp = get_data_update_timestamp(
    os.getenv("DATA_FILE_PARQUET_PATH", ""),
    os.getenv("DUCKDB_PATH", "./decp.duckdb"),
)
if update_date_timestamp is not None:
    update_date = datetime.fromtimestamp(update_date_timestamp).strftime("%d/%m/%Y")
    update_date_iso = datetime.fromtimestamp(update_date_timestamp).isoformat()
else:
    update_date = "date inconnue"
    update_date_iso = ""
```

- [ ] **Step 5 : Élargir `get_sources_tables` dans `src/figures.py`**

Dans `src/figures.py` (`get_sources_tables`, ~lignes 122-125), remplacer :

```python
    try:
        dff = pl.read_csv(source_path)
    except (URLError, HTTPError):
        return html.Div("Erreur de connexion")
```

par :

```python
    try:
        if not source_path:
            raise ValueError("SOURCE_STATS_CSV_PATH non défini")
        dff = pl.read_csv(source_path)
    except Exception as e:
        logger.warning(f"Sources de données indisponibles ({e})")
        return html.Div("Sources de données momentanément indisponibles.")
```

Si `URLError`/`HTTPError` (import ligne 3 `from urllib.error import HTTPError, URLError`) ne sont plus utilisés ailleurs dans le fichier, supprimer cet import.

Run: `rtk proxy python -m ruff check src/figures.py`
Expected: pas d'erreur F401.

- [ ] **Step 6 : Lancer, vérifier le vert**

Run: `rtk proxy python -m pytest tests/test_page_loads.py -q`
Expected: 6 PASS.

- [ ] **Step 7 : Smoke test — l'import des modules modifiés ne casse pas**

Run: `rtk proxy python -c "import src.figures, src.pages.tableau; print('import OK')"`
Expected: `import OK`.
(NB : `a-propos.py` a un tiret, non importable par nom — son correctif `get_sources_tables` est couvert par les tests unitaires du Step 6 et la page sera validée par la suite Selenium au Step 8.)

- [ ] **Step 8 : Suite complète**

Run: `rtk proxy python -m pytest -q`
Expected: vert (hors tests Selenium nécessitant Chrome, à lancer si l'environnement le permet).

- [ ] **Step 9 : Commit**

```bash
git add tests/test_page_loads.py src/utils/__init__.py src/pages/tableau.py src/figures.py
git commit -m "feat: chargements de pages best-effort au boot (tableau, sources) (#78)"
```

---

## Notes d'exécution

- **Dev hors-ligne 1er run :** « cache seul » supprime le fallback in-repo. Au tout premier démarrage sur une machine sans `schema.cache.json` ni réseau, le boot lèvera `RuntimeError`. En conditions normales (URL OK une fois, ou cache déjà présent) c'est transparent. Les tests sont rendus déterministes via `tests/schema.fixture.json` (Task 2).
- **CHANGELOG :** penser à ajouter une entrée (résilience bootstrap données/schéma) avant de finaliser la PR #78, si le projet le tient à jour.
- **`get_last_modified` reste memoïsé** : non modifié ici ; le cache FileSystem est vidé à chaque boot (`rmtree` dans `app.py`), donc pas de last-modified périmé entre déploiements.
