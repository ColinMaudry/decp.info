# Tools MCP colibre (scope A de #111) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer 4 fonctions métier des DECP comme _tools_ MCP via le décorateur `@mcp_enabled` de Dash, sans authentification (le gate abonnement = scope B, séparé).

**Architecture:** Un package `src/mcp/` fin. `tools.py` contient les 4 fonctions décorées (surface MCP + tracking, aucun SQL) ; `queries.py` porte la logique données en réutilisant la couche existante (`src/db.py`, `src/api/filters.py`, `src/utils/search.py`) ; `serialization.py` convertit le Polars en JSON propre. Le serveur MCP est activé dans `src/app.py` via `enable_mcp` + `configure_mcp_server` qui coupe l'exposition des callbacks/layout/pages : seules les 4 fonctions sont exposées.

**Tech Stack:** Python 3, Dash 4.4 (`dash.mcp`), Polars, DuckDB, httpx (tracking Matomo), pytest.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `from src.db import ...`), jamais `db` ou `utils`.
- Périmètre = **scope A uniquement**. Aucune authentification, aucun gate abonnement dans ce plan.
- Sorties des tools = structures **JSON-sérialisables** : dates en ISO 8601 (`YYYY-MM-DD`), valeurs manquantes en `None`, montants numériques.
- Le serveur MCP n'expose **que** les fonctions `@mcp_enabled` (couper `include_callbacks/layout/pages/clientside`).
- Activation par variable d'env `DASH_MCP_ENABLED` (`"true"` pour activer), **off par défaut**. Ne pas activer en prod tant que le scope B n'est pas livré.
- Colonnes réelles de la table `decp` : `uid`, `objet`, `montant`, `dateNotification`, `codeCPV`, `acheteur_id`, `acheteur_nom`, `acheteur_departement_code`, `acheteur_departement_nom`, `acheteur_commune_nom`, `titulaire_id`, `titulaire_nom`, `titulaire_departement_nom`, `titulaire_commune_nom`. **Pas de colonne `annee`** → dériver l'année via `date_part('year', "dateNotification")`. **Pas de libellé CPV** dans les données.
- Avant chaque commit, le hook `pre-commit` (ruff + prettier) s'exécute et peut reformater : si des fichiers sont modifiés par le hook, refaire `git add` puis `git commit`.
- Lancer les tests avec `uv run pytest`. Chaque tâche ne lance QUE son fichier de test ; la suite complète (`uv run pytest` sans chemin) uniquement à la dernière tâche.

## File Structure

- Create: `src/mcp/__init__.py` — package vide.
- Create: `src/mcp/serialization.py` — `to_json_records(df) -> list[dict]`.
- Create: `src/mcp/queries.py` — `search_organisations`, `search_marches`, `build_where_args`, `compute_org_stats`, `_org_identite`.
- Create: `src/mcp/tools.py` — les 4 fonctions `@mcp_enabled`.
- Modify: `src/utils/tracking.py` — ajouter `track_mcp_tool`.
- Modify: `src/utils/search.py` — ajouter le paramètre `track: bool = True` à `search_org`.
- Modify: `src/app.py` — activer le serveur MCP (constructeur + `configure_mcp_server` + import des tools).
- Modify: `.template.env` — documenter `DASH_MCP_ENABLED`.
- Create: `tests/mcp/__init__.py`, `tests/mcp/test_serialization.py`, `tests/mcp/test_tracking.py`, `tests/mcp/test_queries.py`, `tests/mcp/test_tools.py`.

Le harness de test racine (`tests/conftest.py`) écrit `tests/test.parquet` (1 ligne : `acheteur_id="123"`, `acheteur_nom="ACHETEUR 1"`, `titulaire_id="345"`, `titulaire_nom="TITULAIRE 1"`, `montant=10`, `codeCPV="71600000"`, `dateNotification=2025-01-01`, `acheteur_departement_code="75"`, `objet="Objet test"`) et construit une base DuckDB de test isolée à l'import du conftest. Les tests sous `tests/mcp/` en héritent automatiquement.

---

### Task 1: `serialization.py` — conversion Polars → JSON

**Files:**

- Create: `src/mcp/__init__.py`
- Create: `src/mcp/serialization.py`
- Test: `tests/mcp/__init__.py`, `tests/mcp/test_serialization.py`

**Interfaces:**

- Produces: `to_json_records(df: pl.DataFrame) -> list[dict[str, Any]]` — convertit chaque ligne en dict JSON-sérialisable ; `datetime.date`/`datetime.datetime` → chaîne ISO, `None` préservé.

- [ ] **Step 1: Créer le package et le fichier de test**

Créer `src/mcp/__init__.py` (vide) et `tests/mcp/__init__.py` (vide), puis écrire le test :

