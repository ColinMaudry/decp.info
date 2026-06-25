# Abonnements payants via Frisbii — design

- **Issue** : [#90](https://github.com/ColinMaudry/decp.info/issues/90)
- **Branche** : `feature/90_subscriptions`
- **Date** : 2026-06-25

## Objectif

Permettre à un utilisateur connecté de **souscrire** un abonnement payant et de
**résilier** son abonnement, via [Frisbii](https://docs.frisbii.com/) (ex-Reepay),
une solution européenne de gestion d'abonnements. L'abonnement débloque les
sections premium de l'espace compte (Mes archives, Mes filtres, Mon SIRET), déjà
protégées par le mécanisme `require_subscription`.

Le câblage côté app est déjà prêt : `current_user_has_subscription()` dans
`src/pages/_compte_shell.py` est un stub qui renvoie `False`, et
`src/pages/compte_abonnement.py` est une page placeholder. Cette fonctionnalité
les branche sur Frisbii.

## Décisions clés

1. **Session de checkout hébergée + webhooks.** On crée une _subscription session_
   Frisbii (`POST /v1/session/subscription`) qui renvoie une URL de page de
   paiement hébergée. Frisbii collecte la carte ; on ne manipule jamais de données
   de paiement. Les **webhooks** sont la **source de vérité** de l'état d'abonnement.
2. **Deux plans fixes, définis côté Frisbii.** decp.info ne référence que leurs
   _handles_ (via `.env`) :

   - `simple` — **20 € HT / mois**
   - `soutien` — **50 € HT / mois**

   Les deux plans donnent **le même accès premium** ; le soutien est une
   contribution supérieure, pas un palier de fonctionnalités.

3. **Abonnement à durée indéterminée, mois glissants.** L'abonnement est renouvelé
   chaque mois (période ancrée sur la date d'inscription, comportement par défaut
   Frisbii — pas de prorata de première période). Il perdure jusqu'à résiliation.
4. **Essai gratuit configuré côté Frisbii (2 jours souhaités).** L'essai est un
   `trial_interval` réglé sur **chaque plan dans le dashboard Frisbii** (aucun code
   pour le définir, et **la durée n'est pas codée en dur** côté app : elle est lue
   depuis le plan via l'API). La carte est **collectée à la souscription** (page hébergée)
   mais débitée seulement à la fin de l'essai ; l'abonnement passe alors
   automatiquement de `trial` à `active`. Si le paiement échoue → `expired`. Une
   résiliation pendant l'essai expire en **fin d'essai** (pas de débit). Pendant
   l'essai, l'utilisateur a **accès aux fonctions premium**.
5. **Résiliation en fin de période courante.** `POST` cancel Frisbii avec le
   comportement **par défaut** (expiration en fin de période courante — ou fin
   d'essai si en essai). L'accès est maintenu jusqu'à `current_period_end` renvoyé
   par Frisbii ; aucun calcul de date côté app.
6. **Clé privée serveur uniquement.** HTTP Basic Auth (clé privée en username),
   jamais exposée au frontend.

## Architecture

Nouveau module `src/subscriptions/`, calqué sur `src/auth/`, avec des frontières
nettes :

| Fichier     | Rôle                                                           | Dépendances       | Ne dépend PAS de |
| ----------- | -------------------------------------------------------------- | ----------------- | ---------------- |
| `client.py` | Client HTTP pur de l'API Frisbii                               | `requests`, env   | DB, Flask        |
| `db.py`     | Table `subscriptions` (réutilise `auth.db.get_conn`)           | sqlite            | Flask, client    |
| `plans.py`  | Catalogue des plans (clé → handle, libellé, prix, description) | env               | DB, Flask        |
| `routes.py` | Blueprint Flask : subscribe, cancel, webhook                   | client, db, plans | —                |
| `setup.py`  | `init_subscriptions(app)`                                      | routes            | —                |

Côté présentation :

- `src/pages/compte_abonnement.py` — UI de la page `/compte/abonnement`.
- `src/pages/_compte_shell.py` — `current_user_has_subscription()` branché sur
  `subscriptions.db`.

### `client.py` — client Frisbii

Fonctions pures, sans état applicatif (toute config lue depuis l'env) :

- `_auth()` → tuple HTTP Basic `(FRISBII_API_KEY, "")`.
- `get_or_create_customer(handle: str, email: str) -> dict`
  - Handle déterministe `decpinfo-{user_id}`. GET le customer ; s'il n'existe pas
    (404), le crée (`POST /v1/customer`). Idempotent.
- `create_subscription_session(plan_handle, customer_handle, accept_url, cancel_url) -> str`
  - `POST /v1/session/subscription` avec `prepare_subscription` (plan + customer) et
    les URLs de retour. Renvoie l'`url` hébergée.
- `cancel_subscription(subscription_handle) -> dict`
  - Cancel par défaut (fin de période courante). Renvoie l'objet subscription.
- `get_subscription(subscription_handle) -> dict` (utilitaire de réconciliation).
- `get_plan(plan_handle) -> dict`
  - `GET /v1/plan/{handle}`. Sert à lire les caractéristiques du plan (dont la durée
    d'essai `trial_interval`) sans la coder en dur côté app.

Base URL : `FRISBII_API_BASE_URL` (à confirmer au moment de l'implémentation depuis
la doc Frisbii ; valeur par défaut documentée dans `.template.env`). Timeouts
explicites sur tous les appels. Les erreurs HTTP lèvent une exception
`FrisbiiError` (sous-classe locale) loggée par l'appelant.

### `db.py` — état d'abonnement

Table `subscriptions` dans `users.sqlite` (un abonnement courant par utilisateur) :

```sql
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id                     INTEGER PRIMARY KEY,
    frisbii_customer_handle     TEXT,
    frisbii_subscription_handle TEXT,
    plan                        TEXT,   -- 'simple' | 'soutien'
    status                      TEXT,   -- 'pending' | 'trial' | 'active' | 'cancelled' | 'expired'
    current_period_end          TEXT,   -- ISO 8601, nullable
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer
    ON subscriptions(frisbii_customer_handle);
```

Le module possède sa propre `init_schema()` (appelée depuis `setup.py`) utilisant
`auth.db.get_conn()`, pour rester isolé du schéma auth.

Fonctions :

- `upsert_subscription(user_id, customer_handle, subscription_handle, plan, status, current_period_end)`
- `get_subscription_by_user(user_id) -> Row | None`
- `get_subscription_by_customer(customer_handle) -> Row | None` (résolution webhook)
- `set_status(user_id, status, current_period_end=None)`
- `has_active_subscription(user_id) -> bool`
  → `True` si une ligne existe avec `status` dans (`trial`, `active`) **ou**
  (`status='cancelled'` **et** `current_period_end` dans le futur). Couvre l'essai en
  cours et le cas « résilié mais encore valide jusqu'à la fin de la période ».

### Statuts et cycle de vie

| Statut      | Sens                                          | Accès premium         |
| ----------- | --------------------------------------------- | --------------------- |
| `pending`   | Session créée, paiement pas encore confirmé   | non                   |
| `trial`     | Essai gratuit en cours (2 j), carte collectée | oui                   |
| `active`    | Abonnement en cours, renouvelé chaque mois    | oui                   |
| `cancelled` | Résilié, valide jusqu'à `current_period_end`  | oui (jusqu'à la date) |
| `expired`   | Période échue (annulé ou échec de paiement)   | non                   |

### `routes.py` — blueprint Flask

`subscriptions_bp` (préfixe explicite par route) :

- `POST /subscriptions/subscribe` — `@login_required`, **CSRF protégé**.
  - Form `plan=simple|soutien`. Résout le handle via `plans.py` (400 si inconnu).
  - `get_or_create_customer("decpinfo-{user_id}", email)`.
  - `upsert_subscription(..., status='pending')`.
  - `create_subscription_session(...)` avec
    `accept_url={APP_BASE_URL}/compte/abonnement?paiement=succes` et
    `cancel_url={APP_BASE_URL}/compte/abonnement?paiement=annule`.
  - Redirection **303** vers l'URL hébergée.
  - En cas d'erreur API : redirection `/compte/abonnement?error=frisbii` + log.
- `POST /subscriptions/cancel` — `@login_required`, **CSRF protégé**.
  - Récupère l'abonnement de l'utilisateur ; 400 s'il n'y en a pas d'actif.
  - `cancel_subscription(handle)` (défaut = fin de période).
  - Met à jour le statut localement (`cancelled` + `current_period_end` si renvoyé) ;
    le webhook confirmera.
  - Redirection `/compte/abonnement?resiliation=ok`.
- `POST /frisbii/webhook` — **CSRF-exempt**, pas d'auth de session.
  - **Vérifie la signature** via `FRISBII_WEBHOOK_SECRET` selon le schéma documenté
    par Frisbii (à confirmer depuis la doc webhooks à l'implémentation). Signature
    invalide → **403**.
  - Dispatch par type d'événement (mapping vers l'utilisateur via le customer
    handle stocké) :
    - `subscription_created` → `status='trial'` si l'abonnement démarre en essai
      (champ d'essai du payload), sinon `status='active'` ; `current_period_end`
      (= fin d'essai pendant l'essai) maj.
    - fin d'essai / premier débit (`subscription_renewed` / `invoice_settled`) →
      `status='active'`, `current_period_end` maj.
    - `invoice_settled` / renouvellement → `current_period_end` maj.
    - `subscription_cancelled` → `status='cancelled'`, `current_period_end` maj.
    - `subscription_expired` / échec de paiement terminal → `status='expired'`.
  - Événement inconnu → **200** (ignoré). Erreur de traitement → **5xx** pour que
    Frisbii réessaie. Les noms exacts d'événements seront confirmés depuis la doc
    Frisbii ; le dispatch est piloté par une table `EVENT_HANDLERS` facile à étendre.

### `setup.py` — initialisation

`init_subscriptions(app)` :

- `db.init_schema()`.
- Enregistre `subscriptions_bp`.
- Exempte la vue webhook de CSRF (même approche que `_auth_csrf.exempt` dans
  `src/app.py`).
- Warnings au démarrage si `FRISBII_API_KEY`, `FRISBII_WEBHOOK_SECRET`,
  `FRISBII_PLAN_SIMPLE` ou `FRISBII_PLAN_SOUTIEN` manquent (comme Brevo/LinkedIn).

Appelé depuis `src/app.py` après `init_auth(...)`.

### `plans.py` — catalogue

```python
PLANS = {
    "simple":  {"handle": env("FRISBII_PLAN_SIMPLE"),  "label": "Abonnement simple",
                "prix_ht": 20, "description": "..."},
    "soutien": {"handle": env("FRISBII_PLAN_SOUTIEN"), "label": "Abonnement de soutien",
                "prix_ht": 50, "description": "..."},
}
```

`resolve_handle(key) -> str | None` pour les routes ; le dict sert aussi à rendre
les cartes de la page.

`trial_days(key) -> int | None` : lit la durée d'essai **depuis Frisbii**
(`client.get_plan(handle)` → `trial_interval`, parsé en jours), avec un **cache**
(TTL ~1 h via `src/utils/cache.py`, les plans changeant rarement). Échec API ou plan
sans essai → `None` (la mention d'essai est alors masquée, pas de valeur en dur).

## Page `/compte/abonnement`

`account_guard("/compte/abonnement", require_subscription=False)` reste (la page est
accessible sans abonnement). Le contenu dépend de l'état :

**Sans abonnement actif** :

- Deux cartes de plan (Simple 20 € HT/mois, Soutien 50 € HT/mois), chacune avec un
  formulaire `POST /subscriptions/subscribe` (input caché `plan` + CSRF) et un bouton
  « S'abonner ». Mention « {n} jours d'essai gratuit » sur les cartes, où `{n}` est
  lu depuis le plan via `plans.trial_days(key)` (masquée si le plan n'a pas d'essai).
- Contenu pédagogique (issue #90) :
  - **À quoi servent les abonnements** : abonnement Frisbii 50 €, serveur Scaleway
    40 €, espace de coworking 250 €, salaire médian 3 840 €.
  - **Ce que le soutien permettrait** : rédaction d'études à partir des données (ex.
    acheteurs aux données introuvables et raisons de la non-publication) ;
    coordination des bonnes volontés militant pour une législation plus exigeante sur
    la transparence de la commande publique.

**Avec abonnement actif** :

- Plan courant, statut, date de prochain renouvellement / fin de validité
  (`current_period_end`).
- Si `trial` : bandeau « Essai gratuit jusqu'au {date}, puis débit automatique ».
- Si `cancelled` : bandeau « Abonnement résilié, actif jusqu'au {date} ».
- Si `trial` ou `active` : formulaire `POST /subscriptions/cancel` (CSRF) + bouton
  « Résilier » (en essai, la résiliation évite tout débit).

**Messages de retour** (query params lus dans le `layout`) : `paiement=succes`
(« Merci, votre abonnement est en cours d'activation »), `paiement=annule`,
`resiliation=ok`, `error=frisbii`.

## `current_user_has_subscription()`

Dans `_compte_shell.py`, remplacer le stub par :

```python
def current_user_has_subscription() -> bool:
    if not current_user.is_authenticated:
        return False
    return subscriptions.db.has_active_subscription(current_user.id)
```

C'est le seul point de branchement avec le reste de l'espace compte ; le mécanisme
`visible_sections` / `guard_redirect` existant fonctionne tel quel.

## Configuration (`.template.env`)

```bash
# Frisbii — gestion des abonnements (https://docs.frisbii.com)
FRISBII_API_KEY=                 # clé PRIVÉE (priv_...), serveur uniquement
FRISBII_API_BASE_URL=            # base de l'API Frisbii (cf. doc)
FRISBII_PLAN_SIMPLE=             # handle du plan "abonnement simple" (20 € HT/mois)
FRISBII_PLAN_SOUTIEN=            # handle du plan "abonnement de soutien" (50 € HT/mois)
FRISBII_WEBHOOK_SECRET=          # secret de signature des webhooks
```

**Prérequis de configuration côté dashboard Frisbii** (hors code, à documenter) :

- Créer les deux plans mensuels (mois glissants, ancrés sur la date d'inscription)
  avec un **essai de 2 jours** (`trial_interval`) et collecte de la carte à la
  souscription.
- Configurer un webhook vers `{APP_BASE_URL}/frisbii/webhook` avec les événements
  d'abonnement et de facturation, et récupérer le secret de signature.

## Gestion des erreurs

| Situation                    | Comportement                                                              |
| ---------------------------- | ------------------------------------------------------------------------- |
| Échec API à la souscription  | Redirect `/compte/abonnement?error=frisbii` + log                         |
| Échec API à la résiliation   | Redirect `/compte/abonnement?error=frisbii` + log ; statut local inchangé |
| Webhook signature invalide   | 403, pas de traitement                                                    |
| Webhook événement inconnu    | 200, ignoré                                                               |
| Webhook erreur de traitement | 5xx → Frisbii réessaie                                                    |
| Config Frisbii absente       | Warnings au démarrage ; souscription échoue proprement                    |

## Tests

Unitaires (mocks, pas d'appel réseau réel) :

- `client.py` : auth Basic, get-or-create customer (200 vs 404→create), création de
  session (URL renvoyée), cancel ; gestion d'erreur HTTP → `FrisbiiError`. HTTP mocké.
- `db.py` : upsert / get / set_status ; `has_active_subscription` pour chaque statut
  (`trial` et `active` → vrai ; `cancelled` futur → vrai, passé → faux ; `pending`
  et `expired` → faux).
- `plans.py` : `resolve_handle` (connu / inconnu) ; `trial_days` (parsing du
  `trial_interval` renvoyé par un `get_plan` mocké, mise en cache, `None` si échec API
  ou plan sans essai).
- `routes.py` : webhook — signature valide/invalide, dispatch de chaque événement
  vers le bon changement de statut (payloads factices), résolution par customer
  handle ; subscribe (redirect 303 vers l'URL de session, statut `pending` créé) ;
  cancel (appel client + statut `cancelled`).

Intégration légère (rendu) :

- Page `/compte/abonnement` : affiche les deux cartes + boutons « S'abonner » sans
  abonnement ; affiche le bouton « Résilier » et la date avec abonnement actif (DB
  de test préremplie).

## Hors périmètre (YAGNI)

- Changement de plan / upgrade-downgrade en self-service (le client peut résilier et
  re-souscrire).
- Montant de soutien libre (décidé : plans fixes).
- Réconciliation périodique automatique (un utilitaire `get_subscription` existe pour
  un script manuel si besoin, mais pas de cron).
- Facturation / historique des factures dans l'UI (Frisbii fournit son propre portail
  et envoie les factures par email).
