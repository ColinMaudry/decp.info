# Démarrage manuel de l'abonnement à la fin de l'essai

Issue : [#132](https://github.com/ColinMaudry/colibre/issues/132)
Date : 2026-08-13

## Contrainte

L'organisme bancaire qui évalue le processus d'inscription de colibre exige que
le passage de l'essai gratuit à l'abonnement payant **ne soit pas automatique** :
la conversion automatique d'un essai vers un débit récurrent est classée « à
haut risque » et entraîne des frais supplémentaires. Le premier débit doit
résulter d'une action explicite de l'utilisateur, postérieure à la fin de
l'essai.

## Décision

L'essai sort entièrement de Frisbii.

Aujourd'hui l'essai est une propriété du plan Frisbii : l'abonnement est créé
dès l'entrée en essai, la carte est collectée immédiatement, et c'est Frisbii
qui tient l'horloge et déclenche le débit. Frisbii/Reepay n'expose aucun
endpoint permettant de repousser ou de terminer un essai (`on_hold`,
`reactivate`, `cancel`, `expire` seulement) : empêcher le débit supposerait
d'agir avant l'échéance, avec une fenêtre de 2 jours et un risque de course.

Désormais :

- **Pendant l'essai, aucun abonnement Frisbii n'existe et aucune carte n'est
  enregistrée.** L'essai est une simple fenêtre de dates côté colibre.
- **L'abonnement payant n'est créé qu'au moment de la décision d'achat**, via le
  parcours de souscription existant avec `no_trial=True`.

Le risque de prélèvement non sollicité devient structurellement nul : il n'y a
rien à débiter tant que l'utilisateur n'a pas saisi sa carte, et il ne la
saisit qu'après avoir vu le récapitulatif de commande et cliqué sur un bouton
qui nomme le montant.

## Modèle de données

Une colonne sur `subscriber_state` :

```sql
ALTER TABLE subscriber_state ADD COLUMN trial_ends_at TEXT   -- ISO 8601 UTC
```

- `NULL` = aucun essai n'a jamais été ouvert pour ce compte.
- La valeur est posée **une seule fois** et jamais réécrite : un compte ne peut
  pas rouvrir un essai.
- Migration `0014_add_trial_ends_at_to_subscriber_state` dans `src/migrations.py`
  (et ajout de la colonne à `SUBSCRIPTIONS_SCHEMA` pour les bases fraîches).
- Les comptes existants gardent `NULL` : pas d'essai rétroactif. Sans effet en
  production, qui tourne en `TOUS_ABONNES`.

`trial_used` n'est plus ni lu ni écrit : `trial_ends_at IS NOT NULL` porte la
même information. La colonne est laissée en place (retrait dans un
nettoyage ultérieur), mais `has_used_trial()` et `plans.trial_days()`
disparaissent.

Durée : `TRIAL_DAYS = 2`, constante dans `src/subscriptions/db.py`.

## Démarrage de l'essai

Un compte non vérifié ne peut pas se connecter : `login()` refuse la session
tant que `email_verified` est faux (`src/auth/routes.py:149`), et tout l'espace
abonné exige `current_user.is_authenticated` (`src/pages/_compte_shell.py:62`).
Démarrer l'horloge à la soumission du formulaire ferait donc courir l'essai sur
un compte strictement inutilisable.

L'essai démarre à **l'activation du compte**, c'est-à-dire aux deux points où
`login_user()` est appelé pour la première fois :

- `verify_email()` — clic sur le lien de vérification ;
- `linkedin_callback()` — l'email est attesté par LinkedIn.

Les deux appellent `start_trial_if_new(user_id)`, idempotent : il n'écrit que
si `trial_ends_at IS NULL`.

## Accès aux fonctionnalités

`has_active_subscription()` est aujourd'hui appelée pour deux usages qui
divergent maintenant :

| Usage                                                       | Appelants                                                                              | Comportement pendant l'essai |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------- | ---------------------------- |
| Ouvrir les fonctionnalités                                  | `_compte_shell`, `mcp/auth`, `mcp/oauth/consent`, `mcp/account`, `a_propos/abonnement` | **oui**                      |
| Empêcher une souscription en double, router après connexion | `subscriptions/routes.py:22`, `auth/routes.py:22`                                      | **non**                      |

Si le second groupe comptait l'essai, un utilisateur en essai ne pourrait plus
s'abonner du tout — exactement le parcours que cette issue cherche à ouvrir.

D'où :

- `has_active_subscription()` **inchangée** : elle ne parle que d'abonnements.
- `trial_active(user_id)` : `trial_ends_at` non nul et dans le futur.
- `has_access(user_id)` : `trial_active(user_id) or has_active_subscription(user_id)`.

Seul le premier groupe bascule vers `has_access`. `TOUS_ABONNES` reste traité
aux appels, comme aujourd'hui.

Les votes de la roadmap restent fermés pendant l'essai sans code
supplémentaire : `_accrues_votes()` exige une ligne `subscriptions`, qui
n'existe pas pendant l'essai. Le comportement actuel (`status == "trial"` →
pas d'accumulation) est préservé par construction.

## Parcours

| Moment                                    | Écran                                                                                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Inscription                               | mention : « Votre essai gratuit de 2 jours démarre dès la validation de votre adresse email. »                                       |
| Vérification de l'email / retour LinkedIn | redirection vers `/compte/abonnement` (aujourd'hui `/compte/abonnement/mes-infos` hors `TOUS_ABONNES`)                               |
| Pendant l'essai                           | `/compte/abonnement` : « Essai gratuit jusqu'au JJ/MM/AAAA à HH:MM » + rappel des fonctionnalités débloquées                         |
| Essai terminé                             | `/compte/abonnement` : « Votre essai gratuit est terminé » + bouton **Commencer mon abonnement** vers `/compte/abonnement/mes-infos` |
| Confirmation                              | `/compte/abonnement/mes-infos` : choix de formule + récapitulatif de commande. Bouton **Commencer mon abonnement (24 € TTC / mois)** |
| Paiement                                  | checkout Frisbii → débit → `active`                                                                                                  |

Le montant ne figure pas sur le bouton de `/compte/abonnement` : à ce stade
l'utilisateur n'a pas encore choisi de formule. Il apparaît sur le bouton de
`/compte/abonnement/mes-infos`, dont le libellé suit la formule sélectionnée
(24 € TTC pour la formule simple, 60 € TTC pour le soutien) via le callback
`_select_plan` qui pilote déjà les cartes de formule et le récapitulatif.

Pas de modale de confirmation. `/compte/abonnement/mes-infos` remplit déjà ce
rôle et mieux : elle porte la sélection de formule — que l'utilisateur n'a plus
faite en amont, puisqu'il n'y a plus de souscription à l'entrée en essai — et
un récapitulatif de commande (vendeur, prestation, début, durée, prix HT/TTC)
construit précisément pour l'organisme de validation
(`_recap_lines`, `src/pages/compte/abonnement_mes_infos.py:48-54`). Une modale
n'ajouterait qu'un écran redondant entre ce récapitulatif et le checkout, qui
affiche à nouveau le montant.

## Modifications par fichier

**`src/migrations.py`** — migration `0014`.

**`src/subscriptions/db.py`** — `trial_ends_at` dans le schéma ; constante
`TRIAL_DAYS` ; `start_trial_if_new()`, `trial_active()`, `has_access()` ;
suppression de `has_used_trial()` ; `update_from_webhook()` cesse d'écrire
`trial_used`.

**`src/subscriptions/plans.py`** — suppression de `trial_days()` et de la clé
`trial_days` des deux plans.

**`src/subscriptions/routes.py`** — `subscribe()` passe toujours
`no_trial=True` ; suppression du discriminant `souscription=trial` sur
l'`accept_url` ; le garde d'entrée reste sur `has_active_subscription()`.

**`src/auth/routes.py`** — `start_trial_if_new()` dans `verify_email()` et
`linkedin_callback()` ; destination post-vérification `/compte/abonnement`
quel que soit `TOUS_ABONNES`.

**`src/pages/inscription.py`** — mention de l'essai sous le formulaire ;
`linkedin_next` → `/compte/abonnement` inconditionnellement.

**`src/pages/_compte_shell.py`**, **`src/mcp/auth.py`**,
**`src/mcp/oauth/consent.py`**, **`src/mcp/account.py`**,
**`src/pages/a_propos/abonnement.py`** — `has_active_subscription` →
`has_access`.

**`src/pages/compte/abonnement.py`** — vue « essai en cours » et vue « essai
terminé » avec le bouton ; suppression de la branche `trial` de `_active_view`
(devenue morte) ; correction du texte de la branche `pending`, qui annonce une
résiliation « à la fin de la période d'essai » alors qu'il n'y a plus d'essai à
ce stade — un abonnement `pending` est désormais une souscription abandonnée en
cours de checkout, à reprendre.

**`src/pages/compte/abonnement_mes_infos.py`** — suppression de `_trial_for` et
du paramètre `trial` de `_recap_lines` / `_recap` ; « Début de l'abonnement
payant » = date du jour ; libellé du bouton de soumission.

**`src/assets/goals.js`** — l'objectif Matomo `subscription_trial` était émis au
retour du checkout ; ce moment n'existe plus. Il est ré-ancré sur le démarrage
effectif de l'essai, via un paramètre posé sur la redirection
post-vérification. L'entonnoir devient : compte créé → essai démarré →
abonnement actif.

**`docs/cgv-abonnement-api.md`**, **`src/pages/a_propos/abonnement.py`** —
relecture des clauses et mentions d'essai et de reconduction : l'essai n'est
plus adossé à un abonnement et ne se transforme plus en abonnement.

## Frisbii (hors code)

Retirer la période d'essai de la configuration des plans `FRISBII_PLAN_SIMPLE`
et `FRISBII_PLAN_SOUTIEN`. Ceinture et bretelles : un oubli de `no_trial`
côté code ne pourra pas réintroduire la conversion automatique.

## Tests

- `trial_active()` : `trial_ends_at` nul, dans le futur, dans le passé, et à la
  borne.
- `start_trial_if_new()` : pose la date au premier appel, ne la réécrit pas aux
  suivants ; crée la ligne `subscriber_state` si absente.
- `has_access()` : essai en cours / abonné / ni l'un ni l'autre / `TOUS_ABONNES`.
- `verify_email()` et `linkedin_callback()` démarrent l'essai et redirigent vers
  `/compte/abonnement`.
- Un utilisateur en essai peut souscrire : `subscribe()` n'est pas bloqué par
  son essai et passe `no_trial=True`.
- Les accès MCP sont ouverts pendant l'essai et fermés après.
- `/compte/abonnement` affiche les trois états (essai en cours, essai terminé,
  abonné).
- Les votes roadmap restent fermés pendant l'essai.

## Hors périmètre

- **Email de relance** à J-1 et à la fin de l'essai. Utile pour la conversion,
  mais sans lien avec l'exigence de la banque ; à ouvrir en issue séparée.
- **Bandeau d'essai global** (navbar). L'essai est annoncé sur
  `/compte/abonnement`, où l'utilisateur atterrit juste après la validation de
  son email. Un rappel permanent est ajoutable ensuite si la conversion le
  justifie.
- **Retrait de la colonne `trial_used`**, laissée en place et inutilisée.
- **Retrait de `"trial"` de `_ACCESS_STATUSES`**. Plus aucun abonnement Frisbii
  ne devrait atteindre ce statut, mais le laisser coûte zéro et évite qu'un plan
  Frisbii encore configuré avec un essai ne coupe l'accès d'un abonné.