```python
# tests/mcp/test_serialization.py
import datetime

import polars as pl

from src.mcp.serialization import to_json_records


def test_dates_become_iso_strings():
    df = pl.DataFrame({"d": [datetime.date(2025, 1, 1)], "n": [10]})
    assert to_json_records(df) == [{"d": "2025-01-01", "n": 10}]


def test_none_is_preserved():
    df = pl.DataFrame({"nom": [None], "x": [3]})
    assert to_json_records(df) == [{"nom": None, "x": 3}]


def test_strings_and_numbers_untouched():
    df = pl.DataFrame({"s": ["abc"], "f": [1.5]})
    assert to_json_records(df) == [{"s": "abc", "f": 1.5}]
```

- [ ] **Step 2: Lancer le test → échec**

Run: `uv run pytest tests/mcp/test_serialization.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.mcp.serialization'`

- [ ] **Step 3: Implémenter `serialization.py`**

```python
# src/mcp/serialization.py
import datetime
from typing import Any

import polars as pl


def to_json_records(df: pl.DataFrame) -> list[dict[str, Any]]:
    """Convertit un DataFrame Polars en liste de dicts JSON-sérialisables.

    Les dates/datetimes deviennent des chaînes ISO 8601 ; les valeurs nulles
    restent None. Utilisé par tous les tools MCP pour produire une sortie propre.
    """
    return [
        {key: _jsonify(value) for key, value in row.items()}
        for row in df.to_dicts()
    ]


def _jsonify(value: Any) -> Any:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value
```

- [ ] **Step 4: Lancer le test → succès**

Run: `uv run pytest tests/mcp/test_serialization.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/mcp/__init__.py src/mcp/serialization.py tests/mcp/__init__.py tests/mcp/test_serialization.py
git commit -m "feat(mcp): sérialisation Polars -> JSON pour les tools MCP"
```

(Si le hook reformate, refaire `git add` puis `git commit`.)

---

### Task 2: `track_mcp_tool` — tracking Matomo des appels MCP

**Files:**

- Modify: `src/utils/tracking.py`
- Test: `tests/mcp/test_tracking.py`

**Interfaces:**

- Consumes: le module `src.utils.tracking` (constante `DEVELOPMENT`, `post` de httpx).
- Produces: `track_mcp_tool(tool_name: str, query: str | None = None) -> None` — best-effort, n'émet qu'en prod (`not DEVELOPMENT` et `MATOMO_DOMAIN` défini) ; envoie `action_name="MCP / <tool>"`, `dimension1=<tool>`, et `search=<query>` si fourni.

- [ ] **Step 1: Écrire le test**

```python
# tests/mcp/test_tracking.py
import src.utils.tracking as tracking


def test_track_mcp_tool_sends_action_and_dimension(monkeypatch):
    captured = {}

    def fake_post(url, params):
        captured["url"] = url
        captured["params"] = params

        class _R:
            def raise_for_status(self):
                pass

        return _R()

    monkeypatch.setattr(tracking, "DEVELOPMENT", False)
    monkeypatch.setattr(tracking, "post", fake_post)
    monkeypatch.setenv("MATOMO_DOMAIN", "matomo.example")
    monkeypatch.setenv("MATOMO_ID_SITE", "1")

    tracking.track_mcp_tool("rechercher_marches", query="informatique")

    assert captured["params"]["action_name"] == "MCP / rechercher_marches"
    assert captured["params"]["dimension1"] == "rechercher_marches"
    assert captured["params"]["search"] == "informatique"


def test_track_mcp_tool_noop_in_development(monkeypatch):
    called = False

    def fake_post(url, params):
        nonlocal called
        called = True

    monkeypatch.setattr(tracking, "DEVELOPMENT", True)
    monkeypatch.setattr(tracking, "post", fake_post)
    monkeypatch.setenv("MATOMO_DOMAIN", "matomo.example")

    tracking.track_mcp_tool("stats_acheteur")

    assert called is False
```

- [ ] **Step 2: Lancer le test → échec**

Run: `uv run pytest tests/mcp/test_tracking.py -v`
Expected: FAIL — `AttributeError: module 'src.utils.tracking' has no attribute 'track_mcp_tool'`

- [ ] **Step 3: Ajouter `track_mcp_tool` à `src/utils/tracking.py`**

Ajouter à la fin du fichier (les imports `os`, `uuid`, `localtime`, `post`, `DEVELOPMENT` sont déjà présents en tête) :

