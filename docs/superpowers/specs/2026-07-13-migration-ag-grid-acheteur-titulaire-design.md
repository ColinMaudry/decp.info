# Migration des tables vers Dash AG Grid — Design (Lot 2a : `acheteur.py` + `titulaire.py`)

- **Issues** : #41 (migration AG Grid)
- **Date** : 2026-07-13
- **Fait suite à** : `docs/superpowers/specs/2026-07-09-migration-ag-grid-design.md` (Lot 1, `tableau.py`)

## Contexte

Le Lot 1 a migré `tableau.py` de `dash_table.DataTable` vers `dag.AgGrid`, avec un moteur de requête générique (AST booléen → SQL DuckDB, `src/utils/query_ast.py`) et une datasource server-side réutilisable (`fetch_grid_page`, `grid_column_defs`, `apply_persisted_layout` dans `src/utils/grid.py`, déjà paramétrée par `base_where_sql`/`base_params`). Depuis, `ag_grid()` (`src/figures.py`) a aussi reçu un thème ("brique", accentColor `rgb(179, 56, 33)`, police Inter) qui remplace l'apparence de base initialement conservée au Lot 1.

`acheteur.py` et `titulaire.py` sont deux pages quasi-identiques (même auteur, même pattern, juste paramétrées par le type d'entité) affichant les marchés d'un acheteur ou d'un titulaire donné. Chacune a :

- un tableau principal déjà paginé/filtré/trié **server-side** sur DuckDB, mais via l'ancien DSL `DataTable` (`filter_query`/`sort_by`, mono-condition — la même limite qui causait le bug corrigé sur `/tableau`, cf. commit `117ce9a`),
- deux boutons d'export Excel (toutes les données de la fiche / données filtrées, ce dernier via pipeline Polars),
- un sélecteur de colonnes, un bouton Réinitialiser,
- un petit tableau "top 10" agrégé (`get_top_org_table`, données déjà chargées, pagination/filtre natifs sans aller-retour serveur).

Dash abandonnant `dash_table.DataTable`, cette migration doit couvrir ces deux pages avant que la dépréciation ne devienne bloquante.

## Objectifs

1. **Préserver les fonctionnalités existantes** (filtre/tri/pagination server-side scopés à l'entité, export x2, sélecteur de colonnes, reset) en passant à `dag.AgGrid`.
2. **Réutiliser au maximum l'infrastructure du Lot 1** (`ag_grid()`, `grid_column_defs()`, `fetch_grid_page()`, `apply_persisted_layout()`, thème brique) plutôt que de la redupliquer.
3. **Factoriser** la logique commune à acheteur.py/titulaire.py (déjà dupliquée aujourd'hui) dans un nouveau module partagé, plutôt que de dupliquer une troisième fois la logique AG Grid.
4. **Gagner le filtre multi-conditions (ET/OU)** gratuitement, comme sur `/tableau`, en remplaçant le DSL `filter_query` par le `filterModel` AG Grid + AST.

## Non-objectifs (reportés)

- `observatoire.py` : sous-projet séparé (Lot 2b), architecture de données différente (jusqu'à ~1,5M lignes matérialisées, cf. `prepare_dashboard_data`).
- `recherche.py`, `admin/liste.py`, `figures.make_table` (page a-propos/sources) : Lot 3, pages plus simples.
- #97 (requêtes booléennes texte libre, abonnés) — inchangé, le moteur AST du Lot 1 reste le socle.
- Suppression de l'ancien DSL (`filter_query_to_sql`, `clean_filters`) : reportée à la fin du Lot 3 tant que d'autres pages s'en servent encore.

## Décisions d'architecture

### Nouveau module `src/utils/entity_grid.py`

Factorise la logique commune aux deux pages, paramétrée par `org_type: Literal["acheteur", "titulaire"]` :

- `entity_grid_column_defs(org_type, hidden_columns, column_state) -> list[dict]` : `grid_column_defs()` du Lot 1 + `apply_persisted_layout()` par-dessus (réutilisés tels quels, aucune modif requise).
- `fetch_entity_grid_page(filter_model, sort_model, start_row, end_row, base_where_sql, base_params) -> (rows, total, total_unique)` : appelle directement `fetch_grid_page()` du Lot 1 (déjà générique, aucune modif requise).
- `export_entity_grid(filter_model, sort_model, hidden_columns, base_where_sql, base_params) -> pl.DataFrame` : variante de `export_dataframe()` du Lot 1, étendue avec `base_where_sql`/`base_params` (seule extension nécessaire côté `grid.py`).
- `entity_ag_grid(grid_id: dict, ...) -> dag.AgGrid` : appelle `ag_grid()` du Lot 1 (même thème, même config) avec un `id` pattern-matching au lieu d'une string.
- Fabrique de callbacks pattern-matching partagée (datasource, reset, application des colonnes masquées, export filtré) enregistrée une fois, paramétrée par `org_type` — évite de dupliquer les `@callback` dans `acheteur.py` et `titulaire.py`.

`acheteur.py`/`titulaire.py` gardent leur fichier propre (URL, infos annuaire, carte, stats, histogramme, bouton "toutes les données" — tout ce qui n'est pas la grille) et appellent ce module pour tout ce qui est grille.

### `layout` devient une fonction

`layout = [...]` (liste statique) devient `def layout(acheteur_id=None, **kwargs): ...` (resp. `titulaire_id`) — mécanisme standard Dash pour les routes `path_template` dynamiques. Dash rappelle cette fonction à chaque navigation vers `/acheteurs/<acheteur_id>`, ce qui permet de connaître `acheteur_id` **au moment de construire le layout**, sans passer par `dcc.Location`.

**Périmètre du changement** : seuls la grille et les éléments qui doivent être scopés par entité changent d'id/de câblage. Tout le reste (siret, nom, carte, stats, histogramme, bouton "toutes les données", top 10) **garde exactement son câblage actuel** (id fixe + `Input("acheteur_url", "pathname")`) — `dcc.Location(id="acheteur_url")` est conservé pour ces callbacks, qui n'ont pas besoin de changer.

### Id pattern-matching de la grille

```python
grid_id = {"type": "acheteur-grid", "acheteur_id": acheteur_id, "year": ach_year_at_render}
```

Comme `ach_year` (dropdown, pas dans l'URL) n'est connu qu'au runtime et non au premier rendu du `layout()`, l'id inclut une valeur par défaut (`"Toutes les années"`) à la construction ; un changement d'année **remonte la grille** (nouvel id via un `Output(html.Div, "children")` qui reconstruit le composant `dag.AgGrid` avec le nouvel id) plutôt que de tenter un rafraîchissement in-place — le row model infinite d'AG Grid n'a pas de mécanisme pour se rafraîchir sur un changement externe au filtre/tri/scroll. Effet de bord accepté : `filterModel` se réinitialise aussi au changement d'année (raisonnable, non-régression par rapport au DSL actuel qui ne le préservait pas non plus explicitement).

Callbacks pattern-matching (dans `entity_grid.py`, via `MATCH`) :

- datasource : `Input({"type": f"{org_type}-grid", "acheteur_id": MATCH, "year": MATCH}, "getRowsRequest")` → `Output(..., "getRowsResponse")`.
- reset : bouton (id fixe, hors grille) → `Output({"type": f"{org_type}-grid", ...}, "filterModel", allow_duplicate=True)` avec `ALL` (un seul reset visible à la fois, mais `ALL` reste nécessaire car ce n'est pas le composant qui a émis l'événement).
- export filtré : lit `State({"type": f"{org_type}-grid", ...}, "filterModel")`/`"sortModel"` via `ALL` (un seul match actif).

### Persistance découplée : `filterModel` vs `columnState`

- **`filterModel`** : persistance native AG Grid (`persistence=True, persistence_type="local", persisted_props=["filterModel"]`) sur l'id pattern-matching ci-dessus → une entrée localStorage distincte par `(acheteur_id, year)`, isolée par fiche.
- **`columnState`** : **pas** de persistance native AG Grid pour cette prop (elle serait scopée par le même id, donc par entité — indésirable : la disposition des colonnes est une préférence utilisateur globale). À la place :
  - un `dcc.Store(id="entity-grid-columns-state", storage_type="local")` **partagé entre acheteur.py et titulaire.py** (même schéma DECP dans les deux cas),
  - un callback pattern-matching `Input({"type": ..., ...}, "columnState")` (`ALL`) → `Output("entity-grid-columns-state", "data")` écrit dedans à chaque changement,
  - `entity_grid_column_defs()` lit ce store et réapplique largeur/ordre via `apply_persisted_layout()` (déjà prévu pour ça) avant de construire les `columnDefs` de la grille, peu importe l'acheteur/titulaire affiché.

## Composants non-grille inchangés

`update_acheteur_infos`, `update_acheteur_map`, `update_acheteur_stats`, `update_download_button_acheteur`, `download_acheteur_data`, `get_top_titulaires` (callback autour du top 10, cf. ci-dessous), `toggle_acheteur_columns`, `update_acheteur_distance_histogram` (et équivalents titulaire) : **aucun changement**, toujours pilotés par `Input("acheteur_url", "pathname")`/`Input("acheteur_year", "value")` sur des id fixes.

## Tableaux "top 10" (`get_top_org_table`)

Migrés vers AG Grid **simple** (row model par défaut client-side, `rowData` fournie directement, pas de `getRowsRequest`) :

- Nouvelle fonction dans `figures.py`, ex. `get_top_org_ag_grid(data, org_type, extra_columns, filters=True)`, même signature/usage que l'actuelle `get_top_org_table`, réutilise `ag_grid()` (même thème) mais avec ses **propres** `columnDefs` dérivés de `setup_table_columns()` (le sous-ensemble de colonnes du top 10 n'est pas le schéma DECP complet — pas de réutilisation de `grid_column_defs()` ici).
- Pas de persistance (petit tableau statique, régénéré à chaque changement d'acheteur/année de toute façon).
- Utilisé par `acheteur.py` (`top10_titulaires`) et `titulaire.py` (`top10_acheteurs`). `observatoire.py` réutilise la même fonction dans son propre sous-projet (Lot 2b) sans travail supplémentaire ici.

## Export Excel

Les 2 boutons existants sont conservés (rôles différents, confirmé) :

- **"Téléchargement au format Excel"** (`download_acheteur_data`/`download_titulaire_data`) : inchangé, toutes les données de la fiche pour l'année sélectionnée, ignore l'état de la grille.
- **Bouton "filtré"** (`btn-download-filtered-data-acheteur`/`titulaire`) : passe du pipeline Polars (`filter_table_data`/`sort_table_data` sur `filter_query`/`sort_by`) au chemin DuckDB du Lot 1 — `export_entity_grid()` recompile `filterModel`/`sortModel` courants (lus via `State` pattern-matching `ALL`) → AST → SQL, scopé par `base_where_sql`/`base_params` de l'entité. Seuil de 65 000 lignes conservé (dérivé du `total` retourné par `fetch_grid_page`).

## Dépendances

Aucune nouvelle dépendance (dash-ag-grid déjà installé au Lot 1).

## Cas limites & erreurs

- Mêmes garanties que le Lot 1 : colonnes validées contre le schéma, valeurs toujours paramétrées, `getRowsRequest is None` → `no_update`, colonne de filtre inconnue → ignorée + `logger.warning`.
- Changement d'année pendant un chargement de bloc en cours : la grille est remontée (nouvel id), l'ancienne requête devient orpheline sans effet (comportement standard React/Dash au remount).
- `columnState` vide au premier chargement (nouvel utilisateur) : `apply_persisted_layout(defs, None)` retourne `defs` inchangés (déjà géré, cf. Lot 1).

## Tests

- **Unitaires `entity_grid.py`** : datasource scopée (`base_where_sql`/`base_params` appliqués correctement pour acheteur vs titulaire), export scopé, `apply_persisted_layout` avec le store partagé.
- **Unitaires `figures.get_top_org_ag_grid`** : colonnes dérivées correctement, pas de persistance.
- **Mise à jour `tests/test_main.py`** : `test_002_filter_persistence` (sélecteurs `.marches_table th[data-dash-column=...]` → équivalents AG Grid) et `test_003_tableau_download` (signatures `filter_query`/`sort_by` → `filterModel`/`sortModel` pour les callbacks d'export acheteur/titulaire).
- Suite complète `uv run pytest` uniquement en fin de lot.

## Décisions tranchées

- Factorisation dans `src/utils/entity_grid.py` (pas de duplication acheteur/titulaire pour la nouvelle logique).
- `layout()` dynamique + pattern-matching **limité à la grille et à ce qui doit être scopé par entité** — le reste de la page ne change pas.
- `filterModel` persistant par `(entité, année)` ; `columnState` persistant globalement (partagé acheteur+titulaire), découplé via un store dédié.
- Changement d'année → remontage de la grille (pas de rafraîchissement in-place).
- Thème "brique" du Lot 1 réutilisé tel quel (pas d'apparence de base non-thémée).
- Les 2 boutons d'export conservés (rôles différents).
- Top 10 migré vers AG Grid simple (row model client-side), sans persistance.

## Reporté

- `observatoire.py` (Lot 2b — sous-projet séparé, spec dédiée).
- Lot 3 (`recherche.py`, `admin/liste.py`, `figures.make_table`) puis suppression de l'ancien DSL.
