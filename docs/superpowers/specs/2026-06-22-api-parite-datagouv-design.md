# Parité de l'API decp.info avec tabular-api (data.gouv.fr) — opérateurs manquants

**Date :** 2026-06-22
**Périmètre :** `count_results` + `differs` + suite d'agrégation. **Hors périmètre :** le paramètre réservé `or` (itération dédiée ultérieure).

## Contexte

L'API `/api/v1/data` de decp.info reproduit le schéma de requête de
`tabular-api` (`datagouv/api-tabular`), qui sert la même donnée DECP sur
data.gouv.fr. L'objectif est d'atteindre la parité sur les **opérateurs**
de filtrage/agrégation, pour qu'une requête écrite pour data.gouv.fr
fonctionne à l'identique sur decp.info.

Source faisant autorité du comportement cible : `api_tabular/core/query.py`
du dépôt `datagouv/api-tabular`. Tous les comportements ci-dessous ont été
vérifiés en direct contre la ressource DECP
`22847056-61df-452d-837d-8b8ceadbfc52`.

### Écart constaté

Opérateurs présents chez data.gouv.fr et absents de decp.info :

| Mot-clé                             | Nature                              |
| ----------------------------------- | ----------------------------------- |
| `differs`                           | opérateur de filtre                 |
| `groupby`                           | drapeau d'agrégation (sans valeur)  |
| `count`, `sum`, `avg`, `min`, `max` | drapeaux d'agrégation (sans valeur) |

De plus, le paramètre réservé `count=true|false` de decp.info entre en
collision avec l'opérateur d'agrégation `count` de data.gouv.fr.

État courant pertinent :

- `src/api/filters.py` : `OPERATORS`, `RESERVED_PARAMS`, `build_where()`.
- `src/api/routes.py` : route `data()`, doc swagger des paramètres.
- `src/db.py` : `query_marches()`, `count_marches()`.

## Objectifs

1. Renommer le paramètre réservé `count` → `count_results` (valeurs
   `true|false`, défaut `true`), libérant `count` comme opérateur.
2. Ajouter l'opérateur de filtre `differs`.
3. Ajouter les opérateurs d'agrégation `groupby`, `count`, `sum`, `avg`,
   `min`, `max`, avec la même forme de réponse que data.gouv.fr.
4. **Documenter** chaque mot-clé dans le Swagger UI de l'API, de façon à
   mettre en valeur les possibilités de l'API decp.info.

Non-objectifs : le paramètre `or` (grammaire récursive imbriquée), les
opérateurs `groupby`/agrégats appliqués via `or`, toute évolution du
benchmark (sera traitée après).

## Conception

### 1. Renommage `count` → `count_results`

- `RESERVED_PARAMS` : `{"page", "page_size", "columns", "count_results"}`.
- `routes.data()` : lire `request.args.get("count_results", "true")`.
- Doc swagger : remplacer le paramètre `count` par `count_results`, même
  description (« inclure le total `COUNT(*)` ; `false` pour accélérer »).
- Le mot `count` n'est donc plus réservé ; il est interprété comme
  opérateur d'agrégation (section 3).

**Rupture de contrat :** un client qui passait `count=false` verra ce
paramètre ré-interprété. Sans conséquence : l'API n'est pas encore en
production, on peut donc itérer librement.

### 2. Opérateur `differs`

Sémantique data.gouv.fr : `col__differs=val` → PostgREST `isdistinct`, soit
`IS DISTINCT FROM` (≠ null-safe : `NULL differs 44` est vrai).

- Ajouter `"differs"` à `OPERATORS`.
- Dans `build_where()`, après coercition de la valeur :
  `where_parts.append('"col" IS DISTINCT FROM ?')` ; `params.append(v)`.
- DuckDB supporte nativement `IS DISTINCT FROM`.

### 3. Opérateurs d'agrégation

#### Forme des requêtes (vérifiée)

Drapeaux **sans valeur** dans la query string :
`?acheteur_departement_code__groupby&uid__count&montant__sum&montant__avg&montant__min&montant__max`

Une valeur (`__groupby=1`) est un cas d'erreur côté data.gouv.fr ; on
n'impose pas cette stricte interdiction mais on accepte la forme sans
valeur (Werkzeug fournit alors la valeur `""`).

Opérateurs : `groupby`, `count`, `sum`, `avg`, `min`, `max`.

#### Forme de la réponse (vérifiée)

```
SELECT <cols groupby>, FN("<col>") AS "<col>__<op>", ...
FROM decp
WHERE <filtres>
GROUP BY <cols groupby>
LIMIT <page_size> OFFSET <offset>
```

- Colonnes de sortie : la colonne `groupby` garde son nom ; chaque agrégat
  est nommé `"<colonne>__<opérateur>"` (ex. `uid__count`, `montant__sum`).
- `meta` : `{"page", "page_size"}` **sans `total`** (data.gouv.fr n'en
  renvoie pas en mode agrégation). `count_results` est ignoré dans ce mode.
- Pas de tri par défaut.
- Les filtres `WHERE` (y compris `differs`) restent appliqués.

