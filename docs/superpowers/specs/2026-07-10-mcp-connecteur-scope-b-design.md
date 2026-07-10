# Scope B — Connecteur MCP : accès abonné par jeton Bearer

**Issue :** #111 (2ᵉ partie, « le point dur »)
**Date :** 2026-07-10
**Statut :** approuvé (design)
**Prérequis :** scope A livré et fusionné dans `dev` (serveur MCP `/_mcp`, `src/mcp/`).

## Objectif

Conditionner l'accès au serveur MCP colibre (`/_mcp`, livré en scope A) à un
**abonnement colibre actif**, via un **jeton Bearer statique dédié** que l'abonné
génère lui-même depuis son espace compte et colle dans la configuration de son
agent IA.

Ce scope **n'implémente pas** de serveur OAuth. Le flux OAuth 2.1 complet
(bouton « Connecter », enregistrement dynamique de client, PKCE) est explicitement
reporté à un **scope B2** ultérieur, si l'usage le justifie.

## Décisions de conception (arbitrées)

1. **Jeton statique**, pas de serveur OAuth. Réutilise l'infrastructure
   `api_tokens` (table SQLite, jetons `colibre_…` hachés) et
   `has_active_subscription(user_id)` existantes.
2. **Jetons dédiés MCP** : une colonne `kind` distingue les jetons. Un jeton MCP
   ne fonctionne que sur `/_mcp` ; un jeton API (`kind='api'`, tous les jetons
   CLI actuels) ne fonctionne que sur `/api/v1`.
3. **Garde d'abonnement uniquement sur `/_mcp`**. Le comportement de l'API REST
   existante est inchangé pour les jetons `kind='api'`.
4. **Libellé du menu** dans `/compte` : « Connecteur MCP ».
5. **Instructions de connexion** pour 4 clients : Claude, Gemini, Mistral (jeton
   statique — supporté), ChatGPT (voir §7, caveat).

## Périmètre du support client (vérifié 2026-07)

| Client                      | En-tête Bearer statique | Voie documentée sur la page                                                                                                                                                                                       |
| --------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Claude** (Code / Desktop) | ✅                      | `claude mcp add colibre --transport http <url>/_mcp --header "Authorization: Bearer …"`                                                                                                                           |
| **Gemini CLI**              | ✅                      | `gemini mcp add --transport http --header "Authorization: Bearer …"` ou `httpUrl`+`headers` dans `settings.json`                                                                                                  |
| **Mistral Le Chat**         | ✅                      | Connecteur MCP → auth « API Token », en-tête `Authorization: Bearer …`                                                                                                                                            |
| **ChatGPT** (app)           | ❌                      | L'app exige OAuth 2.1 + PKCE (pas de clé statique). Documenter la voie **développeur** (OpenAI API / Agents SDK, qui accepte un en-tête statique) + note « app ChatGPT = connecteur OAuth, itération future B2 ». |

## Architecture & flux

```
Abonné → /compte/mcp (« Connecteur MCP », gardé require_subscription)
        → [Générer un jeton] → colibre_xxxx (affiché UNE fois) + snippet client

Agent IA → POST /_mcp   (Authorization: Bearer colibre_xxxx)
         → before_request guard (src/mcp/auth.py) :
             • pas de Bearer / jeton introuvable / révoqué / kind≠'mcp' → 401
             • jeton MCP valide mais user_id nul ou abonnement inactif   → 403
             • OK → increment_usage(token_id) → Dash traite la requête MCP
```

## Composants

### 1. Couche données — `src/api/tokens_db.py`

- **Schéma** : ajouter `kind TEXT NOT NULL DEFAULT 'api'` à `api_tokens`.
  - `SCHEMA` (CREATE) inclut la colonne → DB fraîche correcte.
  - **Migration** dans `src/migrations.py` `_MIGRATIONS` :
    `("0007_add_kind_to_api_tokens", "ALTER TABLE api_tokens ADD COLUMN kind TEXT NOT NULL DEFAULT 'api'")`.
    L'erreur _duplicate column name_ est déjà tolérée par `apply_pending()`
    (DB fraîche où `SCHEMA` a déjà créé la colonne).
- **Initialisation au démarrage** : `init_api()` appelle
  `tokens_db.init_schema(USERS_DB_PATH)` (comme `saved_views`/`roadmap`), pour
  garantir que la table existe **avant** que `apply_pending()` (appelée plus tard
  dans `init_subscriptions`) ne tente l'`ALTER`. Ordre dans `app.py` :
  `init_api` (ligne ~112) précède `init_subscriptions` (ligne ~129). ✅
