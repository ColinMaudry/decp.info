# Migration des emails transactionnels vers Brevo (API + templates hébergés)

**Issue :** #87
**Branche :** `87_brevo` (partie de `feature/73_compte_utilisateur`)
**Date :** 2026-06-24

## Contexte

Les emails transactionnels de decp.info (vérification d'adresse à l'inscription,
réinitialisation de mot de passe) sont aujourd'hui envoyés via **Flask-Mail + SMTP**
(boîte mail Infomaniak standard). Cette approche n'offre aucune visibilité sur la
délivrabilité (le mail de reset est-il arrivé ?), expose au risque de suspension de
la boîte mail en cas de pic, et délivre moins bien.

On migre vers **Brevo** (compte gratuit existant) en utilisant son **API
transactionnelle** via le SDK officiel `brevo-python` **v5** (`5.0.0rc1`, une
pré-release / release candidate, à installer avec `--pre` et épinglée strictement)
et ses **templates hébergés**. Brevo est une société française, données en UE
(bon pour le RGPD).

L'API v5 (vérifiée par introspection du paquet) :

```python
from brevo import Brevo, SendTransacEmailRequestSender, SendTransacEmailRequestToItem
from brevo.core.api_error import ApiError

client = Brevo(api_key="...", headers={"X-Sib-Sandbox": "drop"})  # headers optionnels
client.transactional_emails.send_transac_email(
    template_id=123,
    params={"link": "https://..."},
    sender=SendTransacEmailRequestSender(email="noreply@decp.info", name="decp.info"),
    to=[SendTransacEmailRequestToItem(email="dest@example.com")],
)
```

## Objectif

Remplacer entièrement le transport SMTP/Flask-Mail par l'API Brevo, avec deux
templates hébergés côté Brevo (un par email), sans changer l'interface publique du
mailer ni le comportement des routes appelantes.

## Périmètre

### Dans le périmètre

- Réécriture de `src/auth/mailer.py` pour utiliser le SDK Brevo.
- Deux templates Brevo (déjà créés côté web), référencés par leur ID.
- Mise à jour des dépendances et des variables d'environnement.
- Suppression des templates Jinja d'email locaux.
- Réécriture des tests du mailer (hermétiques) + chemin sandbox optionnel.

### Hors périmètre

- Le contenu/design des templates Brevo (géré dans l'interface web Brevo).
- Les autres usages d'email du projet s'il en existe (variables legacy
  `SENDER_SERVER_DOMAIN`, `LOGIN_EMAIL`, `FROM_EMAIL`, `TO_EMAIL` de `.template.env`) :
  à **vérifier** avant suppression ; ne pas y toucher si utilisées ailleurs.

## Architecture

### Interface publique inchangée

Les fonctions appelées depuis `src/auth/routes.py` (lignes 49 et 112) gardent
exactement leur signature — **`routes.py` n'est pas modifié** :

```python
send_verification_email(email: str, token: str) -> None
send_reset_email(email: str, token: str) -> None
```

### Composants de `src/auth/mailer.py` (réécrit)

| Fonction                                         | Rôle                                                                                                                                                                                                         |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `init_mailer()`                                  | Construit le client `Brevo(api_key=...)` depuis `BREVO_API_KEY` (+ header sandbox si `BREVO_SANDBOX=true`). Plus de paramètre `app`. Stocke le client au niveau module.                                      |
| `_send_template(template_id, recipient, params)` | Appelle `client.transactional_emails.send_transac_email(template_id, params, sender=SendTransacEmailRequestSender(...), to=[SendTransacEmailRequestToItem(email=recipient)])`, log + remonte les `ApiError`. |
| `send_verification_email(email, token)`          | Construit le lien `{base}/auth/verify-email?token=...` et appelle `_send_template(VERIFY_ID, email, {"link": link})`.                                                                                        |
| `send_reset_email(email, token)`                 | Construit le lien `{base}/reinitialiser-mot-de-passe?token=...` et appelle `_send_template(RESET_ID, email, {"link": link})`.                                                                                |

Disparaît : toute la logique Jinja (`jinja_loader.searchpath`, `render_template`,
les templates `.txt`/`.html`), `MAIL_SUPPRESS_SEND`, l'objet Flask-Mail.

### Appel d'initialisation

`src/auth/setup.py:39` passe de `mailer.init_mailer(app)` à `mailer.init_mailer()`
(seule modification hors `mailer.py` et tests).

### Sender

Le sender (`MAIL_FROM` + `MAIL_FROM_NAME`) doit correspondre à un **expéditeur
vérifié dans Brevo** ; le domaine `decp.info` doit être authentifié (SPF/DKIM)
côté Brevo. Si le template Brevo définit déjà un sender, le passer explicitement
reste possible et prioritaire.

## Données / flux

1. Une route (`routes.py`) génère un token et appelle `send_*_email(email, token)`.
2. Le mailer construit le lien absolu (`APP_BASE_URL`) et l'envoie comme
   `params = {"link": link}`.
3. Le template Brevo correspondant (`template_id`) injecte `{{ params.link }}` dans
   son HTML et envoie.
4. En cas d'échec API : `ApiException` loggée puis remontée (comme aujourd'hui
   `flask_mail.send` pouvait lever).