```python
def track_mcp_tool(tool_name: str, query: str | None = None) -> None:
    """Enregistre un appel d'outil MCP dans Matomo (best-effort, prod uniquement).

    `action_name="MCP / <tool>"`, `dimension1=<tool>`. Si l'outil porte une
    requête texte, elle est envoyée en `search`. Nécessite un Custom Dimension
    slot 1 (scope Action) configuré côté Matomo — sinon `dimension1` est ignoré.
    Ne lève jamais : une panne Matomo ne doit pas casser l'appel du tool.
    """
    if DEVELOPMENT or not os.getenv("MATOMO_DOMAIN"):
        return
    params = {
        "idsite": os.getenv("MATOMO_ID_SITE"),
        "url": "https://colibre.fr/_mcp",
        "rec": "1",
        "action_name": f"MCP / {tool_name}",
        "dimension1": tool_name,
        "rand": uuid.uuid4().hex,
        "apiv": "1",
        "h": localtime().tm_hour,
        "m": localtime().tm_min,
        "s": localtime().tm_sec,
        "token_auth": os.getenv("MATOMO_TOKEN"),
    }
    if query:
        params["search"] = query
        params["search_cat"] = "mcp"
    try:
        post(url=f"https://{os.getenv('MATOMO_DOMAIN')}/matomo.php", params=params)
    except Exception:
        pass
```

- [ ] **Step 4: Lancer le test → succès**

Run: `uv run pytest tests/mcp/test_tracking.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/utils/tracking.py tests/mcp/test_tracking.py
git commit -m "feat(mcp): helper track_mcp_tool pour tracer les appels MCP dans Matomo"
```

---

### Task 3: `search_org` — paramètre `track` optionnel

**Files:**

- Modify: `src/utils/search.py`
- Test: `tests/mcp/test_queries.py` (créé ici, complété aux tâches suivantes)

**Interfaces:**

- Consumes: `search_org(dff, query, org_type)` existant.
- Produces: `search_org(dff, query, org_type, track: bool = True)` — quand `track=False`, ne déclenche pas `track_search(...)`. Comportement inchangé par défaut.

- [ ] **Step 1: Écrire le test**

```python
# tests/mcp/test_queries.py
import src.utils.search as search_mod
from src.utils.data import DF_ACHETEURS
from src.utils.search import search_org


def test_search_org_track_false_skips_track_search(monkeypatch):
    calls = []
    monkeypatch.setattr(
        search_mod, "track_search", lambda q, c: calls.append((q, c))
    )

    search_org(DF_ACHETEURS, "ACHETEUR", "acheteur", track=False)

    assert calls == []


def test_search_org_track_true_calls_track_search(monkeypatch):
    calls = []
    monkeypatch.setattr(
        search_mod, "track_search", lambda q, c: calls.append((q, c))
    )

    search_org(DF_ACHETEURS, "ACHETEUR", "acheteur", track=True)

    assert calls == [("ACHETEUR", "home_page_search")]
```

- [ ] **Step 2: Lancer le test → échec**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: FAIL — `TypeError: search_org() got an unexpected keyword argument 'track'`

- [ ] **Step 3: Ajouter le paramètre `track`**

Dans `src/utils/search.py`, modifier la signature et le corps :

```python
def search_org(
    dff: pl.DataFrame, query: str, org_type: str, track: bool = True
) -> pl.DataFrame:
```

et remplacer :

```python
    # Enregistrement des recherche dans Matomo
    track_search(query, "home_page_search")
```

par :

```python
    # Enregistrement des recherche dans Matomo
    if track:
        track_search(query, "home_page_search")
```

- [ ] **Step 4: Lancer le test → succès**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/utils/search.py tests/mcp/test_queries.py
git commit -m "feat(mcp): search_org accepte track=False pour ne pas polluer Matomo"
```

---

### Task 4: `queries.py` — `search_organisations`

**Files:**

- Create: `src/mcp/queries.py`
- Test: `tests/mcp/test_queries.py` (ajout)

**Interfaces:**

- Consumes: `search_org(dff, query, org_type, track=False)` (Task 3), `DF_ACHETEURS`/`DF_TITULAIRES` de `src.utils.data`, `to_json_records` (Task 1).
- Produces: `search_organisations(query: str, org_type: str = "acheteur", limite: int = 20) -> list[dict]` — retourne `[{"id", "nom", "departement"}]`. Lève `ValueError` si `org_type` invalide. Aussi : constantes `PAGE_SIZE = 50`, `TOP_N = 10`, `ORG_FRAMES`.

- [ ] **Step 1: Écrire le test (ajouter à `tests/mcp/test_queries.py`)**

```python
import pytest

from src.mcp.queries import search_organisations


def test_search_organisations_finds_known_acheteur():
    result = search_organisations("ACHETEUR", "acheteur")
    assert any(r["id"] == "123" for r in result)
    first = next(r for r in result if r["id"] == "123")
    assert set(first.keys()) == {"id", "nom", "departement"}


def test_search_organisations_invalid_type_raises():
    with pytest.raises(ValueError):
        search_organisations("x", "autre")


def test_search_organisations_respects_limite():
    result = search_organisations("ACHETEUR", "acheteur", limite=1)
    assert len(result) <= 1
