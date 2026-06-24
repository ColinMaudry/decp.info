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

1. **Schéma** : URL primaire, **cache seul** en fallback (on supprime
   `DATA_SCHEMA_LOCAL`). (confirmé)
2. **DuckDB** : réutiliser le dernier DuckDB construit en cas d'échec. (confirmé)
3. **Last-known-good réel du schéma** : après un fetch distant réussi, persister
   le schéma dans un cache local pour que le fallback soit toujours le _dernier
   schéma distant fonctionnel_. (confirmé)

### Chemin de persistance du schéma : `DATA_SCHEMA_CACHE` seul

On remplace `DATA_SCHEMA_LOCAL` (qui pointait, en dev, vers
`../decp-processing/dist/schema.json` — un fichier cross-repo qu'on ne veut pas
écraser) par un **cache unique possédé par l'app**.

- `DATA_SCHEMA_PATH` (URL) — source primaire.
- `DATA_SCHEMA_CACHE` (nouveau, ex. défaut `./schema.cache.json`) — écrit après
  chaque fetch distant réussi, lu en fallback.

Chaîne de résolution : `URL → cache → RuntimeError`.

**Pourquoi c'est suffisant.** Le déploiement est en place sur un VM persistant
(`ssh → cd /var/www/APP_NAME → git pull → restart systemd`), donc le fichier de
cache survit aux déploiements — **même garantie de persistance que le DuckDB
réutilisé**. Tous les incidents constatés (env oubliée, parquet KO, URL schéma en
erreur) surviennent sur un **redéploiement** d'un hôte déjà chaud, où le cache a
déjà été écrit par un boot précédent réussi ⇒ couvert.

**Seul cas non couvert (assumé) :** le _cold start absolu_ — un hôte qui n'a jamais
booté avec succès **et** URL distante down au même instant. Étroit, non-récurrent.
Fermable plus tard par une graine commitée in-repo si jamais il se matérialise
(YAGNI).

**Contraintes :**

- `DATA_SCHEMA_CACHE` (`./schema.cache.json`) doit être **`.gitignore`** — sinon le
  `git pull` du déploiement entrerait en conflit. (Comme `decp.duckdb` aujourd'hui.)
- En dev, plus de fallback vers le schéma frais de `decp-processing` : on bascule
  sur le cache (dernier schéma data.gouv). Acceptable, l'URL restant primaire.

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

> Un schéma valide non-vide est toujours retourné si une source (distant ou cache)
> en fournit un. Échec dur seulement si aucune.

```python
def get_data_schema() -> dict:
    cache_path = os.getenv("DATA_SCHEMA_CACHE", "./schema.cache.json")
    raw = _fetch_remote_schema(os.getenv("DATA_SCHEMA_PATH"))   # dict valide | None
    if raw is not None:
        _persist_schema_cache(raw, cache_path)
    else:
        raw = _load_schema_file(cache_path)
    if raw is None:
        raise RuntimeError("Aucun schéma disponible (ni distant ni cache).")
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

### Invariant 3 — Chargements au niveau module des pages

> L'import d'une page (exécuté au boot via `use_pages`) ne doit jamais tuer le
> démarrage à cause d'une ressource externe KO. Une ressource indisponible
> dégrade gracieusement l'affichage.

Audit des chargements à l'import (tous les `layout` de pages sont au niveau
module ⇒ leur contenu s'exécute au boot). Deux points de rupture **externes** :

**C — `src/pages/tableau.py:36-38`.** `get_last_modified(URL parquet)` fait un
HTTP HEAD **sans gestion d'erreur** (URL injoignable, en-tête `last-modified`
absent) ⇒ import KO ⇒ boot KO. C'est le même piège que `db.py`, mais dans une page.

Correctif : un helper best-effort dans `src/utils/__init__.py` qui ne lève jamais
et retombe sur le mtime du DuckDB (garanti présent par l'Invariant 1) :

```python
def get_data_update_timestamp(parquet_path: str, fallback_path: str | None = None) -> float | None:
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

`tableau.py` l'utilise et gère le cas `None` (affiche « date inconnue »,
`update_date_iso = ""`).

