# Scope B2 — Serveur d'autorisation OAuth 2.1 pour le connecteur MCP

**Issue :** #114 (« Permettre l'accès aux données colibre via ChatGPT et Claude.ai »),
2ᵉ partie de #111.
**Date :** 2026-07-13
**Statut :** design approuvé
**Prérequis :** scopes A et B livrés et fusionnés dans `dev` (serveur MCP `/_mcp`,
`src/mcp/`, garde jeton statique `src/mcp/auth.py`, page `/compte/mcp`).

## Objectif

Permettre aux clients grand public qui exigent OAuth — **Claude.ai, Claude Desktop,
Claude mobile, ChatGPT** — de se connecter au serveur MCP colibre sans copier-coller
de jeton, en faisant de colibre son **propre serveur d'autorisation OAuth 2.1**
conforme à la spec MCP (authorization, 2025-06-18 / 2025-11-25). L'accès reste
**conditionné à un abonnement colibre actif**, vérifié à chaque requête.

Le chemin « jeton statique » livré en scope B (clients CLI : Claude Code, Gemini,
Mistral) est **conservé sans régression**. Ce scope l'**ajoute** en parallèle.

## Décisions de conception (arbitrées)

1. **colibre = serveur d'autorisation ET resource server**, sur le même Flask
   (`app.server`) qui sert déjà `/_mcp`. L'étape de consentement réutilise la
   **session flask_login existante**.
2. **authlib** (déjà en dépendance pour LinkedIn) via son cœur OAuth 2.0
   (`authlib.oauth2.rfc6749/7591/7636/8414`), avec un **stockage SQLite maison**
   (`sqlite3` brut, comme `tokens_db.py` / `auth.db` / `subscriptions.db`). Pas de
   SQLAlchemy.
3. **Tokens d'accès opaques**, validés par lookup haché en base (colibre étant AS
   **et** RS sur le même hôte). Pas de JWT/JWKS/signature. L'audience (`resource`)
   est stockée sur la ligne du token.
4. **DCR (RFC 7591) comme baseline** d'enregistrement client. Claude et ChatGPT le
   supportent nativement et retombent dessus si CIMD n'est pas annoncé. Clients
   **publics** (`token_endpoint_auth_methods_supported: ["none"]` + PKCE S256).
5. **Gate abonnement bloquant tôt, à `/authorize`**, ET re-vérifié à chaque requête
   `/_mcp` et à chaque refresh (défense en profondeur — voir §« Abonnement »).
6. **Détection d'usage (niveau 1)** : table `mcp_usage` journalisant chaque requête
   `/_mcp` authentifiée. Pas de rate-limiting actif (hors-périmètre).
7. **Durées de vie** : access token **1 h**, refresh token **60 j**, **rotation du
   refresh** à chaque usage (exigence client public).

## Exigences externes vérifiées (2026-07)

Sources : spec MCP authorization (2025-06-18/2025-11-25), doc connecteurs Claude
(`claude.com/docs/connectors/building/authentication`), doc Apps SDK ChatGPT
(`developers.openai.com/apps-sdk/build/auth`).

Communes à Claude **et** ChatGPT :

- **Découverte** : PRM (RFC 9728) à `/.well-known/oauth-protected-resource`
  (+ variante suffixée `/_mcp`) ; AS metadata (RFC 8414) à
  `/.well-known/oauth-authorization-server` ; **`/.well-known/openid-configuration`**
  aussi (sondé par ChatGPT). Le champ `resource` de la PRM doit valoir **exactement**
  l'URL saisie par l'utilisateur (`https://colibre.fr/_mcp`) ; `authorization_servers`
  liste l'issuer, **1ʳᵉ entrée utilisée** (pas de fallback vers les suivantes).
- **401 + `WWW-Authenticate: Bearer …, resource_metadata="…"`** : c'est ce header
  qui déclenche le flux OAuth côté client. Le 401 (pas 200) est requis.