```

- [ ] **Step 2: Lancer le test → échec**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.mcp.queries'`

- [ ] **Step 3: Créer `src/mcp/queries.py` avec `search_organisations`**

```python
# src/mcp/queries.py
from src.mcp.serialization import to_json_records  # noqa: F401 (utilisé aux tâches suivantes)
from src.utils.data import DF_ACHETEURS, DF_TITULAIRES
from src.utils.search import search_org

PAGE_SIZE = 50
TOP_N = 10
ORG_FRAMES = {"acheteur": DF_ACHETEURS, "titulaire": DF_TITULAIRES}


def search_organisations(
    query: str, org_type: str = "acheteur", limite: int = 20
) -> list[dict]:
    """Recherche des organisations par nom, résout un nom -> id."""
    if org_type not in ORG_FRAMES:
        raise ValueError(
            f"type invalide: {org_type!r} (attendu 'acheteur' ou 'titulaire')"
        )
    df = search_org(ORG_FRAMES[org_type], query, org_type, track=False).head(limite)
    return [
        {
            "id": r[f"{org_type}_id"],
            "nom": r[f"{org_type}_nom"],
            "departement": r.get("Département"),
        }
        for r in df.to_dicts()
    ]
```

- [ ] **Step 4: Lancer le test → succès**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: PASS (5 tests au total dans ce fichier)

- [ ] **Step 5: Commit**

```bash
git add src/mcp/queries.py tests/mcp/test_queries.py
git commit -m "feat(mcp): tool search_organisations (résolution nom -> id)"
```

---

### Task 5: `queries.py` — `build_where_args` + `search_marches`

**Files:**

- Modify: `src/mcp/queries.py`
- Test: `tests/mcp/test_queries.py` (ajout)

**Interfaces:**

- Consumes: `build_where(args, schema)` et `FilterError` de `src.api.filters` ; `query_marches`, `count_marches`, `schema` de `src.db` ; `to_json_records` (Task 1) ; `PAGE_SIZE` (Task 4).
- Produces:

  - `build_where_args(named: dict, filtres_avances: dict | None) -> list[tuple[str, str]]` — traduit paramètres nommés + filtres avancés en tuples `("col__op", "valeur")`.
  - `search_marches(*, acheteur_id=None, titulaire_id=None, cpv=None, objet_contient=None, montant_min=None, montant_max=None, date_min=None, date_max=None, departement=None, page=1, filtres_avances=None) -> dict` — retourne `{"meta": {"page", "page_size", "total"}, "marches": [...]}` ou `{"error": ..., "champ": ...}` sur `FilterError`.

- [ ] **Step 1: Écrire le test (ajouter à `tests/mcp/test_queries.py`)**

```python
from src.mcp.queries import build_where_args, search_marches


def test_build_where_args_named_params():
    args = build_where_args(
        {"acheteur_id": "123", "montant_min": 5, "objet_contient": "test"}, None
    )
    assert ("acheteur_id__exact", "123") in args
    assert ("montant__greater", "5") in args
    assert ("objet__contains", "test") in args


def test_build_where_args_merges_filtres_avances():
    args = build_where_args(
        {"acheteur_id": "123"}, {"titulaire_departement_code__exact": "35"}
    )
    assert ("acheteur_id__exact", "123") in args
    assert ("titulaire_departement_code__exact", "35") in args


def test_search_marches_returns_meta_and_rows():
    result = search_marches(acheteur_id="123")
    assert result["meta"]["total"] >= 1
    assert result["meta"]["page"] == 1
    assert result["meta"]["page_size"] == 50
    assert any(m["acheteur_id"] == "123" for m in result["marches"])
    # dates sérialisées en ISO
    assert result["marches"][0]["dateNotification"] == "2025-01-01"


def test_search_marches_no_match_is_empty():
    result = search_marches(acheteur_id="inconnu-xyz")
    assert result["meta"]["total"] == 0
    assert result["marches"] == []


def test_search_marches_bad_filter_returns_error():
    result = search_marches(filtres_avances={"colonne_bidon__exact": "x"})
    assert "error" in result
```

- [ ] **Step 2: Lancer le test → échec**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_where_args'`

- [ ] **Step 3: Étendre `src/mcp/queries.py`**

Remplacer la ligne d'import `to_json_records` (marquée `noqa`) par les imports réels et ajouter le code. Nouvel en-tête d'imports en haut du fichier :

```python
from src.api.filters import FilterError, build_where
from src.db import count_marches, query_marches
from src.db import schema as duckdb_schema
from src.mcp.serialization import to_json_records
from src.utils.data import DF_ACHETEURS, DF_TITULAIRES
from src.utils.search import search_org
```

Ajouter après les constantes :

