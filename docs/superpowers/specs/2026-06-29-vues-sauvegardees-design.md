# Sauvegarde des vues du Tableau

**Date :** 2026-06-29
**Statut :** Design validé
**Issue :** [#95](https://github.com/ColinMaudry/decp.info/issues/95)

## Contexte

La page `/tableau` permet déjà de filtrer, trier et choisir les colonnes des
marchés. Ces réglages sont **matérialisés dans l'URL** via trois paramètres
(`filtres`, `tris`, `colonnes`) : `sync_url_and_reset_button` les produit (bouton
« Partager la vue ») et `restore_view_from_url` les restaure à l'ouverture d'une
URL ainsi formée.

L'issue #95 demande d'aller plus loin : permettre aux utilisateur·ices de
**sauvegarder des vues nommées** et de les ré-appliquer en un clic, sans avoir à
manipuler ou conserver des URL.

L'issue mentionnait les trois tableaux (`/tableau`, `/titulaire`, `/acheteur`).
**Le périmètre a été resserré à `/tableau` uniquement.** C'est le seul des trois
qui gère aujourd'hui les paramètres d'URL et le partage ; `/titulaire` et
`/acheteur` ne les supportent pas encore et sont hors périmètre.

## Objectif

Pour un·e **abonné·e** sur `/tableau` :

1. **Sauvegarder** la vue courante (filtres + tris + colonnes) sous un nom
   personnalisé, saisi dans une modale.
2. **Appliquer** une vue sauvegardée en la choisissant dans un menu déroulant.

Pour un·e **abonné·e** dans l'espace compte :

3. **Gérer** ses vues sur une nouvelle page `/compte/vues` : lister, renommer,
   supprimer.

Les non-abonné·es ne voient aucun de ces contrôles, et toute opération
d'écriture est refusée côté serveur.

## Principe

Une **vue** = un nom + la query string que `/tableau` sait déjà produire et
restaurer (`filtres` + `tris` + `colonnes`). On ne réinvente rien :

- **Sauvegarder** = construire la query string comme le fait déjà
  `sync_url_and_reset_button`, puis la stocker avec un nom.
- **Appliquer** = naviguer vers `/tableau?<query>` ; `restore_view_from_url`
  existant fait le reste.

## Architecture existante (rappel)

- `src/pages/tableau.py` :
  - `sync_url_and_reset_button` — construit la query string à partir de
    `filter_query`, `sort_by`, `hidden_columns` (via `invert_columns`).
  - `restore_view_from_url` — réagit à `tableau_url.search`, applique
    `filtres`/`tris`/`colonnes` au DataTable.
  - `dcc.Location(id="tableau_url", refresh=False)` — la navigation interne ne
    recharge pas la page.
- `src/pages/_compte_shell.py` :
  - `current_user_has_subscription()` — **point unique** de contrôle d'accès,
    respecte le drapeau `TOUS_ABONNES`.
  - `SECTIONS` — liste centralisée des sections de l'espace compte (chaque entrée
    peut exiger `require_subscription: True`).
  - `account_guard(path, require_subscription)` — protège une page compte
    (redirige vers `/connexion` ou `/compte/abonnement`).
  - `account_shell(active, contenu)` — gabarit (barre latérale + contenu).
- `src/subscriptions/db.py` — modèle de référence pour un module DB sur
  `users.sqlite` : constante `SCHEMA`, `init_schema()`, fonctions CRUD via
  `src.auth.db.get_conn()`.
- `src/subscriptions/setup.py::init_subscriptions` appelle `db.init_schema()` au
  démarrage ; câblé dans `src/app.py` (`init_subscriptions(app.server)`).
- L'identité de l'utilisateur·ice connecté·e est disponible dans les callbacks
  via `flask_login.current_user` (les callbacks Dash s'exécutent dans le
  contexte de requête Flask).

## Conception

### 1. Stockage — table `saved_views` dans `users.sqlite`

Nouveau module `src/saved_views/db.py`, calqué sur `src/subscriptions/db.py`.

