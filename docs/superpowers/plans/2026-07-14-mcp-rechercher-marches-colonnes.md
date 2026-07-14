# Colonnes configurables pour `rechercher_marches` (MCP) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre configurable la sélection des colonnes du tool MCP `rechercher_marches`, avec un champ `lien` vers chaque marché et un paramètre `colonnes` typé en `enum`.

**Architecture:** Le paramètre `colonnes` (défaut = jeu actuel, sinon « remplace ») est validé au runtime contre un ensemble sélectionnable dérivé du schéma de référence `DATA_SCHEMA ∩ duckdb_schema`, uni au défaut. Un champ virtuel `lien = APP_BASE_URL/marche/{uid}` est ajouté en Python après la requête. L'UX passe par une annotation `Literal` (enum) exposée dans le schéma du tool.

**Tech Stack:** Python, dash 4.4 (`mcp_enabled`), DuckDB, Polars, pytest, `typing.Literal`, pydantic `TypeAdapter`.

Design de référence : `docs/superpowers/specs/2026-07-14-mcp-rechercher-marches-colonnes-design.md`.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `from src.mcp.queries import ColonneMarche`).
- `pre-commit run --files <fichiers>` avant chaque `git add` (ruff formate).
- Lancer les tests avec `uv run pytest` (l'activation du venv dans le shell n'est pas fiable ici).
- Tests ciblés sur leur propre fichier ; ne pas lancer toute la suite (Selenium/Chrome) avant la fin.
- `lien` toujours présent, non désactivable ; `uid` toujours en sortie.
- Sémantique « remplace » : `colonnes=[...]` renvoie exactement ces colonnes (+ `uid` + `lien`).
- Erreur colonne invalide : `{"error": "colonne inconnue: <col>", "champ": <col>}` (même patron que les erreurs de filtre).
- `base = os.getenv("APP_BASE_URL", "").rstrip("/")` (cohérent avec `src/mcp/auth.py`, `oauth/routes.py`).

---

## File Structure

- Modify `src/mcp/queries.py` — ajoute `SELECTABLE_COLUMNS`, `ColonneMarche`, le paramètre `colonnes` + `lien` dans `search_marches`, et `colonnes_disponibles` dans `describe_schema`.
- Modify `src/mcp/tools.py` — ajoute le paramètre `colonnes: list[ColonneMarche] | None` (annotation enum) + docstring, et le transmet à `queries.search_marches`.
- Modify `tests/mcp/test_queries.py` — comportement `search_marches` / `describe_schema`.
- Modify `tests/mcp/test_tools.py` — enum du paramètre + passthrough bout-en-bout.

---

### Task 1: `queries.py` — colonnes configurables, `lien`, schéma

**Files:**

- Modify: `src/mcp/queries.py`
- Test: `tests/mcp/test_queries.py`

**Interfaces:**