## Variables d'environnement (`.template.env`)

**Ajoutées :**

- `BREVO_API_KEY=` — clé API transactionnelle Brevo
- `BREVO_TEMPLATE_VERIFY_ID=` — ID numérique du template de vérification
- `BREVO_TEMPLATE_RESET_ID=` — ID numérique du template de reset
- `BREVO_SANDBOX=` — `true` pour valider sans délivrer (dev / intégration)
- `MAIL_FROM_NAME=decp.info` — nom d'expéditeur

**Conservées :** `MAIL_FROM`, `APP_BASE_URL`

**Supprimées :** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`SMTP_USE_TLS`, `MAIL_SUPPRESS_SEND`

## Gestion d'erreur

- `_send_template` enveloppe l'appel dans un `try/except ApiError` : log
  (niveau error, sans la clé API) puis `raise` pour que l'appelant gère.
- Si `init_mailer()` n'a pas été appelé ou `BREVO_API_KEY` absente : `assert`/erreur
  explicite, comme l'actuel « Mailer non initialisé ».

## Stratégie de tests

Réconciliation validée :

- **Tests unitaires** (`tests/auth/test_mailer.py`, réécrit) : on **mocke** la méthode
  `transactional_emails.send_transac_email` du client (monkeypatch) et on capture les
  kwargs passés pour chaque fonction :
  - `to[0].email == "a@b.c"`
  - `template_id == BREVO_TEMPLATE_VERIFY_ID` / `..._RESET_ID`
  - `params["link"]` contient le bon chemin et le token
  - Aucun appel réseau, tourne en CI sans clé.
- **Mode sandbox Brevo** : pour la **vérification manuelle en dev** — `BREVO_SANDBOX=true`
  ajoute le header sandbox Brevo ; l'app accepte le déclenchement (signup/reset) et
  Brevo valide sans délivrer.
- **Test d'intégration optionnel** : `@pytest.mark.integration`, skippé par défaut,
  exécuté seulement si `BREVO_API_KEY` est présent, tape la vraie API en sandbox.

## Faits vérifiés / points résiduels

**Vérifié par introspection de `brevo-python==5.0.0rc1`** :

- Install : `pip install --pre "brevo-python==5.0.0rc1"` (package PyPI `brevo-python`,
  import `brevo`).
- Imports : `from brevo import Brevo, SendTransacEmailRequestSender, SendTransacEmailRequestToItem` ; `from brevo.core.api_error import ApiError`.
- Client : `Brevo(api_key=..., headers={...})` ; envoi via
  `client.transactional_emails.send_transac_email(template_id=int, params=dict, sender=..., to=[...], headers=dict|None)`.

**À confirmer en implémentation (ne pas bloquer) :**

- Valeur exacte du header sandbox Brevo (`X-Sib-Sandbox: drop` est la valeur
  documentée pour « accepter mais ne pas délivrer ») — à confirmer avec un envoi
  réel en sandbox.
- Usage éventuel des variables legacy `SENDER_SERVER_DOMAIN`/`LOGIN_EMAIL`/
  `FROM_EMAIL`/`TO_EMAIL` ailleurs dans le code avant toute suppression.

## Critères de succès

- L'inscription envoie un email de vérification via Brevo (template hébergé) avec
  un lien fonctionnel.
- La demande de reset envoie l'email de reset via Brevo avec un lien fonctionnel.
- `routes.py` inchangé ; toute la suite de tests passe sans réseau.
- `flask-mail` et les configs/templates SMTP retirés du dépôt.
