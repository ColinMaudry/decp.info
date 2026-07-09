# Design — Serveur MCP colibre, lot 1 : les tools (scope A de l'issue #111)

**Date** : 2026-07-09
**Issue** : #111 — Serveur MCP des données colibre, conditionné à l'abonnement
**Périmètre de CE design** : **A seulement** — exposer des fonctions métier comme
_tools_ MCP via le décorateur `@mcp_enabled` de Dash. **Sans authentification.**
La couche d'autorisation OAuth 2.0 + gate abonnement fera l'objet d'un design
séparé (scope B).

## Contexte

- La migration Dash 4.x (#101) est terminée (Dash 4.4). Le serveur MCP de Dash est
  disponible à partir de Dash 4.3.0 → prérequis satisfait.
- Dash fournit la couche protocole MCP (`enable_mcp=True`, décorateur
  `@mcp_enabled`, `configure_mcp_server(...)`). Dash **n'implémente pas**
  l'authentification (cf. `/dash-mcp/auth`) → c'est le scope B, hors de ce design.
- Les **DECP sont des données publiques ouvertes**. Exposer recherche/stats en MCP
  n'est donc pas une fuite de confidentialité ; le gate abonnement (scope B) relève
  du contrôle d'accès / monétisation, pas du secret. Conséquence : le scope A peut
  tourner en dev/local sans risque de données.

## Ce qui existe déjà et qu'on réutilise

- `src/db.py` : `query_marches(where_sql, params, columns, order_by, limit, offset)`,
  `count_marches(where_sql, params)`, `aggregate_marches(select_sql, where_sql, params, group_by, order_by, limit, offset)` — accès DuckDB paramétré renvoyant du
  Polars.
- `src/api/filters.py` : `build_where(args, schema) -> (where_sql, params, order_by)`
  et `parse_aggregators(...)` — moteur de filtres `col__op=valeur` déjà utilisé par
  l'API REST (`src/api/routes.py`). **On le réutilise tel quel** pour que MCP et REST
  partagent la même sémantique de filtrage.
- `src/utils/search.py` : `search_org(dff, query, org_type)` — recherche floue par
  nom sur les acheteurs/titulaires (déjà utilisée par la page `/`).
- `src/utils/tracking.py` : `track_search(query, category)` — envoi direct à l'API
  HTTP de tracking Matomo (`matomo.php`).

## Approches considérées

- **A — Module MCP fin réutilisant la couche données existante (RETENU).**
  Nouveau package `src/mcp/`, 4 fonctions `@mcp_enabled` appelant directement
  `db.*` / `filters.build_where` / `search_org`. Le « service layer » partagé
  qu'on voudrait existe déjà (`src/db.py` + `src/api/filters.py`) → peu de code neuf.
- **B — Extraire un service commun** partagé entre `api/routes.py` et MCP. Meilleure
  déduplication à terme mais gros refactor de l'API REST pour un gain marginal (la
  logique est déjà factorisée). Rejeté (YAGNI).
- **C — MCP appelle l'API REST en HTTP.** Ajoute un saut HTTP interne en process,
  perd le typage. Rejeté.

## Architecture

### Arborescence

```
src/mcp/
  __init__.py
  tools.py          # les 4 fonctions @mcp_enabled (surface MCP)
  serialization.py  # Polars → JSON propre (dates ISO, montants, None-safe)
  stats.py          # helpers d'agrégation acheteur/titulaire, partagés par les 2 tools stats_*
```

### Activation (dans `src/app.py`, là où `Dash(...)` est construit)

```python
from dash.mcp import configure_mcp_server

app = Dash(__name__, ..., enable_mcp=os.getenv("DASH_MCP_ENABLED") == "true")

configure_mcp_server(
    include_layout=False,
    include_callbacks=False,
    include_pages=False,
    include_clientside_callbacks=False,
)  # n'expose QUE les fonctions @mcp_enabled — aucun callback/layout/page d'UI

import src.mcp.tools  # noqa: E402,F401 — l'import enregistre les @mcp_enabled
```

