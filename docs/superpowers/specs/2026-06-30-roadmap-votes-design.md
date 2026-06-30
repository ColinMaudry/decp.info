# Vote pour les prochaines fonctionnalités (Roadmap) — Design

Issue : [#94](https://github.com/ColinMaudry/decp.info/issues/94)
Date : 2026-06-30

## Objectif

Permettre aux abonnés de voter pour les prochaines fonctionnalités depuis une
section Roadmap réservée aux abonnés (`/compte/roadmap`). La même roadmap est
exposée en lecture seule au public (`/a-propos/roadmap`). Les fonctionnalités
sont gérées dans GitHub via des labels ; le changelog du dépôt est affiché en
bas des deux pages.

## Modèle d'attribution des votes

- Un nouvel abonné reçoit **2 votes** au moment où sa **période d'essai se
  termine** (passage du statut `trial`/pending à `active`).
- Il gagne ensuite **+1 vote par semaine** tant que son abonnement est **actif**.
- Les votes ne s'accumulent **pas** pendant une période sans abonnement (gel).
- Au **réabonnement**, l'accumulation reprend mais **les 2 votes initiaux ne
  sont pas re-crédités**.
- Un abonné peut voter **plusieurs fois** pour la même fonctionnalité.
- Un vote dépensé est **définitif** : pas de retrait possible.

### Accumulation paresseuse (pas de cronjob)

État stocké sur la table `subscriptions` (2 colonnes ajoutées par migration) :

| Colonne                | Type                         | Rôle                                                 |
| ---------------------- | ---------------------------- | ---------------------------------------------------- |
| `votes_balance`        | `INTEGER NOT NULL DEFAULT 0` | Solde de votes dépensable                            |
| `votes_credited_until` | `TEXT` (NULL par défaut)     | Curseur d'accumulation ; NULL tant que jamais activé |

Fonction `credit_pending(user_id)`, appelée **au chargement de
`/compte/roadmap` et avant chaque vote** :

1. Charger la ligne d'abonnement de l'utilisateur. Si absente → ne rien faire.
2. Si `votes_credited_until` est NULL **et** statut `active` (= fin d'essai
   atteinte) → créditer les **+2 initiaux**, `votes_credited_until = maintenant`.
3. Si `votes_credited_until` posé **et** statut `active` →
   `semaines = floor((maintenant − votes_credited_until) / 7 jours)` ;
   si `semaines > 0` : `votes_balance += semaines` et avancer
   `votes_credited_until` de `semaines × 7 jours`.
4. Statut non-`active` → aucun crédit (gel).

Cette fonction est **idempotente** : recharger la page le même jour ne crédite
rien de plus, car le curseur n'avance que par semaines pleines.

### Gel au désabonnement / réabonnement

Dans `update_from_webhook` (`src/subscriptions/db.py`) :

- **Résiliation** (`active` → `cancelled`) : appeler `credit_pending` pour
  banquer les semaines acquises ; le statut `cancelled` bloque ensuite tout
  crédit (le curseur reste figé).
- **Réabonnement** (`cancelled` → `active`) : remettre
  `votes_credited_until = maintenant` pour ne pas créditer la période sans
  abonnement, **sans re-créditer les +2** (curseur non-NULL).

## Registre des votes émis

Nouvelle table dans `users.sqlite` :

```sql
CREATE TABLE feature_votes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    issue_number INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
```

- Une ligne par vote émis (vote multiple = plusieurs lignes).
- Décompte d'une fonctionnalité = `COUNT(*)` groupé par `issue_number`.
- Décomptes **publics** (visibles sur `/a-propos/roadmap`).

Migrations ajoutées dans `src/migrations.py` (`_MIGRATIONS`) :

- ajout de `votes_balance` et `votes_credited_until` sur `subscriptions`
- création de la table `feature_votes`

## Intégration GitHub & cache

Nouveau module `src/utils/roadmap.py` :

- `fetch_roadmap_issues()`, décoré `@cache.memoize(timeout=3600)` (cache 1 h) :
  `httpx.get` sur `GET /repos/ColinMaudry/decp.info/issues?state=open`, puis
  filtrage local par label. Retourne deux listes de dicts
  `{number, title, html_url}` : les `en cours` et les `mis au vote`.
- **Appel anonyme** (pas de `GITHUB_TOKEN`) : suffisant pour un dépôt public
  avec un cache d'1 heure.
- On reste sur `httpx`, déjà dépendance du projet (Dash, `src/utils/data.py`,
  `src/utils/tracking.py`) — pas d'ajout de `requests`.

`src/utils/roadmap.py` centralise aussi :

- la récupération des décomptes (`COUNT` groupé depuis `feature_votes`) ;
- un constructeur de composants `render_roadmap(editable: bool)` partagé par les
  deux pages.

## Pages & navigation

### Page abonné — `src/pages/compte_roadmap.py`

- Route `/compte/roadmap`, `require_subscription=True`, via `account_shell`.
- À l'entrée : `credit_pending(user_id)`.
- Contenu :
  1. Bandeau « Il te reste **N** votes » (solde courant).
  2. Section **« En cours »** (label `en cours`) — titres liés vers GitHub, pas
     de vote.
  3. Section **« Au vote »** (label `mis au vote`) — triée par votes
     décroissants ; chaque fonctionnalité affiche son décompte + un bouton
     « Voter » (désactivé si solde = 0).
  4. **Changelog** (`CHANGELOG.md` rendu via `dcc.Markdown`).

Action de vote : vérifier `votes_balance > 0`, décrémenter `votes_balance`,
insérer une ligne `feature_votes`, rafraîchir l'affichage.

### Page publique — `src/pages/a_propos/roadmap.py`

- Route `/a-propos/roadmap`, via `apropos_shell`.
- Identique mais `render_roadmap(editable=False)` : décomptes publics visibles,
  **aucun bouton**, pas de bandeau de solde.

### Navigation

- Ajout d'une entrée `roadmap` dans `SECTIONS` de `_compte_shell.py`
  (`require_subscription=True`).
- Ajout d'une entrée `roadmap` dans `SECTIONS` de `_apropos_shell.py`.

## Lien version & changelog

- Dans `src/app.py` (~ligne 194), le lien du numéro de version pointe vers
  `/a-propos/roadmap` au lieu de l'URL GitHub du `CHANGELOG.md`.
- Lecture de `CHANGELOG.md` (racine du dépôt) rendue via `dcc.Markdown`,
  partagée par les deux pages.

## Hors périmètre (YAGNI)

- Pas de cronjob / timer pour l'accumulation.
- Pas de retrait de vote.
- Pas de `GITHUB_TOKEN`.
- Pas de gestion d'écriture vers GitHub (les fonctionnalités restent gérées
  manuellement via les labels GitHub).