#### Contraintes répliquées

- `columns` + agrégation → erreur 400 (`columns ne peut pas être combiné avec des agrégateurs`). Vérifié identique chez data.gouv.fr.
- Un agrégat (`count`/`sum`/…) sans `groupby` est autorisé (agrégat global,
  une ligne).

#### Architecture

Nouvelle fonction de parsing dans `src/api/filters.py` :

```
parse_aggregators(args, schema) -> AggregationSpec | None
```

- Retourne `None` si aucun opérateur d'agrégation présent → la route suit
  le chemin existant.
- Sinon retourne les colonnes `groupby` et la liste des agrégats
  `(fonction_sql, colonne, alias)`.
- Valide que chaque colonne existe dans le schéma ; opérateur inconnu →
  `FilterError`.

`build_where()` est inchangé pour WHERE/ORDER ; il continue d'ignorer les
clés réservées et **doit ignorer les drapeaux d'agrégation** (ne pas les
traiter comme des filtres). Comme les drapeaux d'agrégation arrivent comme
`(col__op, "")`, et que `op` ∈ agrégateurs, `build_where` les saute.

Nouvelle fonction dans `src/db.py` :

```
aggregate_marches(select_sql, where_sql, params, group_by, limit, offset) -> pl.DataFrame
```

- `select_sql` et `group_by` sont des fragments SQL construits depuis des
  noms de colonnes validés contre le schéma (jamais de valeur utilisateur
  libre) ; les valeurs de filtre passent par le binding `?`.

Orchestration dans `routes.data()` :

```
agg = parse_aggregators(args, schema)
where_sql, params, order_sql = build_where(args, schema)   # filtres seuls
if agg:
    if columns: -> abort(400)
    df = aggregate_marches(agg.select_sql, where_sql, params, agg.group_by, page_size, offset)
    meta = {"page", "page_size"}        # pas de total
else:
    <chemin existant>
```

### 4. Documentation (Swagger UI)

La doc de l'API est générée par flask-smorest et exposée sur
`/api/v1/swagger`, pilotée par le docstring de `routes.data()` et le bloc
`@bp.doc(parameters=[...])`. C'est la surface de documentation à enrichir
(aucune autre page de doc API n'existe).

À mettre à jour :

- Remplacer le paramètre `count` par `count_results` (même description).
- Étendre la description du paramètre dynamique `<colonne>__<opérateur>`
  avec une **définition d'une ligne par opérateur**, regroupés par
  catégorie :
  - _Filtres_ : `exact`, `differs`, `contains`, `notcontains`, `in`,
    `notin`, `less`, `greater`, `strictly_less`, `strictly_greater`,
    `isnull`, `isnotnull`, `sort`.
  - _Agrégation_ (drapeaux sans valeur) : `groupby`, `count`, `sum`,
    `avg`, `min`, `max`.
- Décrire le **mode agrégation** : drapeaux sans valeur, réponse en lignes
  groupées, colonnes `col__op`, `columns` interdit, pas de `total`.
- Mettre à jour le docstring de `data()` (visible dans Swagger) en
  cohérence, avec au moins un exemple de requête d'agrégation.

Objectif éditorial : un lecteur qui découvre l'API doit comprendre, depuis
le seul Swagger UI, l'ensemble des opérateurs disponibles et comment s'en
servir.

### Sécurité SQL

Les noms de colonnes proviennent du schéma DuckDB validé (`col in schema`),
jamais interpolés depuis une valeur arbitraire ; les fonctions d'agrégation
sont une liste blanche fixe (`COUNT/SUM/AVG/MIN/MAX`). Les valeurs de
filtre restent liées par paramètres `?`. Aucun chemin n'interpole de valeur
utilisateur dans le SQL.

## Tests

Tests existants à adapter (renommage `count` → `count_results`).

Nouveaux tests (`tests/` API) :

- `differs` : exclut les lignes égales, inclut les NULL.
- agrégation `groupby` + `count` : nombre de groupes, noms de colonnes
  `col__count`.
- agrégation multiple `groupby`+`count`+`sum`+`avg`+`min`+`max` : alias et
  types corrects, `meta` sans `total`.
- agrégat sans `groupby` : une ligne.
- `groupby` + filtre `WHERE` : le filtre s'applique avant l'agrégation.
- `columns` + agrégation : 400.
- `count_results=false` : réponse sans `total` (chemin non-agrégé).
- non-régression : opérateurs existants inchangés.
- doc : le spec OpenAPI généré (`/api/v1/openapi.json`) référence
  `count_results` et mentionne les nouveaux opérateurs (vérif légère, p. ex.
  présence des chaînes attendues).

Comparaison de référence : pour quelques requêtes, les valeurs agrégées
doivent correspondre à celles renvoyées par data.gouv.fr sur la même
ressource (aux différences de fraîcheur de données près).

## Gestion des erreurs

- Opérateur inconnu, colonne inconnue → `FilterError` → 400 (existant).
- `columns` + agrégation → 400 avec message explicite.
- Valeur non coercible pour `differs` → `FilterError` (existant via
  `_coerce`).
