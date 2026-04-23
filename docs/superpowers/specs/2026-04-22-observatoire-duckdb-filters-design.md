# Observatoire — filtrage natif DuckDB

## Contexte

La page `/observatoire` construit ses cartes, ses téléchargements et sa prévisualisation
tabulaire à partir de la fonction `prepare_dashboard_data` (dans `src/utils/data.py`).
Aujourd'hui, cette fonction prend une `pl.LazyFrame` — typiquement obtenue par
`query_marches().lazy()` — et applique une série de filtres côté Polars.

`query_marches()` matérialise l'intégralité de la table `decp` (~1,5 M lignes) en
DataFrame Polars, même lorsqu'un utilisateur applique des filtres restrictifs. Les
filtres sont ensuite appliqués sur cet ensemble déjà matérialisé.

Le pattern utilisé par `_fetch_page_sql` (dans `src/utils/table.py`) montre comment
déléguer le filtrage à DuckDB :

1. Un traducteur (`filter_query_to_sql`, dans `src/utils/table_sql.py`) transforme le
   DSL utilisateur en `(where_sql, params)`.
2. `query_marches(where_sql=..., params=...)` ne matérialise que le sous-ensemble utile.

Ce spec décrit comment appliquer ce même pattern aux filtres de l'observatoire.

## Objectifs

- Réduire la consommation mémoire et le temps de chaque callback de l'observatoire
  en poussant le filtrage au niveau DuckDB.
- Conserver strictement la sémantique des filtres actuels (pas de régression
  fonctionnelle).
- Garder une frontière claire : un helper pur `dashboard_filters_to_sql` qui ne
  touche pas à la base, et une `prepare_dashboard_data` fine qui appelle DuckDB.

## Non-objectifs

- Pas de refonte de l'UI de filtres.
- Pas d'optimisation ou de cache supplémentaire autour de
  `_compute_dashboard_children` (déjà `@cache.memoize()`).