**D — `src/pages/a-propos.py:103`.** `get_sources_tables(SOURCE_STATS_CSV_PATH)`
(`src/figures.py:121`) fait `pl.read_csv(source_path)` mais ne rattrape que
`URLError, HTTPError` — pas les erreurs Polars, ni `source_path` vide/`None`, ni
fichier absent ⇒ import KO ⇒ boot KO.

Correctif : élargir le `except` et gérer le chemin vide :

```python
def get_sources_tables(source_path) -> html.Div:
    try:
        if not source_path:
            raise ValueError("SOURCE_STATS_CSV_PATH non défini")
        dff = pl.read_csv(source_path)
    except Exception as e:
        logger.warning(f"Sources de données indisponibles ({e})")
        return html.Div("Sources de données momentanément indisponibles.")
    ...  # suite inchangée
```

Hors périmètre des pages : `data/departements.json` + `.geojson` (fichiers
in-repo apportés par `git pull`, pas pilotés par env/URL — voir Hors périmètre).

## Tests (TDD)

Couvrir chaque branche de fallback. Sans dépendre du réseau réel.

**Schéma (`get_data_schema` / helpers) :**

1. URL OK ⇒ schéma distant retourné **et** cache écrit.
2. URL renvoie une erreur HTTP (mock 500) ⇒ fallback cache.
3. URL renvoie un JSON malformé (sans `"fields"`) ⇒ fallback cache.
4. URL KO + cache présent ⇒ schéma du cache.
5. URL KO + cache absent ⇒ `RuntimeError` claire.
6. Échec d'écriture du cache ⇒ schéma quand même retourné (non bloquant).

**Bootstrap DuckDB (`_ensure_database`) :**

7. `should_rebuild` lève + DuckDB existant ⇒ réutilisé, pas d'exception.
8. `build_database` lève + DuckDB existant ⇒ réutilisé, pas d'exception.
9. Échec + **aucun** DuckDB (cold start) ⇒ ré-lève.
10. Cas nominal : rebuild nécessaire et possible ⇒ build effectué.

Mocker `get_last_modified` / `build_database` / `httpx.get` ; utiliser des fichiers
DuckDB et schéma temporaires (`tmp_path`).

**Chargements de pages (Invariant 3) :**

11. `get_data_update_timestamp` : `get_last_modified` lève + `fallback_path`
    existant ⇒ retourne le mtime du fallback (pas d'exception).
12. `get_data_update_timestamp` : tout KO (lève + pas de fallback) ⇒ `None`.
13. `get_data_update_timestamp` : cas nominal ⇒ retourne la valeur de
    `get_last_modified` (mocké).
14. `get_sources_tables(None)` ⇒ `html.Div` de repli (pas d'exception).
15. `get_sources_tables("/inexistant.csv")` ⇒ `html.Div` de repli.
16. `get_sources_tables(<csv valide>)` ⇒ `html.Div` contenant la `DataTable`.

## Hors périmètre

- Séparation des process API / Web (reportée — voir plus haut).
- Surveillance / alerting externe (les logs `error`/`critical` suffisent pour ce lot).
- Validation fine du contenu du parquet au-delà de « lisible par Polars/DuckDB ».
- Durcissement des `open()` in-repo (`data/departements.json` + `.geojson`) :
  fichiers versionnés, apportés par `git pull`, jamais pilotés par env/URL (YAGNI).

## Variables d'environnement

| Variable                 | Rôle                                    | Changement   |
| ------------------------ | --------------------------------------- | ------------ |
| `DATA_FILE_PARQUET_PATH` | Source parquet (URL ou chemin)          | inchangé     |
| `DATA_SCHEMA_PATH`       | URL schéma (primaire)                   | inchangé     |
| `DATA_SCHEMA_LOCAL`      | Ancien fichier de secours statique      | **supprimé** |
| `DATA_SCHEMA_CACHE`      | Cache last-known-good du schéma distant | **nouveau**  |
| `DUCKDB_PATH`            | Fichier DuckDB                          | inchangé     |
| `SOURCE_STATS_CSV_PATH`  | CSV stats sources (page À propos, D)    | inchangé     |

À faire côté config :

- Ajouter `DATA_SCHEMA_CACHE` à `.template.env`, retirer `DATA_SCHEMA_LOCAL` de
  `.template.env` / `.env`.
- Ajouter `schema.cache.json` (ou la valeur de `DATA_SCHEMA_CACHE`) au `.gitignore`.
