# Panneau admin — éditeur générique de tables (`/admin`)

Date : 2026-07-03
Statut : design validé
Remplace : [2026-07-03-admin-ui-design.md](2026-07-03-admin-ui-design.md) (pages dédiées liste/détail/journal + formulaire de
changement de statut) — abandonné avant merge sur `main` au profit de ce design.

## Contexte

Le design précédent (pages `/admin`, `/admin/user/<id>`, `/admin/journal` + un
formulaire dédié pour changer un statut d'abonnement) a été entièrement
implémenté et revu (9 tâches, revue finale "ready to merge"), mais **jamais
mergé sur `main`**. Avant la fusion, il est apparu qu'ajouter une page dédiée
à chaque nouveau besoin de support serait trop lent à faire évoluer. `dash_table.DataTable`
supporte l'édition de cellule (`editable=True`), ce qui permet une approche
plus générique : une seule page `/admin` avec un menu déroulant pour choisir
la table SQLite à afficher, filtrer nativement, et éditer directement les
cellules.

## Portée

Trois tables du schéma `users.sqlite` sont éditables : `users` (hors
`password_hash`, totalement exclue), `subscriptions`, `subscriber_state`.
Une quatrième table, `admin_actions` (journal d'audit), est consultable dans
le même sélecteur mais **en lecture seule**. Toute autre table du schéma
(`email_verification_tokens`, `password_reset_tokens`, `oauth_identities`,
`saved_views`, `feature_votes`) est hors périmètre — pas dans le sélecteur.

## Architecture

### Fichiers

- **`src/pages/admin/liste.py`** (réécrit) : page unique `/admin` — menu
  déroulant de sélection de table + `dash_table.DataTable` unique, editable,
  `filter_action="native"`, `sort_action="native"`, `page_action="native"`,
  `page_size=20`.
- **Supprimés** : `src/pages/admin/detail.py`, `src/pages/admin/journal.py`,
  `src/admin/routes.py` (le blueprint Flask du formulaire de changement de
  statut — plus de formulaire, l'édition passe par un callback Dash).
- **`src/pages/admin/_shell.py`** simplifié : `admin_nav()` supprimé (une
  seule page, plus de navigation entre sous-pages) ; `not_admin()` conservé
  à l'identique.
- **`src/admin/guard.py`** (`is_admin()`) : inchangé, réutilisé tel quel.
- **`src/admin/db.py`** (`log_action`, `list_actions`) : inchangé, réutilisé
  pour l'audit des éditions de cellule.
- **Nouveau `src/admin/tables.py`** : registre des tables autorisées et
  fonction générique d'écriture.

### Registre des tables (`src/admin/tables.py`)

```python
@dataclass
class TableConfig:
    label: str
    columns: list[str]          # colonnes affichées, dans l'ordre
    editable_columns: set[str]  # sous-ensemble de columns
    pk: str
    column_types: dict[str, type]      # int | float | str, pour les colonnes éditables
    dropdowns: dict[str, list[str]]    # colonne -> valeurs autorisées (optionnel)
    target_user_id: Callable[[dict], int | None]  # dérive le user_id à loguer depuis une ligne
```

| Table              | Colonnes affichées                                                                                                                   | Éditables                                         | Contraintes                                                                     |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------- | ------------------------------------------------------------------------------- |
| `users`            | id, email, email_verified, siret, pending_email, created_at, updated_at (`password_hash` exclue)                                     | email, email_verified, siret, pending_email       | `email_verified` : dropdown 0/1                                                 |
| `subscriptions`    | id, user_id, frisbii_customer_handle, frisbii_subscription_handle, plan, prix_ht, status, current_period_end, created_at, updated_at | plan, prix_ht, status, current_period_end         | `status` : dropdown `SUBSCRIPTION_STATUSES` ; `plan` : dropdown clés de `PLANS` |
| `subscriber_state` | user_id, trial_used, votes_balance, votes_last_credited_at, updated_at                                                               | trial_used, votes_balance, votes_last_credited_at | `trial_used` : dropdown 0/1                                                     |
| `admin_actions`    | id, admin_email, action, target_user_id, details, created_at                                                                         | _(aucune)_                                        | —                                                                               |

Règles fixes, non contournables par la config : la clé primaire et les
colonnes `created_at`/`updated_at` ne sont jamais dans `editable_columns`.
Les handles Frisbii (`frisbii_customer_handle`, `frisbii_subscription_handle`)
et `user_id` (FK) sont explicitement exclus de l'édition — modifier un
handle désynchroniserait silencieusement l'état réel côté Frisbii sans rien
signaler ; modifier `user_id` casserait le rattachement à l'utilisateur.

`target_user_id` par table : `users` → `row["id"]`, `subscriptions` →
`row["user_id"]`, `subscriber_state` → `row["user_id"]` (sa propre PK),
`admin_actions` → non applicable (table en lecture seule, jamais loguée).

## Flux d'édition

1. **Callback de sélection de table** — `Input("admin-table-select", "value")` → `Output("admin-table", "data"/"columns"/"dropdown_conditional")`.
   Charge `SELECT * FROM <table>` où `<table>` est validé contre les clés de
   `TABLES` avant toute requête — jamais interpolé tel quel depuis l'UI, donc
   aucune table hors liste blanche n'est accessible même via un payload de
   callback forgé.
2. **Callback d'édition** — `Input("admin-table", "data")`,
   `State("admin-table", "data_previous")`,
   `State("admin-table-select", "value")`. Diff ligne par ligne pour
   localiser la cellule modifiée.
   - **Revalidation côté serveur** : le callback ignore tout changement sur
     une colonne absente de `editable_columns`, même si elle est présente
     dans le payload — le flag `editable` de la DataTable est une aide
     visuelle côté client, pas une garantie de sécurité. Seul un admin
     authentifié (`is_admin()` déjà en tête de page) peut atteindre ce code.
   - **Coercition de type avant écriture** : SQLite étant faiblement typé,
     écrire sans validation permettrait à du texte non convertible de finir
     silencieusement dans une colonne `REAL`/`INTEGER`. Chaque colonne
     éditable a un type attendu (`column_types`) ; une valeur qui ne
     convertit pas proprement est rejetée : la cellule revient à son
     ancienne valeur, une alerte s'affiche, rien n'est écrit.
   - Pour les colonnes à `dropdowns`, la valeur est aussi vérifiée contre la
     liste autorisée avant écriture (défense en profondeur, en plus du
     rendu en dropdown côté UI).
   - Écriture via `set_cell(table: str, pk_value, column: str, value) -> None`
     dans `src/admin/tables.py` — `UPDATE <table> SET <column> = ? WHERE <pk> = ?`.
   - Audit : `log_action(current_user.email, f"edit_{table}", target_user_id, f"{column}: {old} → {new}")`.

## Gestion des erreurs

- Table hors liste blanche (requête forgée) : aucune donnée renvoyée, pas de
  crash.
- Coercition de type échouée : cellule restaurée à l'ancienne valeur +
  `dbc.Alert` d'erreur, rien n'est écrit en base.
- `UPDATE` touchant 0 ligne (ligne supprimée entre-temps) : alerte d'erreur,
  pas d'exception non gérée.

## Tests

- **`tests/admin/test_tables.py`** (nouveau, remplace `tests/admin/test_routes.py`) :
  table hors liste blanche rejetée, colonne non éditable rejetée même
  présente dans le payload, coercition de type (succès et échec) par type de
  colonne, écriture réussie relue en base, `admin_actions` loguée avec le
  bon `target_user_id` par table.
- Les callbacks Dash (sélection de table, édition de cellule) sont de
  simples fonctions Python décorées — testables en les import-appelant
  directement avec des données factices, sans dispatch Dash ni serveur
  Flask.
- **`tests/admin/test_guard.py`** : inchangé (guard non affecté par ce
  pivot).
- **`tests/admin/test_pages.py`** : les tests anonyme/non-admin → 404 sont
  conservés à l'identique (page toujours gardée par `is_admin()`). Le test
  de flux complet est réécrit : login admin réel → `/admin` → sélection de
  "subscriptions" dans le menu déroulant → édition de la cellule `status`
  d'une ligne → vérification de la nouvelle valeur affichée et d'une ligne
  dans `admin_actions` (consultable via le même sélecteur). Même contrainte
  de nettoyage explicite de `tests/users.test.sqlite` (fichier committé,
  partagé pour toute la session de tests) qu'auparavant.
- Supprimés : `tests/admin/test_routes.py` et toute couverture spécifique à
  `detail.py`/`journal.py`.

## Hors périmètre

- Toute table hors de la liste blanche (`email_verification_tokens`,
  `password_reset_tokens`, `oauth_identities`, `saved_views`,
  `feature_votes`) — pas dans le sélecteur, pas éditable.
- `password_hash` : totalement exclue de l'affichage de `users` (ni lecture
  ni édition).
- Ajout/suppression de lignes depuis l'éditeur — édition de cellule
  seulement, pas de création/suppression.
- Plusieurs administrateurs (`ADMIN_EMAIL` unique, inchangé du design
  précédent).
- Pagination de `admin_actions` au-delà de `list_actions(limit=200)`
  (inchangé du design précédent).