- **PKCE S256** obligatoire ; metadata doit annoncer
  `code_challenge_methods_supported: ["S256"]`.
- **Audience RFC 8707** : `resource` envoyé sur `/authorize` et `/token`, copié sur
  le token, validé à `/_mcp`.
- **`/token`** accepte `application/x-www-form-urlencoded`, renvoie des codes
  d'erreur **RFC 6749** (`invalid_grant`). `/register` en `application/json`.
- **Refresh** : Claude fait la **rotation** (client public) et n'ajoute
  `offline_access` que si annoncé dans `scopes_supported`. ChatGPT ne l'exige pas.
  → on supporte le refresh et on annonce `offline_access`.
- **Redirect URIs** validés en **exact-match** contre ceux fournis au DCR :
  Claude `https://claude.ai/api/mcp/auth_callback` ; ChatGPT
  `https://chatgpt.com/connector/oauth/{id}` (+ legacy
  `https://chatgpt.com/connector_platform_oauth_redirect`). Rien à coder en dur.
- **Consentement** : l'écran doit afficher le **hostname du redirect_uri** (risque
  d'usurpation loopback, spec 2025-11-25).
- **Latence** : discovery/registration/token < 10 s, refresh < 30 s (les opérations
  sqlite sont bien en-deçà).
- **Ops** : l'AS et `/_mcp` doivent rester joignables depuis l'egress Anthropic
  `160.79.104.0/21` sans WAF bloquant, en **HTTPS** (localhost toléré en dev).

## Architecture

### Coexistence des deux chemins d'auth sur `/_mcp`

| Chemin                                         | Clients                                   | Mécanisme                                                  |
| ---------------------------------------------- | ----------------------------------------- | ---------------------------------------------------------- |
| Jeton statique `colibre_…` (scope B, inchangé) | Claude Code, Gemini, Mistral              | collé à la main depuis `/compte/mcp`                       |
| **OAuth 2.1 (ce scope B2)**                    | Claude.ai, Claude Desktop/mobile, ChatGPT | « Ajouter un connecteur » → flux OAuth, zéro copier-coller |

### Arborescence

```
src/mcp/oauth/
  __init__.py
  store.py       # stores sqlite bruts : clients (DCR), codes, tokens
  server.py      # authlib AuthorizationServer : AuthorizationCodeGrant+PKCE, RefreshTokenGrant, DCR
  metadata.py    # documents JSON RFC 9728 (protected-resource) + RFC 8414 (AS)
  consent.py     # écran de consentement + gate abonnement
  routes.py      # blueprint Flask : /.well-known/*, /oauth/register, /oauth/authorize, /oauth/token, /oauth/revoke
src/mcp/usage.py # journal d'usage /_mcp (niveau 1 détection)
```

Fichiers **modifiés** : `src/mcp/auth.py` (garde `/_mcp` accepte aussi les tokens
OAuth + en-tête `resource_metadata` + journal `mcp_usage`), `src/migrations.py`
(nouvelles tables), `src/pages/compte/mcp.py` (instructions Claude.ai / ChatGPT),
`src/app.py` (enregistrement blueprint + exemption CSRF).

### Isolation des unités

- `store.py` : accès sqlite pur (clients/codes/tokens), testable sans HTTP ni authlib.
- `server.py` : configuration authlib (grants, hooks `query_client`/`save_token`),
  branchée sur `store.py`.
- `metadata.py` : documents JSON purs (fonctions déterministes de `APP_BASE_URL`).
- `consent.py` : rendu de l'écran + gate abonnement, testable indépendamment.
- `usage.py` : journal `/_mcp`, testable isolément.

## Stockage — 3 tables OAuth + 1 table usage (`users.sqlite`)

Créées via `_MIGRATIONS` et initialisées au démarrage (`init_schema`, comme
`tokens_db`), **avant** `apply_pending()`. Tolérance _duplicate_ déjà gérée.