- Pas de changement du comportement par défaut (365 derniers jours quand aucune
  année n'est sélectionnée).

## Architecture

### Nouveau helper — `src/utils/table_sql.py`

```python
def dashboard_filters_to_sql(
    dashboard_year=None,
    dashboard_acheteur_id=None,
    dashboard_acheteur_categorie=None,
    dashboard_acheteur_departement_code=None,
    dashboard_titulaire_id=None,
    dashboard_titulaire_categorie=None,
    dashboard_titulaire_departement_code=None,
    dashboard_marche_type=None,
    dashboard_marche_objet=None,
    dashboard_marche_code_cpv=None,
    dashboard_marche_considerations_sociales=None,
    dashboard_marche_considerations_environnementales=None,
    dashboard_marche_techniques=None,
    dashboard_marche_innovant=None,
    dashboard_marche_sous_traitance_declaree=None,
    dashboard_montant_min=None,
    dashboard_montant_max=None,
) -> tuple[str, list]:
    """Traduit les filtres du tableau de bord en (where_clause, params) DuckDB."""
```

Fonction pure, sans accès à la base. Même signature que `prepare_dashboard_data`
actuelle (hors `lff`). Retourne `("TRUE", [])` si aucun filtre n'est actif.

### Réécriture — `prepare_dashboard_data` (`src/utils/data.py`)

```python
def prepare_dashboard_data(**filter_params) -> pl.DataFrame:
    where_sql, params = dashboard_filters_to_sql(**filter_params)
    return query_marches(where_sql=where_sql, params=params)
```

- **Signature** : suppression du paramètre `lff`. Retour `pl.DataFrame` (et non plus
  `pl.LazyFrame`).
- Les appelants qui ont besoin d'une LazyFrame appellent `.lazy()` sur le résultat.

### Appelants — `src/pages/observatoire.py`

Trois sites d'appel à adapter :

1. **`_compute_dashboard_children`** (ligne ~668) — on remplace

   ```python
   lff: pl.LazyFrame = query_marches().lazy()
   lff = prepare_dashboard_data(lff=lff, **filter_params)
   dff = lff.collect(engine="streaming")
   ```

   par

   ```python
   dff = prepare_dashboard_data(**filter_params)
   lff = dff.lazy()
   ```

   Les appels existants à `make_donut`, `get_distance_histogram`, `get_top_org_table`,
   `get_barchart_sources` continuent de recevoir `lff` ; `get_geographic_maps`
   continue de recevoir `dff`. `df_per_uid` est calculé à partir de `dff`.

2. **`download_observatoire`** (ligne ~791) —

   ```python
   dff = prepare_dashboard_data(**(filter_params or {}))
   if hidden_columns:
       dff = dff.drop(hidden_columns)
   def to_bytes(buffer):
       dff.write_excel(buffer, worksheet="DECP")
   ```

3. **`populate_preview_table`** (ligne ~882) —
   ```python
   dff = prepare_dashboard_data(**(filter_params or {}))
   return prepare_table_data(
       dff.lazy(),  # prepare_table_data accepte une LazyFrame
       ...
   )
   ```

## Traduction des filtres

| Filtre                                                    | Actuel (Polars)                                            | Cible (SQL DuckDB)                                             |
| --------------------------------------------------------- | ---------------------------------------------------------- | -------------------------------------------------------------- |
| `dashboard_year` (présent)                                | `dt.year() == int(year)`                                   | `YEAR("dateNotification") = ?`                                 |
| `dashboard_year` (absent) — comportement par défaut       | `> now - 365j`                                             | `"dateNotification" > ?` (datetime calculé à l'appel)          |
| `dashboard_acheteur_id`                                   | `str.contains(val)`                                        | `"acheteur_id" LIKE ?` avec `%val%`                            |
| `dashboard_acheteur_categorie`                            | `== val` (skip si acheteur_id présent)                     | `"acheteur_categorie" = ?`                                     |
| `dashboard_acheteur_departement_code`                     | `is_in(list)` (skip si acheteur_id présent)                | `"acheteur_departement_code" IN (?, ?, ...)`                   |
| `dashboard_titulaire_id`                                  | idem acheteur                                              | idem                                                           |
| `dashboard_titulaire_categorie`                           | idem                                                       | idem                                                           |
| `dashboard_titulaire_departement_code`                    | idem                                                       | idem                                                           |
| `dashboard_marche_type`                                   | `== val`                                                   | `"type" = ?`                                                   |
| `dashboard_marche_objet`                                  | `str.contains("(?i)val")`                                  | `"objet" ILIKE ?` avec `%val%`                                 |
| `dashboard_marche_code_cpv`                               | `str.starts_with(val)`                                     | `"codeCPV" LIKE ?` avec `val%`                                 |
| `dashboard_marche_techniques`                             | `str.split(", ").list.set_intersection(xs).list.len() > 0` | `list_has_any(string_split("techniques", ', '), ?::VARCHAR[])` |
| `dashboard_marche_considerations_sociales`                | idem                                                       | idem sur `"considerationsSociales"`                            |
| `dashboard_marche_considerations_environnementales`       | idem                                                       | idem sur `"considerationsEnvironnementales"`                   |
| `dashboard_marche_innovant` (`"oui"`/`"non"`, sinon skip) | `== val`                                                   | `"marcheInnovant" = ?`                                         |
| `dashboard_marche_sous_traitance_declaree`                | idem                                                       | `"sousTraitanceDeclaree" = ?`                                  |
| `dashboard_montant_min`                                   | `>= val`                                                   | `"montant" >= ?`                                               |
| `dashboard_montant_max`                                   | `<= val`                                                   | `"montant" <= ?`                                               |

**Logique conditionnelle conservée** : si `dashboard_acheteur_id` est fourni, les filtres
`categorie` et `departement_code` acheteur sont ignorés (même chose pour titulaire).

**Traitement des valeurs spéciales** :

- `dashboard_marche_innovant` / `dashboard_marche_sous_traitance_declaree` : valeur
  `"all"` ou falsy → aucun filtre ajouté.
- `dashboard_year` : converti en `int` avant injection.
- `dashboard_montant_min` / `_max` : `None` → aucun filtre (distinct de `0`, qui reste
  un filtre valide via `>=` ou `<=`).

**Sécurité SQL** : toutes les valeurs utilisateurs passent par DuckDB en paramètres liés
(`?`). Seuls des noms de colonnes statiques (contrôlés par le code) sont injectés dans le
fragment SQL via `f"..."`. Pas de différence avec le pattern existant de
`filter_query_to_sql`.

## Tests

### Unitaires (nouveaux)

Nouveau fichier `tests/test_dashboard_filters_to_sql.py` :

- Cas vide → `("TRUE", [])`.
- Un seul filtre simple (année, type, etc.) → fragment SQL et params attendus.
- Filtre montant min/max (migration de l'actuel `test_010_observatoire_montant_filter`).
- Filtre liste (techniques, considerationsSociales) → usage de `list_has_any`.
- Filtre acheteur_id fourni → catégorie/département acheteur ignorés.
- Filtre `"all"` / `None` sur innovant/sous_traitance → aucun fragment ajouté.
- Comportement par défaut sans année → fragment `"dateNotification" > ?` avec un param
  datetime à ~365 j dans le passé (tolérance de quelques secondes).

### Intégration (nouveau, léger)

Un test qui appelle `prepare_dashboard_data` contre `tests/test.parquet` avec un ou
deux filtres connus, vérifie le `height` et la bonne nature du retour (`pl.DataFrame`).

### Test Selenium existant

`test_009_observatoire_filter_persistence` et `test_008_observatoire_navigation_from_search`
ne touchent pas à la signature ; ils doivent continuer à passer.

## Risques et migration

- **Risque sémantique** : la fonction Polars `str.contains` utilisée pour les IDs est
  un regex. Les utilisateurs attendent probablement un contains littéral sur un SIRET
  (14 chiffres). Le passage à `LIKE '%val%'` est neutre si la valeur ne contient pas de
  caractère spécial regex — ce qui est le cas pour des SIRET. **Hypothèse** acceptée :
  le contenu `dashboard_acheteur_id`/`dashboard_titulaire_id` est alphanumérique.
- **Risque de drift du cache** : la date "365 derniers jours" n'est pas incluse dans
  la clé de cache de `_compute_dashboard_children`. C'est un comportement pré-existant
  ; non traité par ce spec.
- **Import circulaire** : `src/utils/data.py` importe déjà depuis `src/db.py`.
  `src/utils/table_sql.py` importe depuis `src/utils/table.py`. Pas de nouveau cycle.

## Succès

- Les 3 callbacks de l'observatoire restent fonctionnellement équivalents.
- Les tests unitaires et d'intégration passent.
- Une inspection manuelle confirme un temps d'exécution réduit sur un filtre
  sélectif (par ex. un département + une année).