```sql
CREATE TABLE IF NOT EXISTS saved_views (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    table_name  TEXT NOT NULL DEFAULT 'tableau',
    name        TEXT NOT NULL,
    query       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (user_id, table_name, name)
);
CREATE INDEX IF NOT EXISTS idx_saved_views_user
    ON saved_views(user_id, table_name);
```

- `table_name` vaut toujours `'tableau'` pour l'instant. La colonne réserve la
  place pour `/titulaire` et `/acheteur` plus tard, sans surcoût ni UI
  aujourd'hui.
- `query` est la query string telle qu'elle apparaît dans l'URL (par ex.
  `filtres=...&tris=...&colonnes=...`), produite et consommée exactement comme le
  fait le partage existant. Appliquer = naviguer vers `/tableau?<query>`.
- `UNIQUE (user_id, table_name, name)` empêche les doublons de nom pour un·e même
  utilisateur·ice.

Fonctions du module (toutes via `src.auth.db.get_conn()`) :

| Fonction                                   | Rôle                                                                                                                                                                            |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `init_schema()`                            | `executescript(SCHEMA)` — idempotent (`IF NOT EXISTS`).                                                                                                                         |
| `list_views(user_id, table_name)`          | Vues de l'utilisateur·ice pour ce tableau, triées par `name`.                                                                                                                   |
| `upsert(user_id, table_name, name, query)` | Insert, ou `ON CONFLICT(user_id, table_name, name) DO UPDATE` → **écrase** `query` et `updated_at`. Enregistrer sous un nom existant **met donc la vue à jour** (pas d'erreur). |
| `rename(view_id, user_id, new_name)`       | Renomme ; `user_id` dans le `WHERE` garantit la propriété.                                                                                                                      |
| `delete(view_id, user_id)`                 | Supprime ; `user_id` dans le `WHERE` garantit la propriété.                                                                                                                     |
| `get(view_id, user_id)`                    | Une vue, contrôle de propriété.                                                                                                                                                 |

`init_schema()` est appelé au démarrage dans `src/app.py`, à côté de
`init_subscriptions(app.server)` :

```python
from src.saved_views import db as saved_views_db
saved_views_db.init_schema()
```

### 2. UI sur `/tableau` (abonné·es uniquement)

Ajout d'un conteneur `saved-views-bar` dans la `table-menu` existante de
`tableau.py`, **masqué par défaut** (`style={"display": "none"}`). Il contient
trois éléments :

1. **Bouton « Sauvegarder la vue »** — ouvre la modale de nommage.
2. **Modale de sauvegarde** — un champ texte (nom) + bouton « Enregistrer ».
3. **Menu déroulant « Mes vues »** (`dbc.DropdownMenu`) — la liste des vues.

#### Affichage conditionnel (gating)

Un callback rend la barre visible **uniquement pour les abonné·es** :

- Déclencheur : chargement de la page (Input sur `tableau_url.pathname` ou
  `href`).
- Logique : `style = {}` si `current_user_has_subscription()`, sinon
  `{"display": "none"}`.

Les composants restent présents dans le DOM (cachés), donc leurs callbacks sont
toujours valides — pas besoin de `suppress_callback_exceptions`. Le masquage
côté client ne suffit pas à lui seul : **toute écriture est re-contrôlée côté
serveur** (voir ci-dessous).

#### Sauvegarder

Callback de la modale (clic sur « Enregistrer ») :

- States : `filter_query`, `sort_by`, `hidden_columns` du DataTable + valeur du
  champ nom.
- **Re-vérifie `current_user_has_subscription()`** ; si faux, ne fait rien
  (no-update).
- Construit la query string de la même manière que
  `sync_url_and_reset_button` (réutiliser/extraire la logique commune dans une
  petite fonction utilitaire pour éviter la duplication).
- Appelle `saved_views.db.upsert(current_user.id, "tableau", name, query)`.
- Ferme la modale et rafraîchit le menu déroulant ; affiche une confirmation
  (« Vue « <nom> » enregistrée. »).
- Nom vide → message d'erreur inline dans la modale, pas d'enregistrement.

#### Appliquer

Callback qui remplit le menu déroulant :

- Déclencheurs : chargement de la page **et** signal de rafraîchissement émis
  après une sauvegarde.
- Récupère `list_views(current_user.id, "tableau")`.
- Rend un `dbc.DropdownMenuItem` par vue, **sous forme de lien** :
  `href=f"/tableau?{view['query']}"`.
- Si la liste est vide, le menu n'est pas affiché (ou est désactivé avec un
  libellé « Aucune vue enregistrée »).

