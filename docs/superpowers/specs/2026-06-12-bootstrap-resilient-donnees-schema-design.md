# Bootstrap résilient des données et du schéma

**Date :** 2026-06-12
**Branche :** `feature/78_api`
**Statut :** design approuvé, à implémenter

## Problème

L'API et l'appli Web Dash partagent le même process Python (`gunicorn app:server`).
L'API sera consommée par des clients en production. Or decp.info tombe « de temps
en temps », et comme tout est dans le même process, une chute du Web emporte l'API.

**Diagnostic (clé).** Les chutes ne sont **pas** des crashs runtime aléatoires
pendant l'ingestion. Ce sont des **échecs de bootstrap au déploiement** :

- env oubliée lors d'un déploiement (ex. `DATA_FILE_PARQUET_PATH` vide) ;
- `DATA_FILE_PARQUET_PATH` (désormais une URL data.gouv.fr) injoignable ou
  pointant vers un parquet absent/invalide à cause d'un souci dans
  `decp-processing` ;
- `DATA_SCHEMA_PATH` (URL data.gouv.fr) qui renvoie une erreur.

Le process démarre sur des ressources manquantes/invalides, lève une exception
**au moment de l'import** (`src/db.py` et `src/utils/data.py` font leur bootstrap
au niveau module), et meurt au boot — API comprise.

## Pourquoi pas « séparer les process » ?

La séparation API / Web protège contre la **contagion runtime** (un callback Dash
qui tue le worker). Elle ne protège **pas** contre le mode d'échec réel : si les
deux process partagent les mêmes ressources de bootstrap (parquet, schéma, env),
ils échouent **tous les deux** au démarrage, de manière identique.

Le levier réel est donc le **durcissement du bootstrap avec fallback
« last-known-good »** : garantir présence + validité des ressources, et sinon
repartir sur les dernières ressources fonctionnelles.

La séparation des process reste **hors périmètre** de ce spec. La couche données
(`src/db.py`) est déjà process-agnostique et sans dépendance à Dash, donc la
séparation restera bon marché à dégainer plus tard _si_ un vrai crash runtime
touche l'API. On ne paie pas cette complexité tant qu'on n'en a pas la preuve.

## État actuel du code (post-merge `main`)

### `src/db.py`

- Bootstrap au niveau module : `DB_PATH = _ensure_database()` puis ouverture d'une
  connexion DuckDB read-only partagée et lecture du `schema`.
- `build_database()` écrit dans un fichier temporaire puis `os.replace()` atomique :
  un build qui échoue en cours de route **laisse l'ancien DuckDB intact**. ✅
- **Faille :** `should_rebuild()` appelle `get_last_modified(parquet_path)` qui
  fait un `httpx.head(...).headers["last-modified"]` **sans aucune gestion
  d'erreur** (`src/utils/__init__.py:12`). URL injoignable, lente, ou sans en-tête
  `last-modified` ⇒ exception ⇒ remonte jusqu'à l'import ⇒ **mort au démarrage
  alors qu'un DuckDB valide existe sur disque**.
- **Faille :** `_load_source_frame()` fait `assert os.path.exists(parquet_path)`
  (non-http) et `scan_parquet` (http) — les deux peuvent lever et ne sont pas
  rattrapés au niveau de `_ensure_database()`.

### `src/utils/data.py` — `get_data_schema()`

- Tente l'URL, attrape **seulement 4 erreurs httpx** (`ReadTimeout`, `ReadError`,
  `ConnectError`, `ConnectTimeout`), sinon fallback sur `DATA_SCHEMA_LOCAL`.
