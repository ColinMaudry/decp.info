# Panneau admin interne (`/admin`)

Date : 2026-07-03
Statut : design validé

## Contexte

Pour le débuggage et le support utilisateur, il n'existe aujourd'hui aucun
moyen de consulter ou corriger l'état d'un compte (`users.sqlite`) sans passer
par SQL en direct sur le serveur. On ajoute un panneau admin interne,
accessible à une seule adresse email (variable d'env `ADMIN_EMAIL`), pour
consulter la liste des comptes, l'historique complet des abonnements Frisbii
d'un compte, et corriger manuellement un statut d'abonnement en cas de
désynchronisation avec Frisbii — avec une trace de chaque action.

Flask-Admin a été écarté : ses `ModelView` supposent un ORM (SQLAlchemy,
Peewee, MongoEngine) alors que `src/auth/db.py` et `src/subscriptions/db.py`
utilisent `sqlite3` brut. Le gain de Flask-Admin (génération auto des
formulaires/listes depuis des modèles ORM) ne s'applique donc pas ici.

## Architecture générale

Le panneau reprend le pattern déjà utilisé pour `/compte/*` (voir
[2026-06-24-espace-compte-design.md](2026-06-24-espace-compte-design.md)) :
des pages Dash (`register_page`) pour la lecture, un Blueprint Flask pour les
mutations (POST + redirect + query params pour les messages), le tout sur le
même serveur Flask (`use_pages=True`, `src/app.py:87`) où les blueprints
enregistrés (`src/auth/routes.py:auth_bp`) coexistent avec le routage de
pages Dash sans collision, du moment que les chemins ne se recouvrent pas.

### Pages Dash (lecture)

Nouveau package `src/pages/admin/` (miroir de `src/pages/compte/`) :

- `src/pages/admin/liste.py` → `/admin`
- `src/pages/admin/detail.py` → `path_template="/admin/user/<user_id>"`,
  avec `def layout(user_id=None, **_):`. Dash injecte le segment dynamique
  comme argument nommé de `layout()`, exactement comme `compte/admin.py`
  reçoit déjà ses paramètres de query string
  (`layout(error=None, password_changed=None, ...)`,
  `src/pages/compte/admin.py:176`). C'est délibérément différent du pattern
  utilisé par `acheteur.py`/`marche.py` (`path_template` + layout statique +
  parsing de `pathname` côté client dans un callback,
  ex. `src/pages/acheteur.py:52`) : ces pages n'ont pas de contrôle d'accès
  serveur, alors qu'ici `admin_guard`/`get_user_by_id` doivent s'exécuter
  côté serveur avant le rendu, donc `user_id` doit être disponible
  synchrone dans `layout()`.
- `src/pages/admin/journal.py` → `/admin/journal`

### Blueprint Flask (mutations)

Nouveau module `src/admin/routes.py`, `Blueprint("admin", __name__, url_prefix="/admin/actions")`, enregistré dans `src/auth/setup.py`
(`init_auth`) juste après `app.register_blueprint(auth_bp)`. Une seule route :

- `POST /admin/actions/subscription-status`

### Garde d'accès

Nouveau module `src/admin/guard.py` :

```python
def is_admin() -> bool:
    admin_email = os.getenv("ADMIN_EMAIL")
    return bool(
        admin_email
        and current_user.is_authenticated
        and current_user.email.lower() == admin_email.lower()
    )
```

Utilisée aux deux points d'entrée :

- Dans chaque `layout()` Dash (`src/pages/admin/*.py`) : si `not is_admin()`,
  retourne un composant "404" simple (`html.H1("404")` — pas de redirect, pour
  ne pas laisser deviner l'existence de la route à un compte non-admin) au
  lieu du contenu de la page.
- Dans le blueprint (`before_request` du blueprint `admin`) : si
  `not is_admin()`, `abort(404)`. Défense en profondeur — la route de mutation
  ne doit pas dépendre uniquement du fait que l'UI qui y pointe soit cachée.

Nouvelle variable d'env `ADMIN_EMAIL` ajoutée à `.template.env`, dans une
nouvelle section `# Panneau admin (accès à /admin)`.

## Couche données

Pas de nouvelle table de schéma pour users/subscriptions ; une seule nouvelle
table pour le journal d'audit (voir plus bas), ajoutée via une migration
`src/migrations.py` comme documenté dans `CLAUDE.md`.

### `src/auth/db.py`

```python
def list_users(limit: int = 1000) -> list[sqlite3.Row]:
    """Tous les users, plus récents en premier, plafonné à `limit`."""
```

### `src/subscriptions/db.py`

```python
def list_by_user(user_id: int) -> list[sqlite3.Row]:
    """Historique complet des abonnements d'un user, plus récent en premier."""
    # SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC

def set_status(subscription_id: int, status: str) -> None:
    """Force le statut d'un abonnement (correction manuelle)."""
    # UPDATE subscriptions SET status = ?, updated_at = ? WHERE id = ?
```

`get_current(user_id)` (déjà existant, `src/subscriptions/db.py:115`) reste
utilisé pour identifier l'abonnement "courant" à afficher en tête de liste et
cibler par défaut dans le formulaire de changement de statut.

Statuts valides (déduits de `src/subscriptions/webhooks.py:map_subscription`) :
`active`, `trial`, `cancelled`, `expired`, `pending`. Cette liste est
centralisée dans une constante `SUBSCRIPTION_STATUSES` (nouveau, dans
`src/subscriptions/db.py` ou `plans.py`) réutilisée à la fois pour peupler le
dropdown du formulaire et pour valider côté route.

### Table d'audit `admin_actions`

Migration `src/migrations.py` (id `0006_create_admin_actions`) :

```sql
CREATE TABLE IF NOT EXISTS admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_email TEXT NOT NULL,
    action TEXT NOT NULL,
    target_user_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL
)
```

Nouveau module `src/admin/db.py` (réutilise `get_conn()` de
`src/auth/db.py`, même fichier `users.sqlite`) :

```python
def log_action(admin_email: str, action: str, target_user_id: int | None,
                details: str | None) -> None: ...

def list_actions(limit: int = 200) -> list[sqlite3.Row]: ...
```

## Pages

### `/admin` (liste)

- Garde d'accès en tête de `layout()`.
- `dash_table.DataTable(filter_action="native", sort_action="native", page_action="native", page_size=20, ...)` alimenté par `list_users()` —
  filtrage/tri/pagination entièrement côté navigateur (pas de callback
  serveur), à la différence de `/tableau` dont le `filter_action="custom"`
  (`src/pages/tableau.py:74`) n'existe que pour déléguer le filtrage à DuckDB
  sur ~1,5M lignes ; ici quelques centaines de lignes au plus, le mode natif
  suffit pour les trois (20 lignes par page).
- Colonnes : email, email vérifié, plan courant, statut courant, créé le.
- Lien "Voir" par ligne vers `/admin/user/<id>`.
- Lien vers `/admin/journal` dans l'en-tête de page.

### `/admin/user/<user_id>` (détail)

- Garde d'accès, puis `get_user_by_id(user_id)` ; si absent, composant "user
  introuvable" (pas une 500).
- **Compte** : email, email vérifié, siret, créé le.
- **État abonné** (`subscriber_state`) : votes_balance, trial_used —
  affichage seul, pas d'édition dans ce lot.
- **Historique des abonnements** (`list_by_user`) : table triée (plus récent
  en haut), badge "actuel" sur la ligne correspondant à `get_current`.
- **Changer le statut** : formulaire ciblant l'abonnement courant — dropdown
  des statuts valides + bouton, POST vers `/admin/actions/subscription-status`
  avec champs cachés `user_id`, `subscription_id`, et le `csrf_token` (même
  pattern que `src/pages/compte/admin.py:_csrf`).
- Bannière succès/erreur lue depuis les query params (`status_changed=1`,
  `error=invalid_status`), même pattern que `compte/admin.py`
  (`ERROR_MESSAGES`/`SUCCESS_MESSAGES`).

### `/admin/journal`

- Garde d'accès, puis `DataTable` en lecture seule de `list_actions(limit=200)` :
  date, email admin, action, user ciblé (lien vers `/admin/user/<id>` si
  `target_user_id` non nul), détails.

## Route de mutation

`POST /admin/actions/subscription-status`, protégée par le
`before_request` du blueprint (`is_admin()` → sinon `abort(404)`) :

1. Lit `user_id`, `subscription_id`, `status` du formulaire.
2. Valide `status` contre `SUBSCRIPTION_STATUSES` → sinon redirect
   `/admin/user/<user_id>?error=invalid_status`.
3. Vérifie que la subscription `subscription_id` appartient bien à `user_id`
   (relit la ligne via `get_current`/une lecture directe) avant d'écrire —
   empêche de modifier l'abonnement d'un autre user par ID forgé dans le
   formulaire.
4. Capture l'ancien statut, appelle `set_status(subscription_id, status)`.
5. `log_action(current_user.email, "subscription_status_change", user_id, f"{old_status} → {status}")`.
6. Redirect `/admin/user/<user_id>?status_changed=1`.

CSRF : protection déjà globale via `CSRFProtect(app)` (`src/auth/setup.py:53`),
aucun code supplémentaire nécessaire au-delà du champ caché habituel.

## Tests

Nouveau dossier `tests/admin/`, calqué sur les conventions existantes :

- **Unitaires** (`tests/admin/test_guard.py`), sur le modèle de
  `tests/test_compte_shell.py` : `is_admin()` avec `current_user` mocké
  (`patch("src.admin.guard.current_user", ...)`) — anonyme → `False`, connecté
  avec un email différent de `ADMIN_EMAIL` → `False`, email correspondant
  (insensible à la casse) → `True`, `ADMIN_EMAIL` non défini → `False`.
- **Route de mutation** (`tests/admin/test_routes.py`), sur le modèle de
  `tests/auth/conftest.py` (`app`/`client`/`users_db_path` fixtures). Session
  admin simulée par injection directe des clés Flask-Login, comme
  `tests/subscriptions/conftest.py:95` (`logged_in_client`) :
  `sess["_user_id"] = str(uid); sess["_fresh"] = True`, avec
  `monkeypatch.setenv("ADMIN_EMAIL", ...)` et un user créé avec cet email.
  Cas couverts : statut invalide → 302 vers `?error=invalid_status` sans
  écriture ; subscription n'appartenant pas au user → refusée ; succès →
  statut mis à jour + une ligne dans `admin_actions` ; accès sans être admin
  → 404.
- **Pages** (`tests/admin/test_pages.py`, Selenium/`DashComposite`, sur le
  modèle de `tests/test_compte_pages.py`) : anonyme sur `/admin` → 404 (pas de
  redirection vers `/connexion`, cohérent avec la garde d'accès qui ne
  distingue pas anonyme / authentifié non-admin) ; compte non-admin
  authentifié → 404 ; admin → liste visible, navigation vers un détail,
  changement de statut reflété à l'écran et dans `/admin/journal`.

## Hors périmètre

- Reset de mot de passe et suppression de compte depuis l'admin (l'utilisateur
  garde ces actions en self-service via `/compte/admin`).
- Édition de `subscriber_state` (votes_balance, trial_used).
- Plusieurs administrateurs (`ADMIN_EMAIL` unique pour l'instant — passer à
  une liste serait un changement d'une ligne dans `is_admin()` si besoin
  futur).
- Pagination de `/admin/journal` (reste une liste plate limitée à 200 lignes) ;
  et pagination de `/admin` au-delà de la limite fixe de `list_users()`
  (1000 users) — la pagination native ne pagine que les lignes déjà chargées,
  pas la requête SQL ; à revoir si le volume le justifie.