**Sécurité (point de vigilance #111)** : en coupant `include_callbacks/layout/pages/ clientside`, aucun callback d'UI ni nom interne (type `get_data_from_s3`) n'est
exposé. La surface se limite aux 4 tools nommés proprement, avec docstrings
maîtrisées.

### Isolation des unités

- `tools.py` : **uniquement** la surface MCP (signatures, docstrings destinées à
  l'agent, validation des arguments, appels aux helpers). Ne contient pas de SQL.
- `stats.py` : logique d'agrégation acheteur/titulaire, testable sans MCP.
- `serialization.py` : conversion Polars → structures JSON-sérialisables, testable
  isolément.

## Les 4 tools

Tous renvoient des structures JSON-sérialisables (dict / list). Montants en euros
(float ou int), dates en ISO 8601 (`YYYY-MM-DD`), valeurs manquantes en `null`.
Les docstrings sont exposées à l'agent (`expose_docstring=True`) : ce sont elles qui
documentent l'outil côté client.

### 1. `rechercher_organisations(query: str, type: str = "acheteur", limite: int = 20)`

- `type` ∈ `{"acheteur", "titulaire"}`.
- Réutilise `search_org` sur la frame correspondante (mêmes données que la page `/`).
- Sortie : `[{ "id", "nom", "departement", "commune" }]`, triée par pertinence,
  tronquée à `limite`.
- Rôle : **résoudre un nom → id** pour alimenter `stats_acheteur` / `stats_titulaire`.

### 2. `stats_acheteur(acheteur_id: str)`

Réutilise `aggregate_marches` avec un `where` filtrant sur `acheteur_id`.
Sortie :

```json
{
  "identite": { "id", "nom", "departement", "commune" },
  "nb_marches": 0,
  "montant_total": 0,
  "repartition_annuelle": [ { "annee", "nb_marches", "montant_total" } ],
  "top_titulaires": [ { "id", "nom", "nb_marches", "montant_total" } ],
  "top_cpv": [ { "cpv", "libelle", "nb_marches" } ]
}
```

- `top_*` limités (ex. 10). Si `acheteur_id` inconnu → `nb_marches: 0` et listes vides
  (pas d'erreur).

### 3. `stats_titulaire(titulaire_id: str)`

Symétrique de `stats_acheteur` : `top_acheteurs` au lieu de `top_titulaires`,
montants remportés.

### 4. `rechercher_marches(...)` — signature **hybride**

```python
rechercher_marches(
    acheteur_id: str | None = None,
    titulaire_id: str | None = None,
    cpv: str | None = None,
    objet_contient: str | None = None,
    montant_min: float | None = None,
    montant_max: float | None = None,
    date_min: str | None = None,   # ISO YYYY-MM-DD (dateNotification)
    date_max: str | None = None,
    departement: str | None = None,
    page: int = 1,
    filtres_avances: dict | None = None,  # échappatoire moteur générique
)
```

- Les paramètres nommés sont traduits en tuples `col__op` (ex.
  `montant_min` → `("montant__greater", ...)`, `objet_contient` →
  `("objet__contains", ...)`, `date_min` → `("dateNotification__greater", ...)`).
- `departement` mappe sur **`acheteur_departement_code`** (intention de requête la
  plus courante). Pour filtrer sur le département du titulaire ou du lieu
  d'exécution, l'agent passe par `filtres_avances`.
- `filtres_avances` : dict `{"col__op": valeur}` passant au moteur générique complet,
  **fusionné** avec les paramètres nommés. Couvre toute colonne/opérateur supportés
  par l'API REST.
- L'ensemble passe à `filters.build_where(args, duckdb_schema)` puis
  `db.query_marches` / `db.count_marches` → **même sémantique que l'API REST**.
- Pagination : `page_size` **fixe** (ex. 50), pagination par `page` (offset calculé).
- Sortie :

```json
{
  "meta": { "page": 1, "page_size": 50, "total": 0 },
  "marches": [
    {
      /* colonnes principales du marché */
    }
  ]
}
```

- Erreurs de filtre (`FilterError`) → message d'erreur clair renvoyé à l'agent (pas
  d'exception brute).

## Tracking Matomo des appels MCP

Nouveau helper dédié dans `src/utils/tracking.py` (on **ne** surcharge **pas**
`track_search`, qui gate sur `len(query) >= 4` et attend une requête texte) :

```python
def track_mcp_tool(tool_name: str, query: str | None = None) -> None:
    ...
```

- Même pattern que `track_search` : n'émet que si `not DEVELOPMENT` **et**
  `MATOMO_DOMAIN` défini. Best-effort (ne doit jamais faire échouer l'appel du tool).
- Paramètres envoyés à `matomo.php` :
  - `action_name = "MCP"` (hiérarchie `f"MCP / {tool_name}"` acceptable pour un arbre
    lisible dans le rapport Actions),
  - `dimension1 = tool_name`,
  - `search` / `search_cat` en plus quand l'outil a une requête texte
    (`rechercher_organisations`, `rechercher_marches`).
- Chaque tool appelle `track_mcp_tool(...)` en début d'exécution.
- **Prérequis de déploiement Matomo** : créer un _Custom Dimension_ slot 1, scope
  **Action**, côté admin Matomo. Sinon `dimension1` est ignoré silencieusement.

## Déploiement / gating

- Activation via variable d'environnement `DASH_MCP_ENABLED` (Dash lit nativement
  cette variable ; on la reflète dans le constructeur).
- **Off par défaut.** Activé en dev/local uniquement.
- **Pas activé en prod tant que le scope B (OAuth + gate abonnement) n'est pas
  livré** — sinon le serveur MCP serait ouvert sans contrôle d'accès (feature
  payante + coût compute).
- Documenter la variable dans `.template.env`.

## Tests

- Tests unitaires sur les 4 fonctions (données `tests/test.parquet`) :
  - `rechercher_organisations` : résultats non vides, tri, `limite`, `type` invalide.
  - `stats_acheteur` / `stats_titulaire` : forme de sortie, id inconnu → vides,
    troncature des `top_*`.
  - `rechercher_marches` : fusion params nommés ↔ `filtres_avances`, pagination
    (`meta.total`, `page`), `FilterError` → message propre.
  - `serialization` : dates ISO, `null`, montants.
- Smoke test : après import de `src.mcp.tools`, le registre MCP contient bien les
  4 tools attendus (pas de test du protocole MCP de bout en bout, qui nécessiterait
  un client MCP).
- `tests/test.parquet` étant réduit, vérifier que les colonnes utilisées (cpv,
  montant, dateNotification, acheteur_id, titulaire_id, departement) y sont
  présentes ; sinon compléter la fixture ou marquer les cas concernés.

## Hors périmètre (→ scope B, design séparé)

- Serveur d'autorisation OAuth 2.0 conforme à la spec MCP (2025-06-18) :
  metadata protected-resource, PKCE, dynamic client registration.
- Branchement du gate `subscriptions.has_active_subscription(user_id)` sur
  l'autorisation MCP.
- Documentation de connexion côté client (`claude mcp add …`).
