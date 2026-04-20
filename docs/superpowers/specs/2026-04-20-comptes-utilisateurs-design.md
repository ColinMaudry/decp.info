# Comptes utilisateurs — Design

**Date** : 2026-04-20
**Issue** : #73
**Branche** : `feature/73_compte_utilisateur`
**Spec initiale** : `comptes_utilisateurs.md`

## Objectif

Poser les fondations d'un système de comptes utilisateurs pour decp.info : inscription avec vérification d'email, connexion, réinitialisation de mot de passe, page compte permettant de changer son mot de passe. Ces fondations doivent permettre d'ajouter plus tard d'autres fonctionnalités (alertes email, préférences, etc.) sans avoir à retoucher l'authentification.

## Décisions de conception

| Sujet                              | Choix                                                           |
| ---------------------------------- | --------------------------------------------------------------- |
| Sessions                           | Flask-Login                                                     |
| Reset password                     | Token stocké en base (usage unique)                             |
| Vérification email à l'inscription | Obligatoire avant connexion                                     |
| Règles mot de passe                | Longueur ≥ 8 caractères, rien d'autre                           |
| Hashage mot de passe               | `werkzeug.security` (scrypt par défaut)                         |
| Lien navbar                        | Un seul lien « Connexion » (dropdown avec email quand connecté) |
| Pages                              | 5 pages Dash séparées avec URLs explicites                      |
| Base de données utilisateurs       | SQLite, chemin configurable via `USERS_DB_PATH`                 |
| Migrations                         | `CREATE TABLE IF NOT EXISTS` au démarrage                       |
| Accès SQLite                       | `sqlite3` stdlib, SQL brut avec requêtes paramétrées            |
| Envoi emails                       | Flask-Mail                                                      |
| Rate limiting                      | Aucun pour l'instant                                            |
| Tests                              | Unitaires + intégration Flask (pas de Selenium)                 |
| Format emails                      | HTML + texte brut (multipart)                                   |
| CSRF                               | Flask-WTF (CSRFProtect global)                                  |

## Architecture

### Nouvelles dépendances (`pyproject.toml`)

