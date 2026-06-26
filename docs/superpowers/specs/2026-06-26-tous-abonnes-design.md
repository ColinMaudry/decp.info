# Accès gratuit pour tous via `TOUS_ABONNES`

**Date :** 2026-06-26
**Statut :** Design validé

## Contexte

La plateforme de paiement Frisbii doit effectuer un _background check_ avant
d'autoriser la réception de paiements (plusieurs semaines). En attendant, on
veut ouvrir gratuitement à tout utilisateur connecté les fonctionnalités
normalement réservées aux abonnés, sans casser le code d'abonnement existant
(qui sera réactivé tel quel une fois Frisbii validé).

## Objectif

Un drapeau d'environnement `TOUS_ABONNES` qui, lorsqu'il vaut `true` :

1. donne à tout utilisateur **connecté** l'accès aux fonctionnalités réservées
   aux abonnés ;
2. affiche un bandeau d'information en haut de la page `/compte/abonnement` ;
3. désactive (et grise) les boutons « S'abonner » sur `/compte/abonnement`.

Quand le drapeau est absent ou `false`, le comportement actuel est strictement
inchangé.

## Architecture existante (rappel)

- `src/pages/_compte_shell.py` centralise l'accès :
  - `current_user_has_subscription()` → utilisé par `_nav` (sections visibles
    du menu) **et** `account_guard` (protection des pages réservées) ;
  - `SECTIONS` marque `archives`, `filtres`, `siret` avec
    `require_subscription: True`.
- `db.has_active_subscription(user_id)` est le contrôle bas-niveau « vrai
  abonnement payant » ; appelé directement par :
  - `compte_abonnement.py` (`has_access` → vue « abonnement actif » vs cartes de
    plans) ;
  - `auth/routes.py::_post_login_url` (redirection post-login) ;
  - `subscriptions/routes.py::subscribe` (anti double-abonnement).
- `compte_abonnement.py::_plan_card` rend le bouton « S'abonner ».

## Conception

### 1. Variable d'environnement

Dans `src/utils/__init__.py`, suivant la convention de `DEVELOPMENT` :

```python
TOUS_ABONNES = os.getenv("TOUS_ABONNES", "False").lower() == "true"
```

Documentée dans `.template.env`.

### 2. Déblocage de l'accès (point unique)

`src/pages/_compte_shell.py::current_user_has_subscription()` :

```python
def current_user_has_subscription() -> bool:
    from src.subscriptions import db

    if not current_user.is_authenticated:
        return False
    if TOUS_ABONNES:
        return True
    return db.has_active_subscription(current_user.id)
```

Ce seul changement débloque les sections `archives`/`filtres`/`siret` dans le
menu (`_nav`) **et** lève leur `account_guard`.

**On ne touche pas** à `db.has_active_subscription()` : il doit continuer à
refléter un vrai abonnement payant. Conséquence voulue : sur
`/compte/abonnement`, `has_access` reste `False` pour un utilisateur sans
abonnement réel → il voit les cartes de plans (désactivées) + le bandeau, et
non une fausse vue « abonnement actif ».

### 3. Bandeau d'information (page `/compte/abonnement` uniquement)

Dans `compte_abonnement.py::layout`, quand `TOUS_ABONNES`, insérer en haut du
`body` (avant les cartes) un `dbc.Alert` (`color="info"`) :

> Les fonctionnalités normalement accessibles contre un abonnement de 20 € HT
> par mois sont accessibles à tous et toutes en attendant la validation de mon
> dossier pour recevoir des paiements.

### 4. Boutons « S'abonner » désactivés et gris

Dans `compte_abonnement.py::_plan_card`, quand `TOUS_ABONNES`, le bouton est
rendu désactivé et gris (`className="btn btn-secondary disabled"`,
`disabled=True`). Les cartes restent visibles à titre informatif.

### 5. Redirection post-login

**Inchangée.** `_post_login_url` s'appuie sur `db.has_active_subscription`, qui
reste `False` pour les non-abonnés réels → redirection vers
`/compte/abonnement`, ce qui est le comportement souhaité avec `TOUS_ABONNES`.

## Hors périmètre

- Aucune autre fonctionnalité « abonné » n'est gatée ailleurs que via
  `account_guard` (vérifié : pas de contrôle d'abonnement dans `tableau.py`,
  exports, sauvegarde de filtres).
- Pas de modification du flux de paiement Frisbii ni du webhook.

## Tests

- `current_user_has_subscription()` : `True` si connecté + `TOUS_ABONNES`,
  `False` si non connecté même avec le drapeau, comportement DB normal si
  drapeau absent.
- `visible_sections` : sections réservées visibles via le drapeau (en
  s'appuyant sur le helper).
- `compte_abonnement` : bandeau présent et bouton désactivé quand `TOUS_ABONNES`
  est actif ; absents sinon.
