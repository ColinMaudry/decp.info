# API privée decp.info — Design

**Date** : 2026-05-13
**Statut** : design validé, en attente du plan d'implémentation

## 1. Contexte et objectifs

decp.info reçoit des demandes récurrentes pour un accès programmatique aux
données DECP exposées par l'application web. Le besoin est d'ouvrir une API
HTTP **privée** (accès sur token), inspirée de l'API tabulaire de data.gouv.fr
(https://tabular-api.data.gouv.fr/api/resources/22847056-61df-452d-837d-8b8ceadbfc52/swagger/),
qu'un utilisateur en cours s'est déjà appropriée comme référence.

Objectifs explicites :

- Réponses rapides.
- API documentée (OpenAPI + Swagger UI).
- Suivi de la consommation par utilisateur.

Non-objectifs (V1) :

- Self-service de création de tokens via UI web.
- Rate-limiting / quotas.
- Formats de sortie autres que JSON (CSV, Parquet…).
- Endpoints sémantiques métier (`/acheteurs/{id}`, etc.).

## 2. Choix structurants

### 2.1 Framework : Flask + flask-smorest

L'API est ajoutée à l'application Flask existante (serveur Dash) sous forme
d'un blueprint flask-smorest monté sur `/api/v1`. Choix motivé par :

- L'app Dash actuelle tourne déjà sur Flask via gunicorn.
- DuckDB est ouvert une seule fois au boot dans `src/db.py` (`conn` read-only)
  et peut être partagé directement par les endpoints API.
- L'API est tabulaire avec filtres **dynamiques** : la liste des colonnes et
  des types vient du schéma DuckDB, pas d'une déclaration Pydantic. Les
  bénéfices de FastAPI (auto-validation Pydantic) sont donc faibles.
- flask-smorest génère OpenAPI + sert Swagger UI nativement.
- Un seul process, un seul serveur, un seul déploiement.

Alternatives écartées :

- **FastAPI séparé reverse-proxié** : deux processus, ops plus complexe,
  bénéfice marginal vu les filtres dynamiques.
- **FastAPI englobant Flask via WSGIMiddleware** : changerait le serveur de
  toute l'app Dash existante, migration risquée.

### 2.2 Style d'API : tabulaire générique

Un endpoint unique de requête (`/api/v1/data`) avec filtres dynamiques sur
toutes les colonnes du schéma, à l'image du swagger cible. Aucun endpoint
sémantique métier en V1.

### 2.3 Authentification : tokens admin manuels

Tokens Bearer émis manuellement par l'admin via un CLI. Pas de page web de
gestion en V1. Modèle prévu pour se lier ultérieurement aux comptes
utilisateurs (cf. `comptes_utilisateurs.md`) sans migration de données.

### 2.4 Suivi de consommation : Matomo asynchrone + compteurs locaux

- Matomo en fire-and-forget pour l'analyse fine (qui, quand, quoi, code HTTP).
- Compteurs locaux SQLite (`count_total`, `last_used_at`) pour identifier
  les tokens inactifs et préparer un éventuel rate-limit futur.

## 3. Architecture

### 3.1 Arborescence

```
src/api/
├── __init__.py        # init_api(server) — enregistre le blueprint flask-smorest
├── routes.py          # endpoints /data, /schema, /health
├── schemas.py         # marshmallow : query params, réponses
├── filters.py         # parsing & validation `col__op=val` → (where_sql, params)
├── auth.py            # décorateur @require_token, header Authorization Bearer
├── tracking.py        # worker thread compteurs SQLite + httpx fire-and-forget Matomo
├── tokens_db.py       # CRUD api_tokens dans users.sqlite
└── tokens_cli.py      # python -m src.api.tokens_cli create|list|revoke
```

`src/auth/` reste réservé aux comptes utilisateurs interactifs
(`comptes_utilisateurs.md`), distincts des tokens API.

### 3.2 Branchement

Dans `src/app.py`, après l'init Dash :

```python
from src.api import init_api
init_api(app.server)
```

`init_api` enregistre le blueprint sur `/api/v1` et expose :

- `/api/v1/data`
- `/api/v1/schema`
- `/api/v1/health`
- `/api/v1/swagger` (UI)
- `/api/v1/openapi.json`

### 3.3 Partage de la connexion DuckDB

Les routes importent `src.db.conn` et utilisent les helpers existants
(`query_marches`, `count_marches`) ainsi que `src.db.schema` (Polars Schema)
pour la whitelist de colonnes.

## 4. Stockage

### 4.1 SQLite consolidée

Une seule base SQLite, `users.sqlite` à la racine, contient :

- `users` (futur — cf. `comptes_utilisateurs.md`)
- `api_tokens` (V1)

Bénéfice : un seul fichier à sauvegarder et migrer ; la liaison future
`api_tokens.user_id → users.id` est immédiate sans migration de données.

### 4.2 Schéma `api_tokens`

```sql
CREATE TABLE api_tokens (
    id           INTEGER PRIMARY KEY,
    token_hash   TEXT NOT NULL UNIQUE,
    label        TEXT NOT NULL,
    user_id      INTEGER,
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    count_total  INTEGER NOT NULL DEFAULT 0,
    revoked_at   TEXT
);
CREATE INDEX idx_api_tokens_hash ON api_tokens(token_hash);
```

`user_id` est `NULL` pour les tokens admin manuels. Quand le self-service
arrivera, il suffira de le renseigner.

## 5. Endpoints

### 5.1 Vue d'ensemble

| Méthode | Path                   | Auth   | Rôle                                        |
| ------- | ---------------------- | ------ | ------------------------------------------- |
| GET     | `/api/v1/data`         | Bearer | Endpoint tabulaire principal                |
| GET     | `/api/v1/schema`       | Bearer | Liste des colonnes (nom, type, description) |
| GET     | `/api/v1/health`       | Aucune | Sonde monitoring                            |
| GET     | `/api/v1/swagger`      | Aucune | Swagger UI                                  |
| GET     | `/api/v1/openapi.json` | Aucune | Spec OpenAPI                                |

### 5.2 `/api/v1/data` — langage de requête

Filtres en query string, opérateurs suffixés par `__` (mirror swagger cible) :

| Opérateur            | Sens                                                  |
| -------------------- | ----------------------------------------------------- |
| `__exact`            | égalité                                               |
| `__contains`         | sous-chaîne (LIKE %v%)                                |
| `__notcontains`      | négation de `__contains`                              |
| `__less`             | ≤                                                     |
| `__greater`          | ≥                                                     |
| `__strictly_less`    | <                                                     |
| `__strictly_greater` | >                                                     |
| `__in`               | liste séparée par virgules                            |
| `__notin`            | négation de `__in`                                    |
| `__isnull`           | `IS NULL` (valeur ignorée)                            |
| `__isnotnull`        | `IS NOT NULL` (valeur ignorée)                        |
| `__sort`             | `asc` ou `desc` — ordre = ordre des params dans l'URL |

Autres paramètres réservés :

- `page` (int, défaut 1, ≥1)
- `page_size` (int, défaut 50, max 1000)
- `columns` (string, liste séparée par virgules ; défaut = toutes)
- `count` (bool, défaut `true` ; `false` → `meta.total` absent, économise un `COUNT(*)`)

Exemple :

```
GET /api/v1/data?acheteur_departement_code__exact=44
                 &dateNotification__greater=2024-01-01
                 &montant__strictly_greater=100000
                 &objet__contains=informatique
                 &cpv_8__in=72000000,72200000
                 &dateNotification__sort=desc
                 &page=1
                 &page_size=50
                 &columns=uid,objet,montant,dateNotification
```

### 5.3 Sécurité du parsing

`filters.py` est l'unique chemin de génération du `WHERE` SQL :

1. Chaque clé `<col>__<op>` est splittée puis validée :
   - `<col>` doit être dans `src.db.schema` (whitelist stricte).
   - `<op>` doit être dans la liste blanche d'opérateurs.
   - La valeur est convertie selon le type Polars de la colonne :
     - `String` : utilisée telle quelle.
     - `Int*` : `int(value)`, 400 si non parseable.
     - `Float*` : `float(value)`, 400 si non parseable.
     - `Date` / `Datetime` : ISO 8601 (`YYYY-MM-DD` ou `YYYY-MM-DDTHH:MM:SS`), 400 sinon.
     - Booléens : **les colonnes booléennes sont stockées comme strings
       "oui"/"non" en DuckDB** (cf. `src/db.py:43`), donc traitées comme
       `String`. L'utilisateur filtre avec `colonne__exact=oui`.
2. Le `WHERE` est composé de fragments paramétrés (`?`) ; les valeurs
   utilisateur sont passées au moteur DuckDB via les paramètres, **jamais
   concaténées** dans le SQL.
3. Le résultat est consommé par `src.db.query_marches(where_sql=..., params=...)`
   qui existe déjà.

### 5.4 Format de réponse

```json
{
  "data": [{ "uid": "...", "objet": "...", "montant": 12345.0 }],
  "meta": { "page": 1, "page_size": 50, "total": 1234 },
  "links": {
    "next": "/api/v1/data?...&page=2",
    "prev": null
  }
}
```

`meta.total` est omis si `count=false`. `links.next`/`links.prev` sont
`null` aux extrémités.

### 5.5 `/api/v1/schema`

```json
{
  "columns": [
    { "name": "uid", "type": "string", "description": "..." },
    { "name": "montant", "type": "float", "description": "..." }
  ]
}
```

Descriptions tirées de `../decp-processing/reference/base_schema.json` si
disponible ; sinon vides.

### 5.6 V1 : JSON only

Pas de CSV / Parquet. Ajout possible plus tard via `?format=`.

## 6. Authentification

### 6.1 Transmission

Header HTTP standard :

```
Authorization: Bearer decpinfo_a1b2c3d4...
```

Pas de support via query string (fuites dans les logs).

### 6.2 Format du token

Préfixe `decpinfo_` + 32 octets aléatoires hex (43 caractères au total).
Le préfixe facilite la détection de fuites (gitleaks, etc.).

### 6.3 Hashing

`sha256(token)` stocké dans `api_tokens.token_hash`. Pas de bcrypt/argon2 :
les tokens ont 256 bits d'entropie, le brute-force est impossible et un
hash lent ralentirait inutilement chaque requête API.

### 6.4 Décorateur `@require_token`

1. Lit `Authorization` ; absent → 401 `missing_token`.
2. Calcule `sha256`, `SELECT` indexé.
3. Pas trouvé → 401 `invalid_token`.
4. `revoked_at IS NOT NULL` → 401 `revoked_token`.
5. Pose `flask.g.token_id` pour `tracking.py`.

### 6.5 CLI de gestion

`python -m src.api.tokens_cli` :

```
create --label "Marie Dupont - étude transport 2026"
   → affiche UNE FOIS le token plaintext (irrécupérable ensuite)

list
   → id | label | created_at | last_used_at | count_total | revoked?

revoke <id>
   → set revoked_at = now() (ISO 8601 UTC)
```

Pas d'UI web pour les tokens en V1.

## 7. Suivi de consommation

### 7.1 Hook

`@bp.after_request` déclenche deux actions **sans bloquer la réponse** :

1. Enfilage d'un update SQLite dans une `queue.Queue` consommée par un
   worker thread unique (writer série, pas de contention SQLite).
2. POST httpx fire-and-forget vers la Tracking API Matomo.

Les erreurs des deux chemins sont loggées en `warning` mais jamais propagées
à l'utilisateur.

### 7.2 Update SQLite

```sql
UPDATE api_tokens
SET count_total = count_total + 1,
    last_used_at = ?
WHERE id = ?
```

### 7.3 Event Matomo

```
POST https://analytics.maudry.com/matomo.php
  idsite=14
  rec=1
  url=https://decp.info/api/v1/data?<query>
  action_name=API /data
  uid=token-<id>           # jamais le token plaintext
  dimension1=<token_id>
  dimension2=<status_code>
  ua=<user_agent client>
```

Custom Dimensions à créer côté Matomo : `dimension1=token_id`,
`dimension2=http_status`.

### 7.4 Variables d'environnement nouvelles

```
MATOMO_URL=https://analytics.maudry.com/matomo.php
MATOMO_SITE_ID=14
MATOMO_TRACKING_ENABLED=true     # false en dev/test par défaut
USERS_DB_PATH=./users.sqlite     # tests : tests/users.test.sqlite
```

## 8. Erreurs

Format uniforme (RFC 7807, déjà standard flask-smorest) :

```json
{
  "code": 400,
  "status": "Bad Request",
  "message": "Colonne inconnue 'foo'.",
  "errors": { "field": "foo__exact" }
}
```

| HTTP | Cas                                                                   |
| ---- | --------------------------------------------------------------------- |
| 200  | Succès                                                                |
| 400  | Colonne/opérateur/valeur invalide, `page_size` hors bornes            |
| 401  | `missing_token` / `invalid_token` / `revoked_token`                   |
| 404  | Path API inexistant                                                   |
| 500  | Exception non gérée — message générique, stack trace loggée seulement |

Pas de 429 en V1.

Les 4xx sont loggées en `info` (path + token_id), les 500 en `error` avec
stack trace.

## 9. Tests

Tests pytest purs (pas de Selenium) via `app.server.test_client()`.

```
tests/api/
├── test_filters.py            # parsing, génération SQL/params, erreurs
├── test_auth.py               # 401 cases, last_used_at update
├── test_tokens_cli.py         # create/list/revoke
├── test_endpoints_data.py     # pagination, filtres, sort, columns, count=false
├── test_endpoints_schema.py   # /schema renvoie les colonnes attendues
├── test_health.py             # /health 200 sans auth
└── test_tracking.py           # compteurs SQLite, Matomo désactivé par défaut + mock httpx
```

Fixtures pytest :

- `api_client` : `app.server.test_client()`
- `valid_token_header` : crée un token dans `tests/users.test.sqlite`, renvoie le header `Authorization: Bearer …`
- `revoked_token_header` : idem avec `revoked_at` set

Ajouts `pyproject.toml` `[tool.pytest.ini_options].env` :

```
USERS_DB_PATH=tests/users.test.sqlite
MATOMO_TRACKING_ENABLED=false
```

Couverture cible : 100% de `filters.py` et `auth.py` (sécurité-critique) ;
raisonnable ailleurs.

## 10. Dépendances nouvelles

À ajouter dans `pyproject.toml` :

- `flask-smorest` (blueprint + OpenAPI + Swagger UI)
- `marshmallow` (déjà transitif de flask-smorest, à expliciter)

`httpx` est déjà présent. Pas d'autres dépendances.

## 11. Documentation utilisateur

À fournir séparément (hors scope spec, à inclure dans le plan d'implémentation) :

- Section "API" dans la page À propos ou page dédiée `/api` avec :
  - lien vers Swagger UI
  - exemples curl
  - procédure pour obtenir un token (« contactez X »)
- Mention dans le `CHANGELOG.md` à la sortie de version.

## 12. Risques et points ouverts

- **Coût du `COUNT(*)`** sur gros filtres : mitigé par `count=false` opt-out.
- **Charge SQLite write** : un worker série suffira pour le trafic attendu
  (admin tokens manuels, faible volume). Si le volume monte, passer à un
  buffer en RAM avec flush périodique.
- **Matomo down** : impact nul sur l'API (fire-and-forget loggué).
- **Évolution vers self-service** : déjà préparée par `user_id` nullable et
  séparation `src/api/` vs `src/auth/`.