- **Fonctions** :
  - `create_token(db_path, label, user_id=None, kind='api') -> (token, id)` —
    paramètre `kind` ajouté.
  - `list_user_tokens(db_path, user_id, kind='mcp') -> list[dict]` — jetons d'un
    utilisateur d'un type donné, triés par `created_at` décroissant.
  - `revoke_user_token(db_path, token_id, user_id) -> bool` —
    `WHERE id=? AND user_id=?` (anti-IDOR). Retourne `True` si une ligne a été
    révoquée, `False` sinon (jeton inexistant ou d'un autre utilisateur).
  - `increment_usage` et `get_token_by_plaintext` existants, réutilisés tels quels.

### 2. Garde `/_mcp` — nouveau `src/mcp/auth.py`

- `init_mcp_auth(server: Flask) -> None` enregistre un `@server.before_request`
  qui **ne s'active que** si `request.path == "/_mcp"` ou commence par `/_mcp/`.
- Logique :
  1. Lire l'en-tête `Authorization`. Absent ou pas `Bearer ` → **401**.
  2. `get_token_by_plaintext` → introuvable → **401** ; `revoked_at` non nul →
     **401** ; `kind != 'mcp'` → **401** (un jeton API ne donne pas accès au MCP).
  3. `user_id` nul → **403** ; `has_active_subscription(user_id)` faux (en
     respectant `TOUS_ABONNES`) → **403**.
  4. Succès → `increment_usage(db_path, token_id)`, laisser passer (`return None`).
- **Codes & en-têtes** :
  - 401 : corps JSON `{"error": "unauthorized", "message": …}` +
    `WWW-Authenticate: Bearer realm="colibre-mcp"`.
  - 403 : corps JSON `{"error": "no_active_subscription", "message": …}`.
  - Messages en français, sans divulguer si le jeton existe (401 générique).
- Enregistré dans le bloc `if _mcp_enabled:` de `app.py`, après
  `configure_mcp_server(...)`.

### 3. Exemption CSRF — `src/app.py`

- La boucle d'exemption CSRF actuelle cible `/_dash*` et `/_reload*`. Ajouter
  `/_mcp` : `_rule.rule.startswith("/_mcp")`. `/_mcp` reçoit des POST JSON-RPC
  externes sans jeton CSRF possible. (Le webhook Frisbii est déjà exempté de la
  même façon.)

### 4. UI self-service — `src/pages/compte/mcp.py`

- **Section** ajoutée à `src/pages/_compte_shell.py` `SECTIONS` :
  `{"key": "mcp", "label": "Connecteur MCP", "href": "/compte/mcp", "require_subscription": True}`.
  Placée avant « Abonnement ». La garde de section existante redirige vers
  `/compte/abonnement` si pas d'abonnement actif.
- **Page** `@register_page` sur `/compte/mcp`, enveloppée par `account_shell` +
  `account_guard("/compte/mcp", require_subscription=True)`, suivant le patron des
  autres pages `compte/`.
- **Contenu** :
  1. Explication courte : ce qu'est le connecteur MCP, qu'il faut un abonnement
     actif, que le jeton vaut identité (à garder secret).
  2. **Tableau** des jetons MCP de l'utilisateur : label, créé le, dernière
     utilisation, statut (actif/révoqué), bouton **Révoquer** par jeton actif.
  3. **Formulaire de création** : champ « label » (ex. « Claude sur mon portable »)
     - bouton. À la création, le jeton en clair est **affiché une seule fois**
       (jamais re-stocké en clair), avec bouton copier.
  4. **Instructions par client** (accordéon/onglets) : Claude, Gemini, Mistral,
     ChatGPT — chacune avec le snippet de §7, le jeton fraîchement créé injecté
     dans le snippet, et l'URL `<APP_BASE_URL>/_mcp`.
- **Implémentation** : callbacks Dash + inputs CSRF, comme les autres pages
  `compte/`. Création via `create_token(..., kind='mcp', user_id=current_user.id)` ;
  liste via `list_user_tokens(..., current_user.id, 'mcp')` ; révocation via
  `revoke_user_token(..., token_id, current_user.id)`. Toute action vérifie
  `current_user.is_authenticated` et l'abonnement côté serveur (pas seulement
  masquée dans l'UI — cf. points de vigilance sécurité de l'issue).

### 5. API REST inchangée — `src/api/auth.py`

- `require_token` : ajouter un filtre pour **refuser** les jetons `kind='mcp'`
  (401), afin que les jetons dédiés MCP ne fonctionnent pas sur `/api/v1`. Les
  jetons `kind='api'` (tous les jetons CLI existants) restent acceptés à
  l'identique → aucun changement de comportement pour l'existant.