- **`oauth_clients`** — `client_id` (PK), `client_metadata` (JSON : `redirect_uris`,
  `client_name`, `token_endpoint_auth_method='none'`, `grant_types`, `scope`),
  `created_at`. Clients **publics**, créés par DCR.
- **`oauth_codes`** — `code_hash` (PK), `client_id`, `user_id`, `redirect_uri`,
  `code_challenge`, `code_challenge_method`, `scope`, `resource`, `expires_at`,
  `used`. Éphémère (~60 s).
- **`oauth_tokens`** — `access_token_hash`, `refresh_token_hash`, `client_id`,
  `user_id`, `scope`, `resource` (audience), `issued_at`, `access_expires_at`
  (+1 h), `refresh_expires_at` (+60 j), `revoked_at`. Rotation du refresh à chaque
  usage.
- **`mcp_usage`** — `id` (PK), `user_id`, `token_id`, `kind` (`'static'`|`'oauth'`),
  `created_at`. Une ligne par requête `/_mcp` **authentifiée** (niveau 1 détection).

Les jetons statiques restent dans `api_tokens` (inchangé).

## Endpoints, discovery & flux OAuth

Blueprint `src/mcp/oauth/routes.py` sur `app.server`, **exempté de CSRF** (comme
`/_mcp` ; POST externes sans jeton CSRF).

| Route                                                                           | Méthode     | Rôle                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/.well-known/oauth-protected-resource` + `…/oauth-protected-resource/_mcp`     | GET         | **PRM (RFC 9728)** : `{ resource:"<base>/_mcp", authorization_servers:[issuer], scopes_supported:["mcp","offline_access"] }`                                                                                                                                                                                           |
| `/.well-known/oauth-authorization-server` + `/.well-known/openid-configuration` | GET         | **AS metadata (RFC 8414)** : `authorization_endpoint`, `token_endpoint`, `registration_endpoint`, `code_challenge_methods_supported:["S256"]`, `token_endpoint_auth_methods_supported:["none"]`, `grant_types_supported:["authorization_code","refresh_token"]`, `scopes_supported:["mcp","offline_access"]`, `issuer` |
| `/oauth/register`                                                               | POST (JSON) | **DCR (RFC 7591)** : crée un `oauth_clients` public, renvoie `client_id` + metadata                                                                                                                                                                                                                                    |
| `/oauth/authorize`                                                              | GET / POST  | **Consentement** : login flask_login → gate abonnement → écran → code                                                                                                                                                                                                                                                  |
| `/oauth/token`                                                                  | POST (form) | grants `authorization_code` (+PKCE) et `refresh_token` (rotation)                                                                                                                                                                                                                                                      |
| `/oauth/revoke`                                                                 | POST (form) | **RFC 7009** (révocation ; peu coûteux)                                                                                                                                                                                                                                                                                |

### Flux `/authorize`

1. `server.get_consent_grant()` (authlib) valide `client_id`, `redirect_uri`
   (exact-match), `resource`, `code_challenge`.
2. `current_user` non authentifié → `redirect('/connexion?next=<authorize-url>')`,
   retour ici après login.
3. Connecté mais **pas d'abonnement actif** (`TOUS_ABONNES or has_active_subscription(user_id)` faux) → page HTML « Abonnement requis » + lien
   `/compte/abonnement`, **aucun code émis**.
4. Sinon → écran de consentement minimal : nom du client, **hostname du
   redirect_uri**, périmètre (« lire les données colibre en votre nom »),
   boutons Autoriser / Refuser.
5. **Autoriser** → `server.create_authorization_response(grant_user=current_user)` :
   `code_hash` stocké dans `oauth_codes` (avec `resource`, `code_challenge`),
   redirection vers le client.

### Flux `/token`

- `authorization_code` : authlib échange code + `code_verifier` (PKCE S256) →
  `oauth_tokens` (access 1 h, refresh 60 j, `resource` copié comme audience).
  Code invalide / `code_verifier` erroné → `invalid_grant`.
- `refresh_token` : **rotation** (ancien refresh révoqué, nouveau renvoyé dans la
  même réponse), et **re-vérification de l'abonnement** : si perdu → `invalid_grant`,
  ce qui force le client à relancer le flux complet (lequel rebute au gate
  `/authorize`).

## Garde `/_mcp` unifié (`src/mcp/auth.py`)

1. **401 enrichi** :
   `WWW-Authenticate: Bearer realm="colibre-mcp", resource_metadata="<base>/.well-known/oauth-protected-resource/_mcp"`.
2. **Routage du Bearer** :
   - préfixe `colibre_` → chemin statique existant (`api_tokens`, inchangé) ;
   - sinon → chemin OAuth (`oauth_tokens` : lookup haché, **non expiré**,
     **audience == `<base>/_mcp`**, non révoqué).
3. Convergence : `user_id` → abonnement actif → `increment_usage` →
   **`mcp_usage.record(user_id, token_id, kind)`** (best-effort) → laisser passer.
4. Échecs : token invalide / expiré / mauvaise audience / révoqué → **401** (avec
   le header) ; `user_id` nul ou abonnement inactif → **403**. Rien n'est journalisé
   dans `mcp_usage` sur échec.

## Abonnement : sémantique `TOUS_ABONNES` et « pas de droit acquis »

`TOUS_ABONNES` est lu au démarrage (constante d'`os.getenv`). L'abonnement est
**re-vérifié à chaque requête** `/_mcp`, pas seulement à l'émission du token :

| Moment                                       | Effet sur un token OAuth existant                                                                                                                                                            |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TOUS_ABONNES=true`                          | Tout utilisateur connecté franchit `/authorize`, obtient un token ; chaque requête `/_mcp` passe.                                                                                            |
| `TOUS_ABONNES` → `false` (après redémarrage) | Token ni supprimé ni révoqué, mais à la requête suivante le garde ré-évalue `False or has_active_subscription(user_id)`. Sans abonnement actif → **403** immédiat ; le token devient inerte. |
| L'utilisateur s'abonne ensuite               | Le **même** token refonctionne (garde de nouveau vrai), sans re-login.                                                                                                                       |

