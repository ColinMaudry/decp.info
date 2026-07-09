# Migration des tables vers Dash AG Grid — Design (Lot 1 : `tableau.py`)

- **Issues** : #41 (migration AG Grid), #97 (requêtes booléennes, abonnés), #112 (partage de vues abonnés par URL courte)
- **Date** : 2026-07-09
- **Décision d'archi de référence** : commentaire sur #41

## Contexte

Les tables de l'application reposent sur `dash_table.DataTable`, que Plotly abandonne au profit d'AG Grid. `colibre` a fortement personnalisé ses DataTable et les utilise sur 6 emplacements. La page vitrine `tableau.py` est la plus riche : paging / filtre / tri **server-side** sur DuckDB (~1,5 M lignes), partage de vue par URL, vues sauvegardées (abonnés), export Excel, sélecteur de colonnes, persistance, tooltips d'en-tête, liens dans les cellules.

Cette migration prépare une **version majeure** (pas de rétro-compatibilité) et doit rendre implémentable #97 (requêtes booléennes OR/AND/NOT + parenthèses, réservé aux abonnés).

## Objectifs

1. **Préserver les fonctionnalités existantes** de `tableau.py` en passant de `DataTable` à `dag.AgGrid`.
2. **Conserver l'apparence de base d'AG Grid** dans un premier temps — le portage de nos overrides CSS (polices Inter, largeurs de colonnes conditionnelles, tailles) est **reporté** au 2e temps.
3. **Poser le moteur de requête** (AST booléen → SQL DuckDB) comme socle canonique, pour que #97 soit une extension incrémentale.

## Non-objectifs (reportés)

