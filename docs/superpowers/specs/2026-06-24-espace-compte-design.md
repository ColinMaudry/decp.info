# Espace « Mon compte » — restructuration et section Compte

Date : 2026-06-24
Statut : design validé
Issue : #73 (comptes premium — abonnement mensuel à prix libre)

## Contexte

La page `/compte` actuelle (`src/pages/compte.py`) est une page unique étroite
qui affiche l'email, un formulaire de changement de mot de passe (POST vers
`/auth/change-password`) et un bouton de déconnexion. L'authentification passe
par un Blueprint Flask `/auth/*` (`src/auth/routes.py`) avec des formulaires
HTML côté serveur ; les pages sont des `register_page` Dash.

L'objectif est de transformer `/compte` en un **espace à plusieurs sections**
(jusqu'à 6 à terme) avec une navigation latérale, et d'implémenter
intégralement la première section, **Compte** (`/compte/admin`).

### Sections cibles

| Section      | URL                  | Statut   | Accès      |
| ------------ | -------------------- | -------- | ---------- |
| Compte       | `/compte/admin`      | ce lot   | compte     |
| Abonnement   | `/compte/abonnement` | coquille | compte     |
| Mes archives | `/compte/archives`   | futur    | abonnement |
| Mes filtres  | `/compte/filtres`    | futur    | abonnement |
| Mon SIRET    | `/compte/siret`      | futur    | abonnement |

## Niveaux d'accès

Trois niveaux :

1. **Visiteur sans compte** → redirigé vers `/connexion?next=<path>`.
2. **Compte sans abonnement valide** → accès à _Compte_ et _Abonnement_
   uniquement ; toute page gated redirige vers `/compte/abonnement`.
3. **Compte avec abonnement valide** → accès à toutes les sections.

L'abonnement n'est pas encore implémenté : on introduit une abstraction
`current_user_has_subscription() -> bool` qui renvoie `False` pour l'instant.
C'est le seul point à brancher lorsque la facturation arrivera.

## Architecture

### Routage (une page par section)

- Chaque section est un `register_page` distinct sous `/compte/*`, fidèle à la
  convention « une page = un fichier » du projet.
- La page `/compte` actuelle devient une **redirection** vers `/compte/admin`
  (renvoie `dcc.Location(href="/compte/admin")`).
- Ce lot crée `/compte/admin` (section Compte) et la coquille
  `/compte/abonnement` (page enregistrée minimale, contenu de vente à venir).
  Les sections gated (`archives`, `filtres`, `siret`) ne sont **pas** créées
  dans ce lot.

### Coquille partagée

Nouveau module `src/pages/_compte_shell.py` exposant :

- `account_shell(active: str, contenu) -> Component`
  Construit la mise en page commune :

  - **Sidebar verticale** (desktop) listant les sections **accessibles** à
    l'utilisateur courant ; l'entrée `active` est surlignée.
  - **Bouton « ☰ Sections »** + `dbc.Offcanvas` (mobile) reprenant la même
    liste.
  - Insère `contenu` dans la zone principale.
  - Sections gated **masquées** tant que `current_user_has_subscription()` est
    faux (Compte + Abonnement seules visibles). La vente des fonctionnalités se
    fera dans le contenu de la section Abonnement, pas via des entrées
    verrouillées.
  - Construit avec Dash Bootstrap Components (`dbc.Row`/`dbc.Col`,
    `dbc.Nav`/`dbc.NavLink`, `dbc.Offcanvas`).

- `account_guard(require_subscription: bool) -> Component | None`
  Appelé en tête de chaque `layout()` :
  - non authentifié → `dcc.Location(href="/connexion?next=<path>")`
  - authentifié, `require_subscription` et pas d'abonnement →
    `dcc.Location(href="/compte/abonnement")`
  - sinon → `None` (la page se rend normalement).

La définition des sections (libellé, URL, icône, `require_subscription`) est
centralisée dans une structure unique dans `_compte_shell.py`, pour que sidebar,
offcanvas et gardes restent cohérents et que l'ajout d'une section future tienne
en une ligne.

## Section Compte (`/compte/admin`)

Agencement : sections empilées avec séparateurs, dans `account_shell`.

1. **Adresse email** — affiche l'email actuel, champ « nouvelle adresse »,
   bouton « Mettre à jour l'email » → `POST /auth/change-email`.
2. **Mot de passe** — formulaire existant (mot de passe actuel + nouveau +
   confirmation), inchangé → `POST /auth/change-password`.
   Sa cible de redirection passe de `/compte` à `/compte/admin`.
3. **Zone danger** — encadré rouge, bouton « Supprimer mon compte » qui ouvre
   une **modale `dbc.Modal`** de confirmation demandant la re-saisie du mot de
   passe → `POST /auth/delete-account`.

Le bouton **Déconnexion** est conservé (POST `/auth/logout`).

Les messages de succès/erreur sont passés en query string et rendus en
`dbc.Alert`, sur le modèle actuel ; `ERROR_MESSAGES` est étendu.

## Changement d'email avec re-vérification

Le changement d'email **ne prend pas effet immédiatement** : la nouvelle adresse
doit être confirmée par email, par cohérence avec l'inscription. L'ancienne
adresse reste active tant que la nouvelle n'est pas vérifiée (évite qu'une faute
de frappe verrouille le compte).

Flux :

1. `POST /auth/change-email` (`@login_required`) :
   - valide la nouvelle adresse (`validate_email`, normalisée en minuscules) ;
   - vérifie l'unicité (`get_user_by_email` → erreur `email_taken`) ;
   - enregistre l'adresse en attente sur l'utilisateur et envoie un lien de
     vérification à cette nouvelle adresse (réutilise le mécanisme de jetons de
     vérification existant) ;
   - redirige `/compte/admin?email_pending=1`.
2. Clic sur le lien → la nouvelle adresse devient l'email du compte et le
   `pending_email` est effacé, puis redirection vers `/compte/admin?email_changed=1`.

Implications stockage : ajout d'un champ `pending_email` à la table `users`
(migration de schéma) et nouvelle fonction DB `update_email(user_id, email)`.
Le détail exact du jeton (réutilisation de `create_email_verification_token` vs
table dédiée) est laissé au plan d'implémentation.

## Suppression de compte

`POST /auth/delete-account` (`@login_required`) :

- vérifie le mot de passe courant (`check_password_hash`) → sinon
  `?error=invalid_current_password` ;
- purge les jetons (`delete_email_verification_tokens_for_user`,
  `delete_password_reset_tokens_for_user`) puis `delete_user(current_user.id)` ;
- `logout_user()` ;
- redirige vers `/?account_deleted=1`.

## Tests

- **Accès (Selenium)** : les trois niveaux, avec le stub d'abonnement forcé à
  `True`/`False` ; redirection des non-authentifiés ; redirection des non-abonnés
  sur une page gated ; présence/masquage des entrées de sidebar.
- **Navigation (Selenium)** : `/compte` → `/compte/admin` ; surlignage de la
  section active ; ouverture de l'offcanvas mobile.
- **Routes** :
  - `change-email` : succès (passage en attente), email déjà pris, email
    invalide.
  - `delete-account` : mauvais mot de passe (refus), succès (compte supprimé +
    déconnexion).

## Hors périmètre

- Contenu réel de la section Abonnement (perks, tarifs, paiement).
- Sections Archives, Filtres, Mon SIRET.
- Implémentation réelle de la facturation derrière
  `current_user_has_subscription()`.
