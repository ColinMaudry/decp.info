# Colonnes configurables pour `rechercher_marches` (MCP) — Design

**Issue liée :** connecteur MCP colibre (#114).

## Objectif

Rendre la sélection des colonnes du tool MCP `rechercher_marches` souple, au lieu
de la liste figée `MARCHES_COLUMNS`. Trois besoins :

1. Un **choix par défaut** (les colonnes actuelles), comportement inchangé si le
   client ne demande rien.
2. Un **champ de lien** dynamique vers chaque marché, ajouté à chaque résultat :
   `APP_BASE_URL/marche/{uid}`.
3. La possibilité pour l'agent/l'utilisateur de **choisir d'autres colonnes** parmi
   celles disponibles, avec la meilleure UX atteignable dans l'interface tool MCP.

## Contexte UX (ce qui est possible, ce qui ne l'est pas)

- **Cases à cocher rendues par le serveur : impossible.** dash 4.4 n'implémente pas
  l'_élicitation_ MCP (le serveur n'annonce que les capacités `tools` et
  `resources`). Aucun widget interactif ne peut être poussé dans le client.
- **Levier retenu : un `enum` dans le schéma du paramètre.** En typant `colonnes`
  avec un `Literal` des colonnes disponibles, l'agent reçoit la liste fermée valide
  directement dans le schéma du tool (pas de tâtonnement, pas besoin d'appeler
  `schema_donnees` au préalable). Beaucoup de clients (dont Claude) rendent un
  paramètre enum comme un sélecteur cochable. C'est aussi une validation au niveau
  schéma.

## Source de vérité des colonnes

`DATA_SCHEMA` (issu du TableSchema `base_schema.json`) est la référence, déjà
utilisée par `describe_schema()`. L'ensemble sélectionnable part de l'intersection `DATA_SCHEMA ∩ duckdb_schema`
(exactement le set déjà exposé comme `colonnes_filtrables`), **unie** aux colonnes
du défaut `MARCHES_COLUMNS` — pour que toute colonne du jeu par défaut reste
re-sélectionnable même si elle est enrichie et absente de `DATA_SCHEMA` (ex.
`acheteur_nom`). Ces colonnes du défaut sont toutes présentes dans la table DuckDB
(elles fonctionnent déjà), donc sûres à `SELECT` :

```python
_filtrables = tuple(name for name in DATA_SCHEMA if name in duckdb_schema)
SELECTABLE_COLUMNS = tuple(dict.fromkeys((*MARCHES_COLUMNS, *_filtrables)))
```

Source de vérité unique (schéma de référence + défaut), ni liste « raw DuckDB », ni
sous-ensemble à maintenir à la main.

## Modifications

### `src/mcp/queries.py`

- Construire à l'import :
  ```python
  SELECTABLE_COLUMNS = tuple(name for name in DATA_SCHEMA if name in duckdb_schema)
  ColonneMarche = Literal[SELECTABLE_COLUMNS]
  ```
- `search_marches(..., colonnes: list[str] | None = None)` :
  - `colonnes is None` → `MARCHES_COLUMNS` (comportement inchangé).
  - liste fournie → **exactement** ces colonnes (remplace le défaut).
  - **Validation runtime conservée** (défense en profondeur : le `enum` du schéma
    n'est pas toujours imposé par le client). Toute colonne absente de
    `SELECTABLE_COLUMNS` → retour `{"error": "colonne inconnue: <col>", "champ": col}`
    (même patron que les erreurs de filtre). C'est ce qui protège l'interpolation
    SQL brute de `query_marches` (`src/db.py` fait `", ".join(columns)` sans
    quoting ni validation, prévu pour des appelants internes seulement).
  - **`uid` toujours récupéré** en interne (nécessaire au lien) même s'il n'est pas
    demandé, et **toujours présent en sortie** (clé primaire).
  - **`lien` toujours ajouté** à chaque marché après la requête (champ virtuel,
    calculé en Python comme la colonne `marche`) :
    `f"{base}/marche/{uid}"` avec `base = os.getenv("APP_BASE_URL", "").rstrip("/")`
    (cohérent avec le reste du code : `src/mcp/auth.py`, `oauth/routes.py`, etc.).
- `describe_schema()` : ajoute la clé `colonnes_disponibles = list(SELECTABLE_COLUMNS)`.
  `lien` est mentionné dans `colonnes_retournees`.

### `src/mcp/tools.py`

- `rechercher_marches(..., colonnes: list[ColonneMarche] | None = None)` — c'est
  cette annotation `enum` qui porte l'UX.
- Docstring mise à jour : décrit `colonnes` (défaut = jeu standard ; renvoie vers
  `schema_donnees().colonnes_disponibles`), et mentionne le champ `lien`.

## Points notables / décisions

- **`lien` non désactivable** (YAGNI). Toujours présent.
- **`APP_BASE_URL` non défini (dev)** → `lien` relatif `/marche/{uid}`. Acceptable
  (dev only), cohérent avec le fallback des autres modules.
- **Sémantique « remplace »** (et non « ajoute ») : `colonnes=[...]` renvoie
  exactement ce set (+ `uid` + `lien`). Choix validé : l'utilisateur maîtrise
  précisément ce qu'il reçoit.
- **Pas de champ `title` d'affichage pour les tools** : abandonné (dash 4.4 n'a pas
  de titre séparé du `name`, qui sert à la fois d'identifiant et d'affichage).

## Tests — `tests/mcp/test_queries.py`

- `colonnes=None` → renvoie le jeu par défaut (`MARCHES_COLUMNS`) inchangé, `lien`
  présent.
- `colonnes=["objet", "montant"]` → renvoie exactement ces colonnes + `uid` + `lien`.
- Colonne invalide (`["nexiste_pas"]`) → `{"error": ..., "champ": "nexiste_pas"}`,
  aucune requête SQL avec la colonne interpolée.
- `lien` bien formé : `<APP_BASE_URL>/marche/<uid>` (monkeypatch `APP_BASE_URL`).
- `uid` présent en sortie même absent de `colonnes`.
- `describe_schema()` expose `colonnes_disponibles` non vide et surensemble de
  `colonnes_filtrables` (inclut les colonnes du défaut).
- Le schéma du paramètre `colonnes` du tool `rechercher_marches` contient bien un
  `enum` (via `TypeAdapter` sur l'annotation, ou le builder dash).

## Hors périmètre

- Titre d'affichage joli pour les tools (abandonné).
- Toute modification de l'API REST `/data`.
- Élicitation / widgets interactifs (non supportés par dash 4.4).