- Portage des overrides CSS des DataTable (2e temps).
- Migration des autres pages : `acheteur.py`, `titulaire.py`, `observatoire.py`, `recherche.py`, `admin/liste.py`, `figures.make_table` (Lots 2 et 3).
- UI du champ de requête booléenne avancée #97 (le moteur AST est posé ici, l'UI vient ensuite).
- Partage de vue par URL courte `?vue=<user_id>_<nom>` (#112).

## Décisions d'architecture (rappel)

- **AG Grid = grille d'affichage.** En row model server-side, c'est notre callback Dash qui compile le filtre en SQL ; on ne dépend pas de la puissance de filtrage d'AG Grid.
- **Infinite Row Model** pour `tableau.py` (`rowModelType="infinite"`).
- **Modèle canonique = AST booléen** (`AND`/`OR`/`NOT` + groupement ; feuilles = `colonne op valeur`), compilé en SQL DuckDB paramétré.
- **Deux producteurs** alimentent le même AST : (1) filtres de colonne AG Grid (gratuit, comportement actuel préservé), (2) champ de requête texte inter-colonnes (#97, abonnés — UI reportée).
- **Pas de rétro-compat** : l'encodage riche de vue dans l'URL (`?filtres/tris/colonnes` en DSL DataTable) est **retiré**. Le partage passera par les vues sauvegardées (#112).
- **Pas d'AG Grid Enterprise.**

## Architecture cible (Lot 1)

### Flux de données

```
AG Grid (infinite)
  │  getRowsRequest = {startRow, endRow, filterModel, sortModel}
  ▼
callback Dash `get_rows_tableau`
  │  filterModel ──► filtermodel_to_ast() ──► AST
  │  AST ──► ast_to_sql() ──► (where_sql, params)
  │  sortModel ──► sort_model_to_sql()
  ▼
DuckDB (via _fetch_page_sql, réutilisé/adapté)  ──► page + total
  ▼
getRowsResponse = {rowData, rowCount}
```

### Moteur de requête — nouveau module `src/utils/query_ast.py`

Représentation canonique et compilateur, indépendants de l'UI :

- **Types AST** : nœuds `And(children)`, `Or(children)`, `Not(child)`, et feuille `Condition(column, operator, value)`.
- `ast_to_sql(node, schema) -> (where_sql, params)` : compile en SQL DuckDB **paramétré**. Valide chaque `column` contre `schema.names()` (jamais de concaténation de valeur utilisateur — même garantie que l'actuel `filter_query_to_sql`).
- Les **feuilles texte** réutilisent la logique de `tokenize_text_filter` (`src/utils/table_sql.py`) : insensible casse/accents, wildcards `*`, phrases `+`, multi-mots en `AND`. Les feuilles numériques/date réutilisent la logique de typage de `filter_query_to_sql`.

Deux traducteurs (producteurs) vers l'AST :

- `filtermodel_to_ast(filter_model, schema) -> node` : convertit le `filterModel` d'AG Grid (`agTextColumnFilter`, `agNumberColumnFilter`, `agDateColumnFilter`, avec `operator: AND/OR` + `condition1/condition2`) en AST. Colonnes combinées en `And`.
- _(reporté #97)_ `query_string_to_ast(text, schema) -> node` : parseur de la syntaxe FR `(béton OR ciment) AND brique AND NOT démolition`. Non implémenté au Lot 1, mais l'AST est prêt à le recevoir.

> On **retire** l'ancien DSL `{col} icontains valeur && …` de `tableau.py` : `filter_query_to_sql` et le JS `clean_filters` (`src/assets/dash_clientside.js`) ne sont plus utilisés par cette page. On les conserve tant que les autres pages (Lots 2/3) s'en servent, puis on les supprime au dernier lot.

### Composant grille — `src/figures.py`

Nouvelle fabrique `ag_grid(...)` (à côté de la classe `DataTable`, qui reste pour les pages non encore migrées) :

- `dag.AgGrid(rowModelType="infinite", ...)`.
- `columnDefs` dérivés de `schema` : `field`, `headerName`, `filter` par type (`agTextColumnFilter` / `agNumberColumnFilter` / `agDateColumnFilter`), `floatingFilter: True`, `headerTooltip` = définition de la colonne (remplace `tooltip_header`), `hide` selon les colonnes masquées.
- Cellules à liens (`marche` 🔍, `acheteur_nom`/`titulaire_nom` avec liens détail + 📊, `uid`, ressource) : `cellRenderer: "markdown"` + `dangerously_allow_code=True` sur la grille → le HTML `<a>` produit par `postprocess_page`/`add_links` se rend tel quel. `linkTarget: "_blank"` au besoin.
- `dashGridOptions` : `cacheBlockSize` = taille de page (20), `maxBlocksInCache`, `rowBuffer`, `pagination`/`paginationAutoPageSize` selon l'UX voulue.
- **Apparence de base** : pas de thème custom au Lot 1 (thème AG Grid par défaut).

### Persistance

- `persistence=True`, `persistence_type="local"`, `persisted_props=["filterModel", "columnState"]` — remplace la persistance actuelle (`filter_query`, `sort_by`). Les tris et la visibilité des colonnes vivent dans `columnState`.

### Réécriture des callbacks `tableau.py`

- **Remplacé** : le callback `update_table` (Inputs `page_current/page_size/filter_query/sort_by`) devient `get_rows_tableau` (Input `getRowsRequest` → Output `getRowsResponse`).
- **Sélecteur de colonnes** : les callbacks colonnes pilotent désormais `columnDefs`/`columnState` (`hide`) au lieu de `hidden_columns`. `make_column_picker`, `get_default_hidden_columns`, `invert_columns` réutilisés.
- **Export Excel** (`download_data`) : recompile le filtre via l'AST (à partir du `filterModel` courant, exposé en `State`). **Recommandé** : compiler l'AST en SQL et récupérer les lignes filtrées/triées depuis DuckDB, puis `write_styled_excel` — unifie le chemin de données et évite un second compilateur (AST→Polars). L'actuel export passe par Polars (`filter_table_data`) ; ce point est listé dans « Questions ouvertes ».
- **nb_rows / hint téléchargement** : dérivés du `rowCount` et du total (seuil 65 000 lignes conservé).
- **Vues sauvegardées (abonnés)** : `saved_views` stocke désormais l'AST (JSON) + `columnState`, au lieu de la query DSL. `build_view_query` / `restore_view_from_url` remplacés par une sérialisation AST. Le _rappel_ de vue reste ; le _partage par URL riche_ est retiré.
- **Retiré** : `restore_view_from_url` (partie `?filtres/tris/colonnes`), `sync_url_and_reset_button` (URL riche), bouton « Partager la vue » (revient avec #112), `clean_filters` clientside.
- **Conservé** : mode d'emploi (à réécrire pour la nouvelle UX de filtres AG Grid), bouton Réinitialiser, `track_search`.

### Mode d'emploi

Le `dcc.Markdown` d'aide et les **liens d'exemple** codés en dur (qui encodent l'ancien DSL dans l'URL) sont **réécrits** pour décrire les filtres de colonne AG Grid. Les exemples « voirie < 40 k€ » / « clause sociale PME » sont retirés ou reformulés (plus d'URL riche).

## Dépendances

- Ajouter `dash-ag-grid` (non installé actuellement) : `uv add dash-ag-grid`. Version alignée sur Dash 3.4 (dash-ag-grid 35.x). Vérifier la compatibilité au moment de l'ajout.

## Cas limites & erreurs

- `getRowsRequest is None` → `no_update`.
- `filterModel` vide → AST vide → `where = TRUE`.
- Colonne inconnue dans un filtre → ignorée + `logger.warning` (parité avec l'actuel).
- Valeur numérique/date invalide → ignorée + warning.
- `rowCount` = 0 → la grille affiche « aucune ligne » (gérer le total à 0 sans casser la pagination).
- Sécurité : identifiants de colonnes validés contre le schéma, valeurs toujours paramétrées (jamais concaténées).

## Tests

- **Unitaires `query_ast.py`** : `ast_to_sql` (feuilles texte accent-insensitive, wildcard `*`, phrase `+`, numérique `=/>/<`, date ; `And/Or/Not` ; groupement). Réutiliser/adapter les cas de `tests/test_table.py` (ex. `test_filter_table_data_accent_insensitive`).
- **Unitaires `filtermodel_to_ast`** : chaque type de filtre AG Grid + `operator AND/OR` + `condition1/condition2`.
- **Parité SQL** : un `filterModel` simple doit produire le même résultat que l'ancien DSL équivalent (non-régression).
- **Intégration (Selenium/DashComposite)** : chargement de la grille, filtre de colonne, tri, pagination, sélecteur de colonnes, export Excel, persistance locale, vue sauvegardée (abonné).
- Suite complète `uv run pytest` uniquement en fin de lot.

## Questions ouvertes à trancher

1. **UX de pagination** : garder des **pages numérotées** (20 lignes/page, comme aujourd'hui, via `pagination=True` sur l'infinite row model) ou passer au **scroll infini** (chargement continu au défilement) ? Défaut proposé : pages numérotées, plus proche de l'existant.
2. **Chemin de l'export Excel** : passer l'export sur **DuckDB** (AST→SQL, cohérent avec la grille — recommandé) ou conserver le pipeline **Polars** actuel en lui branchant un compilateur AST→Polars ?

## Reporté au 2e temps / lots suivants

- Portage des overrides CSS (apparence).
- #97 : `query_string_to_ast` + champ de requête avancé (abonnés).
- #112 : partage de vue `?vue=<user_id>_<nom>`.
- Migration des Lots 2 (`acheteur`/`titulaire`/`observatoire`) et 3 (`recherche`/`admin`/`figures.make_table`), puis suppression de l'ancien DSL (`filter_query_to_sql`, `clean_filters`).