```python
# Colonnes renvoyées par rechercher_marches (sortie ciblée, pas SELECT *).
MARCHES_COLUMNS = [
    "uid",
    "objet",
    "montant",
    "dateNotification",
    "codeCPV",
    "acheteur_id",
    "acheteur_nom",
    "acheteur_departement_code",
    "titulaire_id",
    "titulaire_nom",
]

# (param nommé, colonne decp, opérateur du moteur de filtres API).
# `greater` = >=, `less` = <=, `contains` = LIKE %v%, `exact` = =.
_NAMED_FILTERS = [
    ("acheteur_id", "acheteur_id", "exact"),
    ("titulaire_id", "titulaire_id", "exact"),
    ("cpv", "codeCPV", "contains"),
    ("objet_contient", "objet", "contains"),
    ("montant_min", "montant", "greater"),
    ("montant_max", "montant", "less"),
    ("date_min", "dateNotification", "greater"),
    ("date_max", "dateNotification", "less"),
    ("departement", "acheteur_departement_code", "exact"),
]


def build_where_args(
    named: dict, filtres_avances: dict | None
) -> list[tuple[str, str]]:
    """Traduit les paramètres nommés + filtres avancés en tuples (col__op, valeur)."""
    args: list[tuple[str, str]] = []
    for param, col, op in _NAMED_FILTERS:
        value = named.get(param)
        if value is not None:
            args.append((f"{col}__{op}", str(value)))
    if filtres_avances:
        for key, value in filtres_avances.items():
            args.append((key, str(value)))
    return args


def search_marches(
    *,
    acheteur_id: str | None = None,
    titulaire_id: str | None = None,
    cpv: str | None = None,
    objet_contient: str | None = None,
    montant_min: float | None = None,
    montant_max: float | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    departement: str | None = None,
    page: int = 1,
    filtres_avances: dict | None = None,
) -> dict:
    """Recherche paginée de marchés. Même sémantique de filtres que l'API REST."""
    named = {
        "acheteur_id": acheteur_id,
        "titulaire_id": titulaire_id,
        "cpv": cpv,
        "objet_contient": objet_contient,
        "montant_min": montant_min,
        "montant_max": montant_max,
        "date_min": date_min,
        "date_max": date_max,
        "departement": departement,
    }
    args = build_where_args(named, filtres_avances)
    try:
        where_sql, params, order_sql = build_where(args, duckdb_schema)
    except FilterError as e:
        return {"error": str(e), "champ": e.field}

    page = max(1, int(page))
    offset = (page - 1) * PAGE_SIZE
    order_by = order_sql or '"dateNotification" DESC, "uid" DESC'
    df = query_marches(
        where_sql,
        params,
        columns=MARCHES_COLUMNS,
        order_by=order_by,
        limit=PAGE_SIZE,
        offset=offset,
    )
    total = count_marches(where_sql, params)
    return {
        "meta": {"page": page, "page_size": PAGE_SIZE, "total": total},
        "marches": to_json_records(df),
    }
```

Supprimer l'ancienne ligne `from src.mcp.serialization import to_json_records # noqa: F401` et l'ancien bloc d'imports partiel de la Task 4 (remplacés par l'en-tête ci-dessus).

- [ ] **Step 4: Lancer le test → succès**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: PASS (10 tests au total dans ce fichier)

- [ ] **Step 5: Commit**

```bash
git add src/mcp/queries.py tests/mcp/test_queries.py
git commit -m "feat(mcp): tool rechercher_marches (filtres hybrides + pagination)"
```

---

### Task 6: `queries.py` — `compute_org_stats`

**Files:**

- Modify: `src/mcp/queries.py`
- Test: `tests/mcp/test_queries.py` (ajout)

**Interfaces:**