- Consumes : `DATA_SCHEMA` (`src.utils.data`), `duckdb_schema` (= `from src.db import schema as duckdb_schema`, déjà importé), `MARCHES_COLUMNS`, `to_json_records`, `query_marches`, `count_marches`, `build_where`.
- Produces :

  - `SELECTABLE_COLUMNS: tuple[str, ...]` — ensemble sélectionnable (défaut ∪ (DATA_SCHEMA ∩ duckdb_schema)).
  - `ColonneMarche` — `typing.Literal[SELECTABLE_COLUMNS]`.
  - `search_marches(..., colonnes: list[str] | None = None) -> dict` — inchangé si `colonnes is None` ; sinon exactement ces colonnes (+ `uid` + `lien`) ; chaque marché gagne `lien`.
  - `describe_schema()` renvoie en plus `colonnes_disponibles: list[str]`, et `colonnes_retournees` inclut `"lien"`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/mcp/test_queries.py` :

```python
def test_search_marches_default_columns_and_lien(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    from src.mcp.queries import MARCHES_COLUMNS

    result = search_marches(acheteur_id="123")
    m = result["marches"][0]
    # Toutes les colonnes du défaut + le lien
    assert set(MARCHES_COLUMNS).issubset(m.keys())
    assert m["lien"] == f"https://colibre.fr/marche/{m['uid']}"


def test_search_marches_custom_columns_replace(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    result = search_marches(acheteur_id="123", colonnes=["objet", "montant"])
    m = result["marches"][0]
    # « remplace » : exactement les colonnes demandées + uid (clé) + lien
    assert set(m.keys()) == {"uid", "objet", "montant", "lien"}


def test_search_marches_custom_columns_include_uid_only_once(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    result = search_marches(acheteur_id="123", colonnes=["uid", "objet"])
    m = result["marches"][0]
    assert set(m.keys()) == {"uid", "objet", "lien"}


def test_search_marches_invalid_column_rejected():
    result = search_marches(acheteur_id="123", colonnes=["nexiste_pas"])
    assert result["error"] == "colonne inconnue: nexiste_pas"
    assert result["champ"] == "nexiste_pas"
    assert "marches" not in result


def test_search_marches_lien_relative_when_base_unset(monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    result = search_marches(acheteur_id="123", colonnes=["objet"])
    m = result["marches"][0]
    assert m["lien"] == f"/marche/{m['uid']}"


def test_describe_schema_exposes_colonnes_disponibles():
    from src.mcp.queries import describe_schema

    schema = describe_schema()
    dispo = schema["colonnes_disponibles"]
    assert isinstance(dispo, list) and dispo
    # surensemble des colonnes filtrables (inclut le défaut)
    assert set(schema["colonnes_filtrables"]).issubset(set(dispo))
    assert "lien" in schema["colonnes_retournees"]
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/mcp/test_queries.py -k "colonnes or lien or disponibles or replace or invalid_column" -v`
Expected: FAIL (`TypeError: search_marches() got an unexpected keyword argument 'colonnes'` et `KeyError: 'colonnes_disponibles'`).

- [ ] **Step 3: Ajouter `import os` et `Literal`**

En tête de `src/mcp/queries.py`, remplacer :

```python
# src/mcp/queries.py
import re
```

par :

```python
# src/mcp/queries.py
import os
import re
from typing import Literal
```

- [ ] **Step 4: Définir `SELECTABLE_COLUMNS` et `ColonneMarche`**

Juste après la définition de `MARCHES_COLUMNS` (la liste des 10 colonnes) dans `src/mcp/queries.py`, ajouter :

```python
# Colonnes sélectionnables par le client : le schéma de référence (présent en
# base) uni aux colonnes du défaut, pour que tout le défaut reste re-sélectionnable
# même si une colonne enrichie (ex. acheteur_nom) est absente de DATA_SCHEMA.
_FILTRABLES = tuple(name for name in DATA_SCHEMA if name in duckdb_schema)
SELECTABLE_COLUMNS = tuple(dict.fromkeys((*MARCHES_COLUMNS, *_FILTRABLES)))

# Enum exposé dans le schéma du tool (UX : liste fermée pour l'agent/le client).
ColonneMarche = Literal[SELECTABLE_COLUMNS]
```

- [ ] **Step 5: Implémenter la résolution des colonnes + `lien` dans `search_marches`**

Dans `src/mcp/queries.py`, remplacer la signature de `search_marches` pour ajouter le paramètre `colonnes` (à la fin, après `filtres_avances`) :

```python
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
    colonnes: list[str] | None = None,
) -> dict:
```

Puis, dans le corps, remplacer le bloc allant de `args = build_where_args(...)` jusqu'au `return {...}` final par :

```python
    args = build_where_args(named, filtres_avances)
    try:
        where_sql, params, order_sql = build_where(args, duckdb_schema)
    except FilterError as e:
        return {"error": str(e), "champ": e.field}

    if colonnes is None:
        out_columns = list(MARCHES_COLUMNS)
    else:
        invalid = [c for c in colonnes if c not in SELECTABLE_COLUMNS]
        if invalid:
            return {"error": f"colonne inconnue: {invalid[0]}", "champ": invalid[0]}
        # uid toujours présent (clé primaire + nécessaire au lien), sans doublon.
        out_columns = ["uid"] + [c for c in colonnes if c != "uid"]

    page = max(1, int(page))
    offset = (page - 1) * PAGE_SIZE
    order_by = order_sql or '"dateNotification" DESC, "uid" DESC'
    df = query_marches(
        where_sql,
        params,
        columns=out_columns,
        order_by=order_by,
        limit=PAGE_SIZE,
        offset=offset,
    )
    total = count_marches(where_sql, params)
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    marches = to_json_records(df)
    for marche in marches:
        marche["lien"] = f"{base}/marche/{marche['uid']}"
    return {
        "meta": {"page": page, "page_size": PAGE_SIZE, "total": total},
        "marches": marches,
    }
```

- [ ] **Step 6: Exposer `colonnes_disponibles` et `lien` dans `describe_schema`**

Dans `src/mcp/queries.py`, dans `describe_schema`, remplacer le `return {...}` final par :

```python
    return {
        "colonnes_filtrables": colonnes,
        "colonnes_retournees": [*MARCHES_COLUMNS, "lien"],
        "colonnes_disponibles": list(SELECTABLE_COLUMNS),
        "operateurs": sorted(OPERATORS),
        "filtres_nommes": {p: f"{c}__{o}" for p, c, o in _NAMED_FILTERS},
    }
```

- [ ] **Step 7: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/mcp/test_queries.py -v`
Expected: PASS (tous, y compris les tests existants inchangés).

- [ ] **Step 8: Commit**

```bash
pre-commit run --files src/mcp/queries.py tests/mcp/test_queries.py
git add src/mcp/queries.py tests/mcp/test_queries.py
git commit -m "feat(mcp): colonnes configurables + lien dans rechercher_marches (#114)"
```

---

### Task 2: `tools.py` — paramètre `colonnes` enum + docstring

**Files:**

- Modify: `src/mcp/tools.py`
- Test: `tests/mcp/test_tools.py`

**Interfaces:**

- Consumes : `ColonneMarche`, `search_marches` (Task 1).
- Produces : `rechercher_marches(..., colonnes: list[ColonneMarche] | None = None) -> dict` — le paramètre `colonnes` porte un `enum` dans le schéma du tool et est transmis à `queries.search_marches`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/mcp/test_tools.py` :

```python
def test_rechercher_marches_colonnes_param_is_enum():
    import typing

    from pydantic import TypeAdapter

    hints = typing.get_type_hints(tools.rechercher_marches)
    schema = TypeAdapter(hints["colonnes"]).json_schema()
    # list[ColonneMarche] | None -> anyOf[array(items.enum), null]
    array_schema = next(s for s in schema["anyOf"] if s.get("type") == "array")
    enum = array_schema["items"]["enum"]
    assert "objet" in enum
    assert "montant" in enum
    assert "uid" in enum


def test_rechercher_marches_colonnes_passthrough(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://colibre.fr")
    result = tools.rechercher_marches(acheteur_id="123", colonnes=["objet"])
    m = result["marches"][0]
    assert set(m.keys()) == {"uid", "objet", "lien"}
    assert m["lien"] == f"https://colibre.fr/marche/{m['uid']}"
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `uv run pytest tests/mcp/test_tools.py -k "colonnes" -v`
Expected: FAIL (`KeyError: 'colonnes'` sur `get_type_hints`, et `TypeError` sur l'appel avec `colonnes=`).

- [ ] **Step 3: Importer `ColonneMarche`**

En tête de `src/mcp/tools.py`, remplacer :

```python
from src.mcp import queries
```

par :

```python
from src.mcp import queries
from src.mcp.queries import ColonneMarche
```

- [ ] **Step 4: Ajouter le paramètre `colonnes` (signature, docstring, appel)**

Dans `src/mcp/tools.py`, remplacer entièrement la fonction `rechercher_marches` par :

```python
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
    colonnes: list[ColonneMarche] | None = None,
) -> dict:
    """Recherche paginée de marchés publics (DECP).

    Filtres nommés : acheteur_id, titulaire_id, cpv (code CPV, correspondance
    partielle), objet_contient (texte de l'objet), montant_min, montant_max,
    date_min / date_max (format YYYY-MM-DD, sur dateNotification),
    departement (code département de l'acheteur).
    filtres_avances : dict optionnel {"colonne__operateur": valeur} pour les
    besoins pointus. Colonnes et opérateurs disponibles via l'outil
    schema_donnees().
    colonnes : liste optionnelle de colonnes à renvoyer. Par défaut, un jeu
    standard (uid, objet, montant, dateNotification, codeCPV, acheteur_id,
    acheteur_nom, acheteur_departement_code, titulaire_id, titulaire_nom). Si
    fournie, REMPLACE le jeu par défaut (le champ uid reste toujours présent).
    Colonnes disponibles via schema_donnees().colonnes_disponibles.
    Chaque marché renvoyé contient en plus un champ `lien` (URL de la fiche
    marché sur colibre).
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
        colonnes=colonnes,
    )
```

- [ ] **Step 5: Lancer les tests pour vérifier le succès**

Run: `uv run pytest tests/mcp/test_tools.py -v`
Expected: PASS (tous).

- [ ] **Step 6: Vérification finale des tests MCP**

Run: `uv run pytest tests/mcp/ -v`
Expected: PASS (aucune régression dans les autres modules MCP).

- [ ] **Step 7: Commit**

```bash
pre-commit run --files src/mcp/tools.py tests/mcp/test_tools.py
git add src/mcp/tools.py tests/mcp/test_tools.py
git commit -m "feat(mcp): parametre colonnes (enum) pour rechercher_marches (#114)"
```

---

## Notes d'implémentation

- **Sécurité SQL** : `query_marches` (`src/db.py`) interpole les colonnes sans quoting. La validation `c not in SELECTABLE_COLUMNS` (Step 5, Task 1) est la barrière — ne pas la retirer. `SELECTABLE_COLUMNS` ne contient que des noms issus du schéma / du défaut, jamais d'entrée libre.
- **`Literal[SELECTABLE_COLUMNS]`** : `Literal` accepte un tuple de littéraux (vérifié : produit bien `items.enum` via `TypeAdapter`). L'ordre suit `MARCHES_COLUMNS` puis les colonnes filtrables.
- **`get_type_hints`** dans le test enum : `tools.py` n'utilise pas `from __future__ import annotations`, donc l'annotation est un objet résoluble ; `ColonneMarche` doit être importable au niveau module (Step 3).

```

```