- `flask-login` — gestion des sessions utilisateur
- `flask-mail` — envoi SMTP
- `flask-wtf` — protection CSRF (uniquement CSRFProtect, pas d'utilisation des formulaires WTForms)
- `email-validator` — validation du format email à l'inscription

`itsdangerous` est déjà une dépendance transitive de Flask.

### Nouveau package `src/auth/`

| Fichier                | Rôle                                                                                                   |
| ---------------------- | ------------------------------------------------------------------------------------------------------ |
| `src/auth/__init__.py` | Exports publics (`current_user`, `login_required`, `init_auth`)                                        |
| `src/auth/db.py`       | Connexion SQLite, création schéma, requêtes CRUD                                                       |
| `src/auth/models.py`   | Classe `User` compatible Flask-Login                                                                   |
| `src/auth/mailer.py`   | Init Flask-Mail, helpers `send_verification_email`, `send_reset_email`                                 |
| `src/auth/tokens.py`   | Génération/validation tokens (vérif email, reset password)                                             |
| `src/auth/routes.py`   | Routes Flask POST (login, signup, logout, request reset, perform reset, verify email, change password) |
| `src/auth/setup.py`    | `init_auth(app)` appelé depuis `src/app.py`                                                            |

### Pourquoi des routes Flask natives plutôt que des callbacks Dash

Les actions d'authentification nécessitent de définir/effacer des cookies de session, rediriger entre pages, et manipuler `flask.session` — c'est le territoire de Flask, pas de Dash. Les callbacks Dash renvoient des composants React, pas des redirections HTTP avec cookies. Les pages Dash s'occupent du **rendu** (formulaires HTML), les routes Flask s'occupent des **actions** (POST).

### Nouvelles pages Dash (`src/pages/`)

| Fichier                         | URL                           | Description                                                                       |
| ------------------------------- | ----------------------------- | --------------------------------------------------------------------------------- |
| `connexion.py`                  | `/connexion`                  | Formulaire email + mot de passe, lien vers inscription, lien mot de passe oublié  |
| `inscription.py`                | `/inscription`                | Formulaire email + mot de passe + confirmation                                    |
| `compte.py`                     | `/compte`                     | Protégée. Affiche l'email, formulaire changement mot de passe, bouton déconnexion |
| `mot_de_passe_oublie.py`        | `/mot-de-passe-oublie`        | Formulaire de demande (email seul)                                                |
| `reinitialiser_mot_de_passe.py` | `/reinitialiser-mot-de-passe` | Formulaire nouveau mot de passe (token en query string)                           |
| `verification_email.py`         | `/verification-email`         | Page de statut après clic sur lien de vérification                                |

### Modifications de fichiers existants

- **`src/app.py`** : ajout de `init_auth(app)` après init du cache. Modification de la navbar pour afficher le lien « Connexion » (déconnecté) ou un `dbc.DropdownMenu` (connecté).
- **`pyproject.toml`** : ajout des dépendances listées ci-dessus et des variables d'env de tests dans `[tool.pytest.ini_options].env`.
- **`.template.env`** : ajout des nouvelles variables d'environnement.

### Nouvelles variables d'environnement

| Variable        | Exemple             | Description                                                             |
| --------------- | ------------------- | ----------------------------------------------------------------------- |
| `USERS_DB_PATH` | `users.sqlite`      | Chemin du fichier SQLite utilisateurs                                   |
| `SECRET_KEY`    | (32 octets random)  | Clé Flask pour sessions + signatures. Fail fast au démarrage si absente |
| `SMTP_HOST`     | `smtp.example.com`  | Serveur SMTP                                                            |
| `SMTP_PORT`     | `587`               | Port SMTP                                                               |
| `SMTP_USERNAME` | `…`                 | Identifiant SMTP                                                        |
| `SMTP_PASSWORD` | `…`                 | Mot de passe SMTP                                                       |
| `SMTP_USE_TLS`  | `True`              | STARTTLS                                                                |
| `MAIL_FROM`     | `noreply@decp.info` | Expéditeur                                                              |
| `APP_BASE_URL`  | `https://decp.info` | Base URL pour construire les liens absolus dans les emails              |

Si `SECRET_KEY` est absente au démarrage → `raise RuntimeError` (fail fast). Si les variables SMTP sont absentes → warning au démarrage, l'app démarre mais toute route déclenchant un envoi d'email retourne une erreur lisible.

## Schéma SQLite

Trois tables créées au démarrage via `CREATE TABLE IF NOT EXISTS`. Connexion initialisée avec :

```python
conn = sqlite3.connect(db_path, check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA journal_mode = WAL")
```

### Table `users`

| Colonne          | Type    | Contraintes                           |
| ---------------- | ------- | ------------------------------------- |
| `id`             | INTEGER | PRIMARY KEY AUTOINCREMENT             |
| `email`          | TEXT    | NOT NULL UNIQUE (stocké en lowercase) |
| `password_hash`  | TEXT    | NOT NULL                              |
| `email_verified` | INTEGER | NOT NULL DEFAULT 0 (0 ou 1)           |
| `created_at`     | TEXT    | NOT NULL (ISO 8601 UTC)               |
| `updated_at`     | TEXT    | NOT NULL (ISO 8601 UTC)               |

Index : `CREATE UNIQUE INDEX idx_users_email ON users(email)`.

### Table `email_verification_tokens`

| Colonne      | Type    | Contraintes                                         |
| ------------ | ------- | --------------------------------------------------- |
| `token_hash` | TEXT    | PRIMARY KEY (SHA-256 hex du token)                  |
| `user_id`    | INTEGER | NOT NULL, FOREIGN KEY → users(id) ON DELETE CASCADE |
| `expires_at` | TEXT    | NOT NULL (ISO 8601 UTC, typiquement +24h)           |
| `created_at` | TEXT    | NOT NULL                                            |

### Table `password_reset_tokens`

| Colonne      | Type    | Contraintes                                         |
| ------------ | ------- | --------------------------------------------------- |
| `token_hash` | TEXT    | PRIMARY KEY (SHA-256 hex du token)                  |
| `user_id`    | INTEGER | NOT NULL, FOREIGN KEY → users(id) ON DELETE CASCADE |
| `expires_at` | TEXT    | NOT NULL (ISO 8601 UTC, typiquement +1h)            |
| `created_at` | TEXT    | NOT NULL                                            |

### Principes sur les tokens

- **Stockage hashé** : on stocke `sha256(token)`, jamais le token en clair. Si la DB fuite, les tokens actifs restent inutilisables.
- **Génération** : `secrets.token_urlsafe(32)` → ~43 caractères URL-safe.
- **Usage unique** : à la validation réussie d'un token, on fait `DELETE FROM <table> WHERE user_id = ?` pour invalider tous les tokens actifs de l'utilisateur (pas uniquement celui utilisé).
- **Nouvelle demande** : avant de créer un nouveau token de reset, on supprime les anciens du même utilisateur.
- **Nettoyage périodique** : au démarrage de l'app, `DELETE FROM <table> WHERE expires_at < now()` sur les deux tables. Pas de cron nécessaire.

## Flux utilisateurs

### Flux A — Inscription

1. GET `/inscription` → formulaire Dash (email, mot de passe, confirmation).
2. Soumission POST `/auth/signup` avec token CSRF.
3. Serveur valide :
   - Format email (`email-validator`).
   - Longueur mot de passe ≥ 8.
   - `password == password_confirm`.
   - Email non déjà pris (lookup lowercase).
4. Création : `INSERT INTO users` avec `email_verified=0`, hash via `werkzeug.security.generate_password_hash`.
5. Génération token 32 octets, `INSERT INTO email_verification_tokens` (hash, expiration +24h).
6. Envoi email HTML+texte contenant `{APP_BASE_URL}/verification-email?token=…`.
7. **Si envoi KO** : rollback (`DELETE` user + token), erreur « Erreur technique, réessayez plus tard ».
8. **Si envoi OK** : redirection `/connexion?pending_verification=1` avec message « Compte créé, vérifie ton email ».

### Flux B — Vérification d'email

1. L'utilisateur clique sur le lien dans l'email → GET `/verification-email?token=…`.
2. La page Dash déclenche côté serveur la vérification via GET `/auth/verify-email?token=…`.
3. Serveur :
   - Hash le token reçu, cherche dans `email_verification_tokens` non expiré.
   - Si trouvé : `UPDATE users SET email_verified=1, updated_at=now()`, `DELETE FROM email_verification_tokens WHERE user_id = ?`, redirect `/connexion?verified=1`.
   - Sinon : redirect vers page d'erreur avec bouton « Renvoyer l'email de vérification ».

### Flux C — Connexion

1. GET `/connexion` → formulaire Dash.
2. POST `/auth/login`.
3. Serveur :
   - Lookup user par email lowercase.
   - **Toujours** appeler `check_password_hash()` (même si user inexistant, avec un hash bidon pré-calculé) pour uniformiser le temps de réponse.
   - Si user existe **et** password OK **et** `email_verified=1` → `login_user(user)` → redirect vers `next` validé ou `/compte`.
   - Si user existe mais `email_verified=0` → message « Vérifie d'abord ton adresse email » + bouton « Renvoyer email ».
   - Sinon → message générique « Identifiants invalides ».

### Flux D — Mot de passe oublié

1. GET `/mot-de-passe-oublie` → formulaire (email seul).
2. POST `/auth/request-password-reset`.
3. Serveur :
   - Message de retour **toujours identique** : « Si un compte existe avec cet email, un lien de réinitialisation a été envoyé. »
   - Si user trouvé : `DELETE` des anciens tokens reset, création d'un nouveau (expiration +1h), envoi email avec `{APP_BASE_URL}/reinitialiser-mot-de-passe?token=…`.
   - Si envoi SMTP KO : log serveur + message d'erreur technique (dérogation à la règle de non-énumération, pour éviter de masquer une panne SMTP).

### Flux E — Réinitialisation du mot de passe

1. GET `/reinitialiser-mot-de-passe?token=…`.
2. Page Dash : vérifie le token (sans le consommer) via un callback au rendu. Si invalide → message « Lien invalide ou expiré ». Si valide → affiche formulaire (nouveau mot de passe + confirmation).
3. POST `/auth/reset-password` avec token en champ caché + CSRF.
4. Serveur :
   - Revalide le token (hash, expiration).
   - Valide le mot de passe (longueur, confirmation).
   - `UPDATE users SET password_hash=…, updated_at=now()`.
   - `DELETE FROM password_reset_tokens WHERE user_id = ?`.
   - Redirect `/connexion?password_changed=1`.

### Flux F — Page compte

1. GET `/compte` protégée par `@login_required`. Déconnecté → redirect `/connexion?next=/compte`.
2. Page affiche l'email + formulaire « changer mot de passe » (mot de passe actuel + nouveau + confirmation) + bouton « Déconnexion ».
3. POST `/auth/change-password` : vérifie mot de passe actuel, valide le nouveau, update.
4. POST `/auth/logout` : `logout_user()`, redirect `/`.

### Navbar (`src/app.py`)

- **Déconnecté** : lien « Connexion » pointant vers `/connexion`, placé à droite (après « À propos »).
- **Connecté** : `dbc.DropdownMenu` affichant l'email tronqué (30 caractères max) avec :
  - Item « Mon compte » → `/compte`
  - Item « Déconnexion » → soumission POST vers `/auth/logout` (form avec CSRF)

## Gestion des erreurs et sécurité

### Messages d'erreur utilisateur

- Transit des messages via **query string** (ex : `?error=invalid_credentials`, `?verified=1`) avec mapping code → message côté page Dash. Plus simple à tester et stateless que `flash()`.
- Rendu via `dbc.Alert` en haut du formulaire (couleurs danger/success/info).

### Sécurité des cookies et sessions

- `SESSION_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SAMESITE = 'Lax'`
- `SESSION_COOKIE_SECURE = True` en production (conditionnel sur `DEVELOPMENT=False`)
- Durée de session : 30 jours (« remember me » implicite, permanent session)

### Protection CSRF

- `CSRFProtect(app.server)` installé globalement depuis `init_auth`.
- Chaque formulaire Dash inclut un champ caché `csrf_token` rempli via un callback au rendu (`generate_csrf()` depuis `flask_wtf.csrf`).
- Toutes les routes POST sont protégées automatiquement.

### Protection contre l'énumération de comptes

- Login : même message pour email inexistant et mot de passe faux.
- Request password reset : même message pour email existant et inexistant (sauf en cas de panne SMTP, où l'erreur technique prime).
- Timing : toujours appeler `check_password_hash` même si user inexistant.

### Validation des redirections `next`

```python
def safe_next(url: str, fallback: str = "/") -> str:
    if not url or not url.startswith("/") or url.startswith("//"):
        return fallback
    return url
```

### Tokens

- Entropie : 32 octets via `secrets.token_urlsafe(32)`.
- Stockage : SHA-256 hex.
- Usage unique (voir schéma SQLite).
- Expiration : 24h (vérif email), 1h (reset password).

### Mots de passe dans les logs

Audit rapide du code au moment de la revue : aucun `print`/`logger.debug` ne doit logger mot de passe ou token en clair. Formulaires d'inscription/login/reset loggent uniquement l'email (et encore, seulement en cas d'erreur).

### Pannes SMTP

- **Inscription** : envoi synchrone, échec → rollback de l'inscription, erreur technique affichée.
- **Reset password** : envoi synchrone, échec → erreur technique (dérogation au message générique).
- **Changement de mot de passe** : pas d'email → pas de dépendance SMTP pour ce flux.
- **Vérification email (renvoyer)** : échec → erreur technique.

### Configuration manquante au démarrage

- `SECRET_KEY` absente → `raise RuntimeError` (fail fast).
- Variables SMTP absentes → warning loggué, app démarre ; routes nécessitant SMTP retournent erreur lisible.
- `USERS_DB_PATH` absente → fallback sur `users.sqlite` à la racine.
- `APP_BASE_URL` absente → fallback sur `http://localhost:8050`.

## Emails (HTML + texte)

Templates simples dans `src/auth/templates/emails/` :

- `verify_email.html` et `verify_email.txt`
- `reset_password.html` et `reset_password.txt`

Chaque email contient :

- Salutation neutre (« Bonjour, »)
- Une phrase expliquant le contexte
- Le lien en clair (cliquable en HTML)
- Une phrase sur l'expiration (« Ce lien est valide 24h / 1h »)
- Un mot final (« Si vous n'êtes pas à l'origine de cette demande, ignorez cet email »)
- Pas de logo complexe ; un en-tête texte `decp.info` en gras suffit

## Tests

### Structure `tests/auth/`

- `conftest.py` — fixtures : base SQLite temporaire, capture emails (monkeypatch `mail.send`), `client` (Flask test client), `authed_client`, `SECRET_KEY` fixe.
- `test_db.py` — CRUD users, unicité email case-insensitive, cascade suppression tokens.
- `test_tokens.py` — génération, hash stable, validation, rejet expiré/invalide, invalidation à l'usage.
- `test_signup.py` — GET formulaire, POST validé, doublon rejeté, password trop court rejeté, email invalide rejeté, login avant vérif refusé.
- `test_verify_email.py` — token valide marque vérifié et supprime token, token expiré rejeté, token déjà utilisé rejeté.
- `test_login.py` — succès (cookie posé), mot de passe faux rejeté (message générique), email inexistant rejeté avec même message, user non vérifié rejeté, redirection `next` validée (rejet URLs absolues).
- `test_password_reset.py` — demande envoie email, email inexistant → même message sans envoi, token valide permet changement, token expiré rejeté, login avec nouveau mot de passe OK, ancien KO.
- `test_account.py` — `/compte` redirige si déconnecté, change password OK avec mot de passe actuel correct, KO sinon, logout efface session.
- `test_csrf.py` — POST sans token rejeté (403), POST avec token valide accepté.

### Fixture clé

```python
@pytest.fixture
def mail_outbox(monkeypatch):
    outbox = []
    monkeypatch.setattr(
        "src.auth.mailer.mail.send",
        lambda msg: outbox.append(msg),
    )
    return outbox
```

### Configuration pytest (`pyproject.toml`)

Ajout au bloc `[tool.pytest.ini_options].env` :

```
USERS_DB_PATH=tests/users.test.sqlite
SECRET_KEY=test-secret-do-not-use-in-prod
MAIL_FROM=test@decp.info
APP_BASE_URL=http://localhost:8050
SMTP_HOST=localhost
SMTP_PORT=25
```

### Non couvert (explicitement)

- Tests Selenium sur les formulaires (ajoutables plus tard si parcours critiques).
- Tests de charge SMTP.
- Tests cross-browser.
- Vérification que les tests existants (`tests/test_main.py`) ne cassent pas : l'auth est ajoutée sans modifier les comportements existants (navbar garde un lien « Connexion » par défaut, pas de redirection ajoutée sur les pages publiques).

## Risques et contraintes

- **SMTP indisponible en dev** : tout développeur doit pouvoir tester sans SMTP réel. Prévoir un mode dev où les emails sont loggés dans la console au lieu d'être envoyés (ex : `MAIL_SUPPRESS_SEND=True` de Flask-Mail quand `DEVELOPMENT=True`, avec impression du lien dans le log).
- **Clé de signature (SECRET_KEY)** : la rotation invalidera toutes les sessions actives. À documenter dans le README de deploy.
- **Base SQLite + WAL** : la base est accessible en lecture/écriture par le process de l'app. En cas de plusieurs workers gunicorn, WAL gère correctement la concurrence pour un nombre modéste d'écritures (inscriptions, resets, login updates) — acceptable pour le volume attendu.
- **Concurrence sur `users` depuis plusieurs workers gunicorn** : une seule connexion SQLite par process avec WAL est OK ; pas de connexion partagée entre workers.