Cliquer sur un item navigue vers `/tableau?<query>` (sans rechargement, grâce à
`dcc.Location(refresh=False)`), ce qui déclenche `restore_view_from_url`
existant. **Aucune nouvelle logique d'application n'est nécessaire.**

### 3. Page de gestion `/compte/vues`

#### Section dans `_compte_shell.py`

Ajouter une entrée à `SECTIONS` :

```python
{
    "key": "vues",
    "label": "Mes vues",
    "href": "/compte/vues",
    "require_subscription": True,
},
```

Cela rend automatiquement le lien visible dans la navigation de l'espace compte
pour les abonné·es (via `visible_sections`) et active la protection d'accès.

#### Page `src/pages/compte_vues.py`

Même structure que `src/pages/compte_admin.py` :

```python
def layout(**_):
    guard = account_guard("/compte/vues", require_subscription=True)
    if guard is not None:
        return guard
    contenu = _vues_section()
    return account_shell("vues", contenu)
```

Contenu (`_vues_section`) :

- Titre « Mes vues » + courte explication.
- **Liste** des vues (`list_views(current_user.id, "tableau")`) : pour chaque
  vue, son nom, sa date de création, un lien **« Ouvrir »** vers
  `/tableau?<query>`, un bouton **« Renommer »** et un bouton **« Supprimer »**.
- **État vide** : message invitant à créer une vue depuis `/tableau`.

Actions, via callbacks pattern-matching (ids du type
`{"type": "vue-delete", "index": view_id}`), **contrôle de propriété par
`user_id`** dans chaque appel DB :

- **Supprimer** → `delete(view_id, current_user.id)`, puis rafraîchit la liste.
- **Renommer** → champ de saisie (inline ou petite modale) →
  `rename(view_id, current_user.id, new_name)`, puis rafraîchit la liste.

### 4. Sécurité

- Le masquage des contrôles sur `/tableau` est **cosmétique** ; la garantie
  réelle est le contrôle serveur dans chaque callback d'écriture
  (`current_user_has_subscription()`) et la présence de `user_id` dans tous les
  `WHERE` des opérations DB (lecture comme écriture).
- `/compte/vues` est protégée par `account_guard(..., require_subscription=True)`
  comme les autres sections réservées.

## Hors périmètre

- `/titulaire` et `/acheteur` : ces pages ne gèrent pas encore les paramètres
  d'URL ni le partage. La colonne `table_name` réserve la place pour les y
  étendre plus tard, sans UI ni callback dédiés aujourd'hui.
- Aucune modification du partage d'URL existant (« Partager la vue ») ni de la
  persistance localStorage de la DataTable.
- Pas de partage d'une vue sauvegardée entre comptes, ni de vues publiques.
- La taille de page et la page courante ne font pas partie d'une vue (cohérent
  avec le partage existant).

## Tests

`uv run pytest`

### Tests unitaires DB (`src/saved_views/db.py`)

- `upsert` crée une vue ; `list_views` la retourne.
- `upsert` avec un `(user_id, table_name, name)` existant **écrase** `query` et
  met à jour `updated_at` (pas de doublon, pas d'erreur).
- `rename` / `delete` n'affectent que les vues du bon `user_id` (isolation entre
  comptes).
- La suppression d'un·e utilisateur·ice supprime ses vues en cascade
  (`ON DELETE CASCADE`).

### Tests de gating

- Le callback d'affichage de `saved-views-bar` renvoie un style masqué pour un·e
  non-abonné·e et visible pour un·e abonné·e (en s'appuyant sur
  `current_user_has_subscription()`).
- Le callback de sauvegarde refuse l'écriture (no-update) sans abonnement.
- `/compte/vues` redirige un·e non-abonné·e (comportement `account_guard`, déjà
  couvert par le motif existant).

```

```