- Nettoyer le `print(API_AUTH_DISABLED)` de débogage présent ligne 19 (bruit).

### 6. Activation & configuration

- Le garde rend `DASH_MCP_ENABLED=true` **sûr en production** (accès
  systématiquement conditionné à l'abonnement). Le défaut reste **`false`**
  (tests inchangés, pas de flip automatique dans le code).
- Déploiement recommandé : activer d'abord sur `test.colibre.fr` (branche `dev`)
  via la variable d'environnement, valider, puis `main`.
- `.template.env` : documenter que `DASH_MCP_ENABLED=true` requiert le connecteur
  (scope B) et un abonnement actif côté client.
- `APP_BASE_URL` (déjà utilisé pour le callback LinkedIn) sert à construire l'URL
  `/_mcp` dans les snippets. Si absent, la page affiche l'URL relative + un
  avertissement (comportement dégradé, non bloquant).

### 7. Instructions par client (contenu de la page)

> `<URL>` = `<APP_BASE_URL>/_mcp` (ex. `https://colibre.fr/_mcp`) ;
> `<TOKEN>` = jeton fraîchement généré.

- **Claude (Code / Desktop)** :
  `claude mcp add colibre --transport http <URL> --header "Authorization: Bearer <TOKEN>"`
- **Gemini CLI** :
  `gemini mcp add --transport http --header "Authorization: Bearer <TOKEN>" colibre <URL>`
  (ou bloc `settings.json` : `mcpServers.colibre.httpUrl` + `headers.Authorization`).
- **Mistral Le Chat** : dans les connecteurs MCP, ajouter un serveur HTTP
  d'URL `<URL>`, authentification « API Token », en-tête `Authorization` =
  `Bearer <TOKEN>`.
- **ChatGPT** : l'app grand public exige OAuth 2.1 (pas de jeton statique) →
  documenter la voie **développeur** (OpenAI API / Agents SDK) qui accepte un
  en-tête `Authorization: Bearer <TOKEN>` sur un serveur MCP distant, et noter
  que la prise en charge dans l'app ChatGPT nécessitera le connecteur OAuth
  (**scope B2**, itération future).

## Stratégie de test

- **`tests/api/test_tokens_db.py`** (étendre) : colonne `kind` par défaut `'api'` ;
  `create_token(kind='mcp')` ; `list_user_tokens` filtre par user_id + kind ;
  `revoke_user_token` respecte la propriété (un user ne peut pas révoquer le jeton
  d'un autre → retourne `False`, ligne intacte).
- **`tests/mcp/test_auth.py`** (nouveau) : garde `/_mcp` —
  401 (pas d'en-tête / `Bearer` vide / jeton inconnu / jeton révoqué /
  jeton `kind='api'`) ; 403 (jeton `kind='mcp'` valide mais `user_id` nul ou
  abonnement inactif) ; passage (jeton MCP + abonnement actif, ou `TOUS_ABONNES`) ;
  `increment_usage` appelé en cas de succès ; en-tête `WWW-Authenticate` sur 401.
- **`tests/api/test_api_auth.py`** (étendre) : `require_token` refuse un jeton
  `kind='mcp'`, accepte un jeton `kind='api'`.
- **Migration** : `apply_pending()` idempotente sur DB existante (ajoute `kind`)
  et sur DB fraîche (tolère _duplicate column_).
- **UI** (`tests/…` selon patron compte) : génération → affichage unique du jeton ;
  révocation ; redirection `/compte/abonnement` sans abonnement ; anti-IDOR
  (révocation limitée aux jetons de l'utilisateur courant).

## Hors périmètre (YAGNI)

- Serveur d'autorisation OAuth 2.1 / DCR / PKCE / consentement (→ scope B2).
- Rate-limiting, quotas par jeton, scopes fins par tool MCP.
- Refonte de l'API REST (`/api/v1` inchangée hormis le refus des jetons MCP).
- Support natif de l'app ChatGPT (nécessite OAuth → scope B2).
- Rotation / expiration automatique des jetons (révocation manuelle suffit pour V1).

## Points de vigilance sécurité (rappel issue #111)

- Toute règle d'accès (abonnement, propriété du jeton) est **appliquée
  explicitement côté serveur**, jamais seulement masquée dans l'UI.
- Le jeton en clair n'est affiché qu'une fois ; seul son hachage SHA-256 est stocké.
- 401 générique (ne pas révéler si un jeton existe).
- Révocation et listing strictement limités au propriétaire (`user_id`).