- Consumes: `aggregate_marches`, `query_marches` de `src.db` ; `to_json_records` (Task 1) ; `TOP_N` (Task 4).
- Produces: `compute_org_stats(org_type: str, org_id: str) -> dict` — retourne `{"identite", "nb_marches", "montant_total", "repartition_annuelle", "top_<contrepartie>s", "top_cpv"}`. Contrepartie = `titulaire` si `org_type="acheteur"`, sinon `acheteur`. `nb_marches=0` et listes vides si id inconnu (pas d'exception). Aussi `_org_identite(org_type, org_id) -> dict`.

- [ ] **Step 1: Écrire le test (ajouter à `tests/mcp/test_queries.py`)**

```python
from src.mcp.queries import compute_org_stats


def test_compute_org_stats_acheteur_known():
    stats = compute_org_stats("acheteur", "123")
    assert stats["nb_marches"] >= 1
    assert stats["montant_total"] == 10
    assert stats["identite"]["id"] == "123"
    assert stats["identite"]["nom"] == "ACHETEUR 1"
    assert "top_titulaires" in stats
    assert "top_cpv" in stats
    # répartition annuelle dérivée de dateNotification (2025)
    annees = [row["annee"] for row in stats["repartition_annuelle"]]
    assert 2025 in annees


def test_compute_org_stats_titulaire_known():
    stats = compute_org_stats("titulaire", "345")
    assert stats["nb_marches"] >= 1
    assert "top_acheteurs" in stats


def test_compute_org_stats_unknown_is_empty():
    stats = compute_org_stats("acheteur", "inconnu-xyz")
    assert stats["nb_marches"] == 0
    assert stats["montant_total"] == 0
    assert stats["repartition_annuelle"] == []
    assert stats["top_titulaires"] == []
    assert stats["top_cpv"] == []
```

- [ ] **Step 2: Lancer le test → échec**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_org_stats'`

- [ ] **Step 3: Étendre `src/mcp/queries.py`**

Ajouter `aggregate_marches` à l'import de `src.db` :

```python
from src.db import aggregate_marches, count_marches, query_marches
```

Ajouter les fonctions :

```python
def _org_identite(org_type: str, org_id: str) -> dict:
    df = query_marches(
        where_sql=f'"{org_type}_id" = ?',
        params=[org_id],
        columns=[
            f"{org_type}_id",
            f"{org_type}_nom",
            f"{org_type}_departement_nom",
            f"{org_type}_commune_nom",
        ],
        limit=1,
    )
    if df.height == 0:
        return {"id": org_id, "nom": None, "departement": None, "commune": None}
    r = df.row(0, named=True)
    return {
        "id": org_id,
        "nom": r[f"{org_type}_nom"],
        "departement": r[f"{org_type}_departement_nom"],
        "commune": r[f"{org_type}_commune_nom"],
    }


def compute_org_stats(org_type: str, org_id: str) -> dict:
    """Statistiques agrégées d'un acheteur ou titulaire."""
    if org_type not in ORG_FRAMES:
        raise ValueError(
            f"type invalide: {org_type!r} (attendu 'acheteur' ou 'titulaire')"
        )
    other = "titulaire" if org_type == "acheteur" else "acheteur"
    where_sql = f'"{org_type}_id" = ?'
    params = [org_id]
    identite = _org_identite(org_type, org_id)

    totals = aggregate_marches(
        select_sql='COUNT("uid") AS nb, COALESCE(SUM("montant"), 0) AS montant_total',
        where_sql=where_sql,
        params=params,
    )
    nb = int(totals["nb"][0])
    if nb == 0:
        return {
            "identite": identite,
            "nb_marches": 0,
            "montant_total": 0,
            "repartition_annuelle": [],
            f"top_{other}s": [],
            "top_cpv": [],
        }

    annuelle = aggregate_marches(
        select_sql=(
            'CAST(date_part(\'year\', "dateNotification") AS INTEGER) AS annee, '
            'COUNT("uid") AS nb_marches, '
            'COALESCE(SUM("montant"), 0) AS montant_total'
        ),
        where_sql=where_sql,
        params=params,
        group_by='date_part(\'year\', "dateNotification")',
        order_by="annee",
    )
    top_other = aggregate_marches(
        select_sql=(
            f'"{other}_id" AS id, any_value("{other}_nom") AS nom, '
            'COUNT("uid") AS nb_marches, '
            'COALESCE(SUM("montant"), 0) AS montant_total'
        ),
        where_sql=where_sql,
        params=params,
        group_by=f'"{other}_id"',
        order_by="nb_marches DESC",
        limit=TOP_N,
    )
    top_cpv = aggregate_marches(
        select_sql='"codeCPV" AS cpv, COUNT("uid") AS nb_marches',
        where_sql=where_sql,
        params=params,
        group_by='"codeCPV"',
        order_by="nb_marches DESC",
        limit=TOP_N,
    )
    return {
        "identite": identite,
        "nb_marches": nb,
        "montant_total": float(totals["montant_total"][0]),
        "repartition_annuelle": to_json_records(annuelle),
        f"top_{other}s": to_json_records(top_other),
        "top_cpv": to_json_records(top_cpv),
    }
```

- [ ] **Step 4: Lancer le test → succès**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: PASS (13 tests au total dans ce fichier)

- [ ] **Step 5: Commit**

```bash
git add src/mcp/queries.py tests/mcp/test_queries.py
git commit -m "feat(mcp): tools stats_acheteur / stats_titulaire (agrégations)"
```

---

### Task 7: `tools.py` — les 4 fonctions `@mcp_enabled`

**Files:**

- Create: `src/mcp/tools.py`
- Test: `tests/mcp/test_tools.py`

**Interfaces:**

- Consumes: `queries.search_organisations`, `queries.search_marches`, `queries.compute_org_stats` ; `track_mcp_tool` (Task 2) ; `mcp_enabled` de `dash.mcp`.
- Produces: 4 fonctions décorées `rechercher_organisations`, `stats_acheteur`, `stats_titulaire`, `rechercher_marches`, importables et appelables directement.

- [ ] **Step 1: Écrire le test**

```python
# tests/mcp/test_tools.py
from src.mcp import tools


def test_all_four_tools_are_callable():
    for name in (
        "rechercher_organisations",
        "stats_acheteur",
        "stats_titulaire",
        "rechercher_marches",
    ):
        assert callable(getattr(tools, name))


def test_rechercher_organisations_returns_list():
    result = tools.rechercher_organisations("ACHETEUR", "acheteur")
    assert isinstance(result, list)
    assert any(r["id"] == "123" for r in result)


def test_rechercher_marches_returns_meta():
    result = tools.rechercher_marches(acheteur_id="123")
    assert result["meta"]["total"] >= 1


def test_stats_acheteur_returns_stats():
    result = tools.stats_acheteur("123")
    assert result["nb_marches"] >= 1
    assert result["identite"]["id"] == "123"


def test_stats_titulaire_returns_stats():
    result = tools.stats_titulaire("345")
    assert result["nb_marches"] >= 1
```

- [ ] **Step 2: Lancer le test → échec**

Run: `uv run pytest tests/mcp/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.mcp.tools'`

- [ ] **Step 3: Créer `src/mcp/tools.py`**

```python
# src/mcp/tools.py
from dash.mcp import mcp_enabled

from src.mcp import queries
from src.utils.tracking import track_mcp_tool


@mcp_enabled(name="rechercher_organisations", expose_docstring=True)
def rechercher_organisations(
    query: str, type: str = "acheteur", limite: int = 20  # noqa: A002
) -> list[dict]:
    """Recherche des acheteurs ou titulaires publics par nom.

    Utiliser en premier pour résoudre un nom d'organisation vers son
    identifiant, à passer ensuite à stats_acheteur / stats_titulaire.

    query: texte libre (nom d'organisation).
    type: "acheteur" ou "titulaire".
    Retourne une liste de {id, nom, departement}.
    """
    track_mcp_tool("rechercher_organisations", query=query)
    return queries.search_organisations(query, type, limite)


@mcp_enabled(name="stats_acheteur", expose_docstring=True)
def stats_acheteur(acheteur_id: str) -> dict:
    """Statistiques agrégées d'un acheteur public (par identifiant).

    Retourne nombre de marchés, montant total, répartition annuelle,
    principaux titulaires et principaux codes CPV.
    """
    track_mcp_tool("stats_acheteur")
    return queries.compute_org_stats("acheteur", acheteur_id)


@mcp_enabled(name="stats_titulaire", expose_docstring=True)
def stats_titulaire(titulaire_id: str) -> dict:
    """Statistiques agrégées d'un titulaire (entreprise) par identifiant.

    Retourne nombre de marchés remportés, montant total, répartition
    annuelle, principaux acheteurs et principaux codes CPV.
    """
    track_mcp_tool("stats_titulaire")
    return queries.compute_org_stats("titulaire", titulaire_id)


@mcp_enabled(name="rechercher_marches", expose_docstring=True)
def rechercher_marches(
    acheteur_id: str | None = None,
    titulaire_id: str | None = None,
    cpv: str | None = None,
    objet_contient: str | None = None,
    montant_min: float | None = None,
    montant_max: float | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    departement: str | None = None,
    page: int = 1,
    filtres_avances: dict | None = None,
) -> dict:
    """Recherche paginée de marchés publics (DECP).

    Filtres nommés : acheteur_id, titulaire_id, cpv (code CPV, correspondance
    partielle), objet_contient (texte de l'objet), montant_min, montant_max,
    date_min / date_max (format YYYY-MM-DD, sur dateNotification),
    departement (code département de l'acheteur).
    filtres_avances : dict optionnel {"colonne__operateur": valeur} pour les
    besoins pointus (mêmes colonnes/opérateurs que l'API REST colibre).
    page : numéro de page (50 résultats par page).
    Retourne {meta: {page, page_size, total}, marches: [...]}.
    """
    track_mcp_tool("rechercher_marches", query=objet_contient)
    return queries.search_marches(
        acheteur_id=acheteur_id,
        titulaire_id=titulaire_id,
        cpv=cpv,
        objet_contient=objet_contient,
        montant_min=montant_min,
        montant_max=montant_max,
        date_min=date_min,
        date_max=date_max,
        departement=departement,
        page=page,
        filtres_avances=filtres_avances,
    )
```

- [ ] **Step 4: Lancer le test → succès**

Run: `uv run pytest tests/mcp/test_tools.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/mcp/tools.py tests/mcp/test_tools.py
git commit -m "feat(mcp): expose les 4 fonctions métier via @mcp_enabled"
```

---

### Task 8: Activation du serveur MCP dans l'app + doc env

**Files:**

- Modify: `src/app.py`
- Modify: `.template.env`
- Test: vérification manuelle (import) + suite complète.

**Interfaces:**

- Consumes: `src.mcp.tools` (Task 7), `enable_mcp`/`configure_mcp_server` de Dash.
- Produces: serveur MCP monté sur `/_mcp` quand `DASH_MCP_ENABLED=true`, exposant uniquement les 4 tools.

- [ ] **Step 1: Ajouter le paramètre `enable_mcp` au constructeur `Dash`**

Dans `src/app.py`, juste avant `app: Dash = Dash(` (vers la ligne 78), ajouter :

```python
_mcp_enabled = os.getenv("DASH_MCP_ENABLED") == "true"
```

Puis, dans l'appel `Dash(...)`, ajouter le paramètre (après `compress=True,`) :

```python
    enable_mcp=_mcp_enabled,
```

- [ ] **Step 2: Monter les tools après l'init de l'app**

Toujours dans `src/app.py`, juste après la ligne `init_api(app.server)`, ajouter :

```python
# Serveur MCP (issue #111, scope A) : n'expose QUE les fonctions @mcp_enabled,
# jamais les callbacks/layout/pages d'UI. Activé via DASH_MCP_ENABLED=true.
if _mcp_enabled:
    from dash.mcp import configure_mcp_server  # noqa: E402

    configure_mcp_server(
        include_layout=False,
        include_callbacks=False,
        include_pages=False,
        include_clientside_callbacks=False,
    )
    import src.mcp.tools  # noqa: E402,F401  # l'import enregistre les @mcp_enabled
```

- [ ] **Step 3: Documenter la variable dans `.template.env`**

Ajouter à `.template.env` :

```bash
# Serveur MCP (issue #111). Laisser à false tant que l'authentification
# (OAuth + gate abonnement, scope B) n'est pas en place : sinon le serveur MCP
# est ouvert sans contrôle d'accès. Prérequis Matomo pour le tracking des appels :
# créer un Custom Dimension slot 1 (scope Action).
DASH_MCP_ENABLED=false
```

- [ ] **Step 4: Vérifier l'import des tools (hors app complète)**

Run: `uv run python -c "import src.mcp.tools; print('ok', [f for f in ('rechercher_organisations','stats_acheteur','stats_titulaire','rechercher_marches')])"`
Expected: affiche `ok [...]` sans erreur d'import.

- [ ] **Step 5: Lancer la suite de tests MCP complète**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS (tous les tests des tâches 1-7).

- [ ] **Step 6: Lancer la suite complète (dernière tâche du plan)**

Run: `uv run pytest`
Expected: PASS (aucune régression ; les tests Selenium nécessitent Chrome).

- [ ] **Step 7: Commit**

```bash
git add src/app.py .template.env
git commit -m "feat(mcp): activer le serveur MCP via DASH_MCP_ENABLED (scope A #111)"
```

---

## Vérification manuelle de bout en bout (optionnelle, après Task 8)

Pour tester le serveur MCP réel avec un vrai client :

```bash
DASH_MCP_ENABLED=true DATA_FILE_PARQUET_PATH=tests/test.parquet uv run run.py
# dans un autre terminal / client MCP :
claude mcp add colibre-local --transport http --scope user http://127.0.0.1:8050/_mcp
```

Puis demander à l'agent d'appeler `rechercher_marches` / `stats_acheteur`. Confirmer que seuls les 4 tools sont visibles (aucun callback d'UI).

## Self-Review (effectuée)

- **Couverture spec** : sérialisation (T1), tracking Matomo `action_name="MCP"`+`dimension1` (T2), non-pollution de `track_search` (T3), les 4 tools `rechercher_organisations` (T4) / `rechercher_marches` hybride (T5) / `stats_acheteur`+`stats_titulaire` (T6), surface réduite via `configure_mcp_server` + gating `DASH_MCP_ENABLED` off par défaut (T8), doc env + prérequis Matomo (T8). ✎ Écarts assumés vs spec, dus aux données réelles : pas de libellé CPV (`top_cpv` = `{cpv, nb_marches}`) ; `search_organisations` renvoie `{id, nom, departement}` sans `commune` (colonne absente de la sortie de `search_org`) — l'identité complète (avec commune) reste fournie par `stats_*` via `_org_identite`. Arborescence affinée : logique données regroupée dans `queries.py` (au lieu de `stats.py` seul) pour garder `tools.py` sans SQL.
- **Placeholders** : aucun TODO/TBD ; tout le code est fourni.
- **Cohérence des types** : `search_marches` / `compute_org_stats` / `search_organisations` référencés en T7 avec les signatures définies en T4-T6 ; `to_json_records`, `track_mcp_tool`, `search_org(track=…)` cohérents entre tâches ; contrepartie `top_<other>s` cohérente entre T6 (définition) et T7 (docstrings).
