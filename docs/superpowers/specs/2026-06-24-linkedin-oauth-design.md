# Connexion avec LinkedIn (OIDC) — Design

Date : 2026-06-24
Branche : `dev`

## Objectif

Permettre aux utilisateurs de créer un compte / se connecter à decp.info via
LinkedIn, comme les boutons « Se connecter avec Google/GitHub » d'autres sites.
Beaucoup d'utilisateurs viennent de LinkedIn ; réduire la friction d'inscription.

Portée : **LinkedIn uniquement** (pas d'abstraction multi-provider pour
l'instant). Code simple et direct.

## Mécanisme

LinkedIn fournit _« Sign In with LinkedIn using OpenID Connect »_ (OIDC).
On utilise la bibliothèque **Authlib** (intégration Flask) : elle gère la
découverte OIDC, la redirection, l'échange `code → token`, la validation du
token et le `state` anti-CSRF. Scopes demandés : `openid profile email`.

On ne stocke que l'**email** (comme l'auth existante), pas le nom ni la photo.

## Flux

1. L'utilisateur clique sur **« Connexion avec LinkedIn »** (présent sur
   `/connexion` et `/inscription`).
2. `GET /auth/linkedin` → Authlib redirige vers LinkedIn.
3. L'utilisateur autorise → LinkedIn redirige vers
   `GET /auth/linkedin/callback?code=...&state=...`.
4. Authlib échange le `code`, valide le token, expose l'identité OIDC :
   `sub`, `email`, `email_verified`.
5. Résolution / liaison du compte (voir ci-dessous).
6. `login_user(user, remember=True)` → redirection vers `/compte/admin`
   (ou le `next` validé via `safe_next`).

## Schéma (migrations additives, dans `db._migrate`)

- `users.password_hash` devient **nullable** : un compte créé via LinkedIn n'a
  pas de mot de passe. Un tel utilisateur pourra s'en créer un plus tard via
  le flux « mot de passe oublié ».

  - SQLite ne permet pas de retirer un `NOT NULL` par `ALTER COLUMN`. La
    migration recrée la table `users` sans la contrainte `NOT NULL` sur
    `password_hash` si elle est encore présente (copie des données,
    `PRAGMA table_info` pour détecter l'état). Les nouvelles installations
    créent directement le schéma sans `NOT NULL` sur `password_hash`.

- Nouvelle table :

  ```sql
  CREATE TABLE IF NOT EXISTS oauth_identities (
      provider     TEXT NOT NULL,        -- 'linkedin'
      subject      TEXT NOT NULL,        -- le 'sub' OIDC stable
      user_id      INTEGER NOT NULL,
      created_at   TEXT NOT NULL,
      PRIMARY KEY (provider, subject),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );
  ```

## Résolution / liaison du compte (au callback)

Logique extraite dans une fonction testable `resolve_oauth_user(provider, subject, email, email_verified)` :

1. Si `(linkedin, sub)` existe dans `oauth_identities` → on connecte le
   `user_id` lié.
2. Sinon, si un `user` existe déjà avec cet **email** → **liaison
   automatique** : insert dans `oauth_identities`, et si `email_verified`
   était `0`, on le passe à `1` (LinkedIn garantit un email vérifié).
3. Sinon → **création** d'un nouvel utilisateur (`email`,
   `password_hash = NULL`, `email_verified = 1`) + insert `oauth_identities`.
   Aucun email de vérification Brevo n'est envoyé.

Décision produit : la liaison par email est automatique (l'email LinkedIn est
vérifié, le risque est faible).

## Fichiers touchés

- **`src/auth/oauth.py`** (nouveau) : `init_oauth(app)` — initialise Authlib et
  enregistre le provider LinkedIn (config OIDC, client id/secret depuis l'env).
- **`src/auth/routes.py`** : deux routes
  - `GET /auth/linkedin` — démarre le flux (`authorize_redirect`).
  - `GET /auth/linkedin/callback` — récupère l'identité, appelle
    `resolve_oauth_user`, `login_user`, redirige.
  - `resolve_oauth_user(...)` — logique de résolution (testable).
- **`src/auth/db.py`** : schéma `oauth_identities`, migration `password_hash`
  nullable, helpers `get_oauth_identity(provider, subject)`,
  `link_oauth_identity(provider, subject, user_id)`,
  `create_oauth_user(email)`.
- **`src/auth/setup.py`** : appel à `init_oauth(app)`.
- **`src/pages/connexion.py`** et **`src/pages/inscription.py`** : bouton
  « Connexion avec LinkedIn ».
- **`pyproject.toml`** : ajout de la dépendance `authlib`.
- **`.template.env`** : `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`.

## UI du bouton

- Libellé : **« Connexion avec LinkedIn »**.
- Style : texte blanc sur fond `rgb(10, 102, 194)` (bleu de marque LinkedIn,
  `#0A66C2`).
- Un lien `<a href="/auth/linkedin">` (initiation par GET, pas de CSRF requis),
  placé sous le formulaire email/mot de passe, séparé par un « ou ».
- Présent sur `/connexion` et `/inscription`.

## Gestion d'erreurs

- L'utilisateur annule / refuse sur LinkedIn → `/connexion?error=oauth_cancelled`.
- Échange de token échoué, ou pas d'email renvoyé par LinkedIn →
  `/connexion?error=oauth_failed` (loggé via `logger.exception`).
- `state` invalide → détecté par Authlib → `oauth_failed`.
- Messages ajoutés dans `ERROR_MESSAGES` de `connexion.py`.

## Tests (dans `tests/auth/`)

Sans appel réseau réel à LinkedIn : on **mocke** le retour `userinfo` /
l'identité OIDC exposée par Authlib.

- `resolve_oauth_user` :
  - nouvel utilisateur (création + `email_verified = 1`, pas de password).
  - liaison par email à un compte existant (insert identity, promotion
    `email_verified`).
  - identité déjà liée (retour du même `user_id`, pas de doublon).
- Migration : `password_hash` accepte `NULL` ; table `oauth_identities` créée.
- Helpers db : `get_oauth_identity`, `link_oauth_identity`, `create_oauth_user`.

## Prérequis hors code (côté admin du projet)

1. Créer une application sur le **LinkedIn Developer Portal**.
2. Activer le produit _« Sign In with LinkedIn using OpenID Connect »_.
3. Déclarer les redirect URIs autorisées :
   - `http://localhost:8050/auth/linkedin/callback` (dev)
   - `https://test.decp.info/auth/linkedin/callback` (test.decp.info)
   - `https://decp.info/auth/linkedin/callback` (prod)
4. Récupérer le **Client ID** et le **Client Secret**, les renseigner dans
   `.env` (`LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`).

L'URL de callback est construite à partir de `APP_BASE_URL` (déjà présent dans
l'env).

## Hors périmètre (YAGNI)

- Google / GitHub / autres providers.
- Stockage du nom ou de la photo de profil LinkedIn.
- Page de gestion « délier mon compte LinkedIn » (pourra venir plus tard).