- **Faille :** pas de `raise_for_status()`. Quand data.gouv renvoie une **erreur
  HTTP** (le cas cité par l'utilisateur), `.json()` ne contient pas `"fields"` ⇒
  `KeyError` ligne 92, **sans fallback local**.
- **Faille :** un payload distant valide JSON mais malformé (sans `"fields"`)
  plante aussi sans fallback.
- **Faille :** si les deux sources échouent, `original_schema["fields"]` ⇒
  `KeyError` opaque au lieu d'une erreur claire.

## Décisions

1. **Schéma** : URL primaire, fallback local. (confirmé)
2. **DuckDB** : réutiliser le dernier DuckDB construit en cas d'échec. (confirmé)
3. **Last-known-good réel du schéma** : après un fetch distant réussi, persister
   le schéma localement pour que le fallback soit toujours le _dernier schéma
   distant fonctionnel_. (confirmé)

### Nuance sur le chemin de persistance du schéma

L'utilisateur a demandé « écrire dans `DATA_SCHEMA_LOCAL` ». Mais en dev,
`DATA_SCHEMA_LOCAL = ../decp-processing/dist/schema.json` — un fichier d'un **autre
repo**. L'écraser au boot salirait ce repo.

**Choix retenu (à confirmer en relecture) :** introduire un **chemin de cache
dédié que l'app possède**, distinct du fichier statique de secours.

- `DATA_SCHEMA_PATH` (URL) — source primaire.
- `DATA_SCHEMA_CACHE` (nouveau, ex. défaut `./schema.cache.json`) — écrit après
  chaque fetch distant réussi ; lu en fallback n°1 (dernier distant fonctionnel).
- `DATA_SCHEMA_LOCAL` — graine statique de secours (fichier `decp-processing`),
  **lue mais jamais écrite**.

Chaîne de résolution : `URL → cache → local statique → RuntimeError`.

## Design

### Invariant 1 — Bootstrap DuckDB (`src/db.py`)

> Le process démarre tant qu'un DuckDB exploitable existe, quel que soit l'état de
> la source distante/parquet. Échec dur **seulement** s'il n'existe aucune base
> (cold start).

Garde-fou unique dans `_ensure_database()` :

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

- `should_rebuild()` qui lève (via `get_last_modified()`) est désormais rattrapé :
  base existante ⇒ on la réutilise.
- `build_database()` qui lève sur parquet invalide : base existante intacte
  (atomicité) ⇒ on la réutilise.
- Le mode `DEVELOPMENT` sort de `should_rebuild()` **avant** tout appel réseau
  (court-circuit `if dev and not force: return False`) ⇒ dev inchangé.

### Invariant 2 — Schéma (`src/utils/data.py`)

> Un schéma valide non-vide est toujours retourné si une source (distant, cache,
> ou local statique) en fournit un. Échec dur seulement si aucune.

```python
def get_data_schema() -> dict:
    raw = _fetch_remote_schema(os.getenv("DATA_SCHEMA_PATH"))   # dict valide | None
    if raw is not None:
        _persist_schema_cache(raw, os.getenv("DATA_SCHEMA_CACHE", "./schema.cache.json"))
    else:
        raw = _load_schema_file(os.getenv("DATA_SCHEMA_CACHE", "./schema.cache.json"))
    if raw is None:
        raw = _load_schema_file(os.getenv("DATA_SCHEMA_LOCAL", ""))
    if raw is None:
        raise RuntimeError("Aucun schéma disponible (distant, cache ni local).")
    return OrderedDict((c["name"], c) for c in raw["fields"])
```

Helpers :

- `_fetch_remote_schema(url) -> dict | None` : `get(...).raise_for_status().json()`,
  **valide `"fields" in data`**, attrape large (`httpx.HTTPError`,
  `json.JSONDecodeError`, `KeyError`), log l'erreur, renvoie `None` sur tout échec.
- `_load_schema_file(path) -> dict | None` : lit le fichier s'il existe, parse,
  valide `"fields"`, renvoie `None` sinon.
- `_persist_schema_cache(data, path)` : écriture atomique (tmp + `os.replace`) ;
  un échec d'écriture est loggé mais **non bloquant** (le schéma en mémoire reste
  valide).

## Tests (TDD)

Couvrir chaque branche de fallback. Sans dépendre du réseau réel.

**Schéma (`get_data_schema` / helpers) :**

1. URL OK ⇒ schéma distant retourné **et** cache écrit.
2. URL renvoie une erreur HTTP (mock 500) ⇒ fallback cache.
3. URL renvoie un JSON malformé (sans `"fields"`) ⇒ fallback cache.
4. URL KO + cache présent ⇒ schéma du cache.
5. URL KO + cache absent + local statique présent ⇒ schéma local.
6. Toutes sources KO ⇒ `RuntimeError` claire.
7. Échec d'écriture du cache ⇒ schéma quand même retourné (non bloquant).

**Bootstrap DuckDB (`_ensure_database`) :** 8. `should_rebuild` lève + DuckDB existant ⇒ réutilisé, pas d'exception. 9. `build_database` lève + DuckDB existant ⇒ réutilisé, pas d'exception. 10. Échec + **aucun** DuckDB (cold start) ⇒ ré-lève. 11. Cas nominal : rebuild nécessaire et possible ⇒ build effectué.

Mocker `get_last_modified` / `build_database` / `httpx.get` ; utiliser des fichiers
DuckDB et schéma temporaires (`tmp_path`).

## Hors périmètre

- Séparation des process API / Web (reportée — voir plus haut).
- Surveillance / alerting externe (les logs `error`/`critical` suffisent pour ce lot).
- Validation fine du contenu du parquet au-delà de « lisible par Polars/DuckDB ».

## Variables d'environnement

| Variable                 | Rôle                                    | Changement           |
| ------------------------ | --------------------------------------- | -------------------- |
| `DATA_FILE_PARQUET_PATH` | Source parquet (URL ou chemin)          | inchangé             |
| `DATA_SCHEMA_PATH`       | URL schéma (primaire)                   | inchangé             |
| `DATA_SCHEMA_LOCAL`      | Fichier schéma de secours statique      | **lu, jamais écrit** |
| `DATA_SCHEMA_CACHE`      | Cache last-known-good du schéma distant | **nouveau**          |
| `DUCKDB_PATH`            | Fichier DuckDB                          | inchangé             |

Mettre à jour `.template.env` avec `DATA_SCHEMA_CACHE`.