Il n'existe **aucune fenêtre de tolérance** : le check étant par requête, même un
token émis juste avant le basculement est bloqué dès l'appel suivant. Cohérent avec
le refresh (`invalid_grant` si abonnement perdu).

## Détection d'usage — niveau 1 (`src/mcp/usage.py`)

Objectif : rendre l'usage `/_mcp` **interrogeable** (socle d'un futur quota /
rate-limiting), sans encore plafonner.

- **`record(db_path, user_id, token_id, kind)`** : insère `(user_id, token_id, kind, created_at)` dans `mcp_usage`. Appelé par le garde après un succès. **Best-effort**
  (jamais bloquant).
- **`count_since(db_path, user_id, iso_ts) -> int`** : nombre de requêtes d'un
  utilisateur depuis un horodatage (base d'un futur seuil/minute).
- **`purge_older_than(db_path, days=90)`** : suppression des lignes anciennes,
  appelée **au démarrage** (mirror de `db.purge_expired_tokens()`), pour borner la
  croissance.

Signaux de détection disponibles **au total** après ce scope :

- **Matomo** (déjà câblé, scope A) : volume par tool dans le temps (anonyme).
- **Compteurs par token** : `count_total` / `last_used_at` (`api_tokens` +
  `oauth_tokens`), cumulatifs.
- **`mcp_usage`** : journal par requête, fenêtrable par utilisateur.
- **Logs d'accès** gunicorn/nginx : brut, par IP.

## UI `/compte/mcp` (`src/pages/compte/mcp.py`)

La page conserve son générateur de jetons statiques ; l'accordéon `client_instructions`
évolue :

- **Claude Code / Gemini / Mistral** : inchangés (jeton statique collé).
- **Claude.ai / Desktop / mobile** : nouvelle entrée « Aucun jeton à copier » →
  _Paramètres → Connecteurs → Ajouter un connecteur personnalisé → URL
  `https://colibre.fr/_mcp` → se connecter avec colibre → Autoriser_. Champ
  « Client Secret » laissé vide (client public).
- **ChatGPT** : remplace le texte « votez pour la fonctionnalité » par les étapes
  réelles (connecteurs → ajouter par URL `https://colibre.fr/_mcp` → flux OAuth) ;
  note que la disponibilité dépend du plan ChatGPT de l'utilisateur.
- Court paragraphe expliquant : **jeton = clients CLI**, **OAuth = apps grand
  public**, même abonnement requis.

Les tokens OAuth (éphémères, gérés par le client) ne sont **pas** listés dans le
tableau, qui reste réservé aux jetons statiques.

## Activation & configuration

- Toujours piloté par **`DASH_MCP_ENABLED=true`** (le flux OAuth ne s'enregistre que
  dans ce bloc de `app.py`, après `configure_mcp_server`).
- **`APP_BASE_URL`** sert d'**issuer** et à construire `resource` / URLs well-known.
  **HTTPS obligatoire** hors dev (exigence spec) ; localhost toléré en dev.
- **Aucun nouveau secret** (tokens opaques hachés ; `SECRET_KEY` déjà présent).
- `.template.env` : documenter que le flux OAuth requiert `APP_BASE_URL` en HTTPS et
  que l'egress Anthropic `160.79.104.0/21` doit être joignable.
- Déploiement recommandé : activer d'abord sur `test.colibre.fr` (branche `dev`),
  valider un connecteur Claude.ai réel, puis `main`.

## Stratégie de test

- **`tests/mcp/test_oauth_metadata.py`** : PRM (`resource` exact, `authorization_servers`,
  `scopes_supported` inclut `offline_access`) ; AS metadata
  (`code_challenge_methods_supported:["S256"]`, `none`, `registration_endpoint`,
  grants) ; `/.well-known/openid-configuration` = miroir ; variantes suffixées `/_mcp`.
- **`tests/mcp/test_oauth_store.py`** : CRUD clients/codes/tokens, hachage,
  expiration, rotation refresh, révocation.
- **`tests/mcp/test_oauth_flow.py`** : DCR → client public ; `/authorize`
  (non connecté → redirection ; connecté sans abonnement → « Abonnement requis »,
  **aucun code** ; avec abonnement → code) ; `/token` avec PKCE S256 (mauvais
  `code_verifier` → `invalid_grant`) ; `resource`/audience copiée ; redirect_uri
  non enregistrée → rejet.
- **`tests/mcp/test_auth.py`** (étendre) : garde accepte un token OAuth valide ;
  rejette expiré / mauvaise audience / révoqué (**401 + `resource_metadata`**) ;
  **`TOUS_ABONNES=false` + pas d'abonnement → 403 même avec token OAuth valide** ;
  refresh refusé (`invalid_grant`) si abonnement perdu.
- **`tests/mcp/test_usage.py`** (nouveau) : `record` insère sur succès ; **aucune
  insertion sur 401/403** ; fenêtrage de `count_since` ; `purge_older_than`.
- **Migration** : `apply_pending()` idempotente (DB existante → ajoute les tables ;
  DB fraîche → tolère _duplicate_).

## Hors-périmètre (YAGNI → itérations futures)

- **CIMD** (Client ID Metadata Document, spec MCP 2025-11-25) et redirect loopback
  port-agnostic (Claude Code passe déjà par jeton statique).
- `oauth_anthropic_creds`, `private_key_jwt`, mTLS, `id_token_hint`, tokens JWT/JWKS.
- **Rate-limiting / quotas / 429 / alerting** (niveaux 2-3) : `mcp_usage` en pose le
  socle, le plafonnement effectif fera l'objet d'une issue dédiée.
- Scopes fins par tool ; écran de gestion/révocation des connexions OAuth actives
  côté utilisateur.
- Soumission au directory de connecteurs Claude / ChatGPT.
