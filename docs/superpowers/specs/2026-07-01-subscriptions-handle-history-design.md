# Handle d'abonnement personnalisé + historique des abonnements — design

- **Contexte** : suite de [2026-06-25-frisbii-abonnements-design.md](2026-06-25-frisbii-abonnements-design.md)
- **Date** : 2026-07-01

## Objectif

Remplacer le paramètre `generate_handle: true` (Frisbii génère le handle de
l'abonnement) par un handle choisi par colibre, préfixé `abo`, unique. Générer
ce handle nécessite de pouvoir consulter l'historique des abonnements d'un
utilisateur — ce qui n'est pas possible avec le schéma actuel de
`subscriptions`, qui n'a qu'une ligne par utilisateur (`user_id PRIMARY KEY`),
écrasée à chaque nouvelle souscription. Ce design scinde donc `subscriptions`
en un historique multi-lignes et introduit une table séparée pour l'état
cumulatif de l'utilisateur (votes, essai), en plus du changement de handle.

## Décisions clés

1. **Format du handle : `abo-{user_id}-{N}`**, `N` incrémental par
   utilisateur (ex. `abo-42-1`, puis `abo-42-2` en cas de résiliation puis
   réabonnement). Calculé en scannant les handles déjà utilisés par cet
   utilisateur dans `subscriptions` (`LIKE 'abo-{user_id}-%'`) et en prenant
   le suffixe max + 1.
2. **`subscriptions` devient un historique multi-lignes** (une ligne par
   tentative d'abonnement Frisbii), `id` auto-incrémenté comme clé primaire,
   `user_id` non-unique.
3. **Nouvelle table `subscriber_state`** (1 ligne par utilisateur) pour l'état
   cumulatif indépendant du cycle de vie d'un abonnement particulier
   (`trial_used`, `votes_balance`, `votes_last_credited_at`) — ces colonnes
   n'ont pas de sens sur une ligne d'historique précise. Alternative écartée :
   les ajouter à `users` (mélangerait identité et logique d'abonnement/billing
   dans `auth/db.py`, qui doit rester focalisé sur l'identité).
4. **Le handle est écrit par colibre à la création, pas par le webhook.**
   Contrairement au comportement actuel (Frisbii génère le handle, on
   l'apprend via le webhook), colibre choisit `abo-{user_id}-{N}` et
   l'enregistre dans `subscriptions.frisbii_subscription_handle` **avant**
   d'appeler l'API Frisbii. Le webhook ne fait plus que lire/matcher sur ce
   handle (`get_by_handle`), jamais l'écrire.
   - Ordre retenu : écrire chez nous d'abord, appeler Frisbii ensuite. En cas
     d'échec de l'appel Frisbii, on se retrouve avec une ligne locale
     `pending`→`failed` dont le handle n'a jamais existé côté Frisbii — c'est
     inoffensif (voir décision 5). L'ordre inverse (Frisbii d'abord) est plus
     risqué : un succès Frisbii suivi d'un échec d'écriture locale laisserait
     un abonnement réel et potentiellement payant chez Frisbii sans aucune
     trace côté colibre, avec un risque de collision de handle au prochain
     essai.
5. **Statut `failed`** pour distinguer un échec propre côté Frisbii (juste
   après `create_pending`) d'un abonnement réellement `pending` chez Frisbii
   (session créée, paiement pas encore confirmé). Sans ce statut, l'écran
   `/compte/abonnement` affiche `_active_view` dès qu'une ligne existe pour
   l'utilisateur (peu importe le statut), ce qui bloquerait indéfiniment le
   bouton « S'abonner » derrière un écran « Ajouter une méthode de paiement »
   pour un abonnement fantôme, et « Me désabonner » échouerait aussi (handle
   inconnu de Frisbii). La ligne `failed` reste en base (pas de suppression)
   pour que `abo-{user_id}-{N}` ne réutilise jamais ce suffixe — protection
   utile en cas d'échec réseau ambigu (timeout ne garantit pas que la requête
   n'a pas été traitée côté Frisbii).
6. **Chaque tentative de souscription crée une nouvelle ligne** (pas de
   réutilisation d'une ligne `pending` existante). Chaque clic sur
   « S'abonner » qui atteint `create_subscription_session` crée un véritable
   nouvel objet abonnement chez Frisbii ; réutiliser une ligne locale
   reviendrait à réutiliser un handle déjà proposé à Frisbii pour un objet
   différent.

## Schéma

```sql
CREATE TABLE subscriptions (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                      INTEGER NOT NULL,
    frisbii_customer_handle      TEXT,
    frisbii_subscription_handle  TEXT,
    plan                         TEXT,
    prix_ht                      REAL,
    status                       TEXT,   -- 'pending' | 'trial' | 'active' | 'cancelled' | 'expired' | 'failed'
    current_period_end           TEXT,
    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);
CREATE UNIQUE INDEX idx_subscriptions_handle ON subscriptions(frisbii_subscription_handle);

CREATE TABLE subscriber_state (
    user_id                 INTEGER PRIMARY KEY,
    trial_used              INTEGER NOT NULL DEFAULT 0,
    votes_balance           INTEGER NOT NULL DEFAULT 0,
    votes_last_credited_at  TEXT,
    updated_at              TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### Migration

`ALTER TABLE` ne permet ni de retirer `user_id` comme clé primaire ni de
répartir des colonnes vers une nouvelle table. Migration par reconstruction de
table, sur le modèle de `_rebuild_users_password_nullable` dans
`src/auth/db.py:86` : fonction Python dédiée (pas une entrée de la liste
générique `_MIGRATIONS`, qui n'exécute qu'une instruction SQL simple), guard
d'idempotence sur `PRAGMA table_info(subscriptions)` (absence de la colonne
`id`), transaction unique :

1. `CREATE TABLE subscriptions_new` (nouveau schéma).
2. `INSERT INTO subscriptions_new (...) SELECT user_id, frisbii_customer_handle, ... FROM subscriptions` (les anciennes lignes deviennent l'historique, un `id` frais leur est attribué).
3. `INSERT INTO subscriber_state (user_id, trial_used, votes_balance, votes_last_credited_at, updated_at) SELECT ... FROM subscriptions` (depuis l'ancienne table, avant le `DROP`).
4. `DROP TABLE subscriptions`, `ALTER TABLE subscriptions_new RENAME TO subscriptions`, recréation des index.

Appelée depuis `subscriptions/db.py:init_schema()`, `PRAGMA foreign_keys = OFF`
pendant le `DROP`/`RENAME` (cascade), comme dans le précédent auth.

## API `subscriptions/db.py`

- `get_by_user` → **`get_current(user_id) -> Row | None`** : dernière ligne
  (`ORDER BY id DESC LIMIT 1`). Remplace tous les usages actuels de
  « l'abonnement de l'utilisateur ».
- `get_by_customer` → **`customer_known(customer_handle) -> bool`** : test
  d'existence seul (un `frisbii_customer_handle` peut apparaître sur
  plusieurs lignes d'historique).
- **`get_by_handle(subscription_handle) -> Row | None`** (nouveau) : résout la
  ligne exacte à mettre à jour depuis un webhook.
- **`_next_handle(user_id) -> str`** (nouveau, privé) :
  ```python
  def _next_handle(user_id: int) -> str:
      prefix = f"abo-{user_id}-"
      rows = get_conn().execute(
          "SELECT frisbii_subscription_handle FROM subscriptions "
          "WHERE user_id = ? AND frisbii_subscription_handle LIKE ?",
          (user_id, f"{prefix}%"),
      ).fetchall()
      n = max(
          (int(r[0][len(prefix):]) for r in rows if r[0][len(prefix):].isdigit()),
          default=0,
      )
      return f"{prefix}{n + 1}"
  ```
- **`create_pending(user_id, customer_handle, plan, prix_ht=None) -> tuple[str, int]`** :
  génère le handle via `_next_handle`, **INSERT** une nouvelle ligne
  (`status='pending'`, `frisbii_subscription_handle` déjà renseigné), renvoie
  `(handle, subscription_id)`.
- **`mark_failed(subscription_id) -> None`** (nouveau) :
  `UPDATE subscriptions SET status='failed', updated_at=? WHERE id=?`. Pas de
  logique de crédit de votes (rien n'a jamais été actif), contrairement à
  `set_cancelled`.
- **`update_from_webhook(subscription_handle, status, current_period_end)`** :
  signature simplifiée (retrait de `customer_handle`), cible la ligne via
  `get_by_handle`. `trial_used` déplacé vers `subscriber_state`.
- **`set_cancelled(subscription_id, current_period_end)`** : opère par `id`
  de ligne (plus par `user_id`) — `routes.cancel()` récupère déjà la ligne via
  `get_current`, lui passe `row["id"]`.
- `has_active_subscription`, `has_used_trial`, `credit_pending`, `spend_vote`,
  `next_recharge_at`, `freeze_votes_cursor` : signatures inchangées, mais
  relus/écrits sur `subscriber_state` pour le solde/l'essai. `credit_pending`
  reste la seule fonction à toucher aux deux tables (lit le statut courant sur
  `subscriptions` via `get_current`, écrit le solde sur `subscriber_state`).
  `has_used_trial`/les fonctions de vote tolèrent l'absence de ligne
  `subscriber_state` (première interaction de l'utilisateur : valeurs par
  défaut, pas d'erreur).

## `client.py`

`create_subscription_session` reçoit un paramètre `handle: str` obligatoire ;
remplace `"generate_handle": True` par `"handle": handle` dans le corps de la
requête `POST /v1/subscription`.

## `routes.py`

- `subscribe()` : appelle `db.create_pending(...)` → `(handle, subscription_id)`,
  passe `handle` à `client.create_subscription_session(..., handle=handle)`.
  Dans le `except client.FrisbiiError`, appelle `db.mark_failed(subscription_id)`
  avant de rediriger vers `?error=frisbii`.
- `cancel()` : récupère la ligne via `get_current`, passe `row["id"]` à
  `set_cancelled`.
- `webhook()` : garde existant basé sur `customer_known(customer)` ; appelle
  `update_from_webhook(sub_handle, status, current_period_end)` (sans
  `customer_handle`).

## `compte_abonnement.py`

`layout()` : `if row is not None:` → `if row is not None and row["status"] != "failed":`
pour qu'une ligne `failed` ne bloque plus l'affichage de `_plan_cards` (retour
au formulaire de souscription).

## Sites d'appel à migrer

`get_by_user`/`get_by_customer` sont utilisés dans :
`src/pages/compte_roadmap.py`, `src/pages/_compte_shell.py`,
`src/pages/compte_abonnement.py`, `src/auth/routes.py` — renommage mécanique
vers `get_current`. `tests/subscriptions/test_db.py` et `test_routes.py`
nécessitent une réécriture significative (nouvelles signatures, statut
`failed`, table `subscriber_state`).

## Hors périmètre (YAGNI)

- **Nettoyage automatique des lignes `pending`/`failed` orphelines** (essais
  de souscription abandonnés ou échoués). Inoffensif : ne bloque pas la
  réinscription, ne crée pas de collision de handle. Pas de cron de
  réconciliation pour l'instant — cohérent avec la décision « pas de
  réconciliation périodique automatique » du design initial.
- **Scoping des colonnes des `SELECT *`** dans `subscriptions/db.py` /
  `auth/db.py` (évoqué en discussion, explicitement écarté de cette tâche).
- **Vérifier une vraie méthode de paiement (Frisbii) avant d'afficher le
  bandeau « Ajouter une méthode de paiement »** dans `_active_view` pour
  `status == "pending"`. Aujourd'hui le bandeau s'affiche pour tout `pending`,
  y compris juste après un ajout de méthode de paiement via
  `/subscriptions/add-payment` si le webhook n'a pas encore fait passer le
  statut à `trial`/`active`. `client.get_customer_payment_methods` existe déjà
  pour ça. Orthogonal à ce design (ne dépend d'aucune décision ci-dessus) —
  traité comme tâche de suivi séparée, avec son propre petit design (gestion
  d'erreur API, message si paiement déjà présent mais webhook en retard).
