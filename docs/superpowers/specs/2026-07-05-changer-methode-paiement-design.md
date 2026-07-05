# Changer de méthode de paiement (issue #108) — Design

Date : 2026-07-05
Branche : `dev`

## Objectif

Permettre à un·e abonné·e actif·ve ou en essai de changer sa carte bancaire
depuis `/compte/abonnement`, sans repasser par tout le flux d'inscription.

## Mécanisme Frisbii

`GET /v1/subscription/{handle}` (déjà implémenté : `client.get_subscription`)
renvoie un champ `hosted_page_links.payment_info` : une page hébergée par
Frisbii, dédiée au changement de carte sur un abonnement existant
(doc : https://docs.frisbii.com/docs/change-payment-method-on-existing-subscription).
Elle accepte `accept_url` et `cancel_url` en query params pour rediriger après
succès/annulation.

Ce mécanisme est plus simple que le flux `add-payment` existant (Checkout API
`/v1/session/recurring` + callback qui associe la nouvelle méthode via
`set_subscription_payment_method`) : pas de session à créer, pas de callback à
gérer côté colibre, Frisbii associe directement la nouvelle carte à
l'abonnement.

## Portée

Bouton **« Changer de méthode de paiement »** affiché uniquement pour
`row["status"] in ("trial", "active")` :

- `pending` garde son bouton actuel « Ajouter une méthode de paiement »
  (aucune carte n'existe encore, flux différent).
- `cancelled` n'a pas ce bouton : l'abonnement s'arrête à la fin de la
  période en cours, il n'y a plus rien à facturer dessus. Le chemin logique
  est de reprendre un abonnement (`_reabo_button`, déjà géré ailleurs).

## Fichiers touchés

### `src/subscriptions/client.py`

Nouvelle fonction :

```python
def get_payment_info_url(sub_handle: str, accept_url: str, cancel_url: str) -> str:
    sub = get_subscription(sub_handle)
    url = sub["hosted_page_links"]["payment_info"]
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["accept_url"] = accept_url
    query["cancel_url"] = cancel_url
    return urlunsplit(parts._replace(query=urlencode(query)))
```

Utilise `urllib.parse` pour fusionner proprement avec une éventuelle query
string déjà présente sur `payment_info` plutôt que de la concaténer
naïvement.

### `src/subscriptions/routes.py`

Nouvelle route, symétrique à `add_payment()` / `cancel()` :

```python
@subscriptions_bp.route("/subscriptions/change-payment-method", methods=["POST"])
@login_required
def change_payment_method():
    base = os.getenv("APP_BASE_URL", "")
    row = db.get_current(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement actif", 400
    try:
        url = client.get_payment_info_url(
            row["frisbii_subscription_handle"],
            f"{base}/compte/abonnement?carte=succes",
            f"{base}/compte/abonnement?carte=annule",
        )
    except client.FrisbiiError:
        logger.exception("Échec de récupération du lien de paiement Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    return redirect(url, code=303)
```

Pas de webhook/callback à gérer : Frisbii associe la nouvelle méthode de
paiement à l'abonnement de son côté, et le webhook existant
(`/frisbii/webhook`) continuera de refléter l'état de l'abonnement comme
aujourd'hui.

### `src/pages/compte/abonnement.py`

- `_active_view(row)` : pour `row["status"] in ("trial", "active")`, ajouter
  un `html.Form` POST vers `/subscriptions/change-payment-method` (CSRF token
  via `_csrf_input()`), bouton `btn btn-outline-secondary`
  « Changer de méthode de paiement », affiché à côté du bouton
  « Me désabonner » existant.
- `_feedback(query)` : ajouter la gestion de `query.get("carte")` :
  - `"succes"` → alerte success « Méthode de paiement mise à jour. »
  - `"annule"` → alerte secondary « Modification annulée. »

## Gestion d'erreurs

- Pas d'abonnement / pas de handle → 400 (cas normalement inatteignable
  depuis l'UI, le bouton n'étant rendu que si `row` existe et a un statut
  trial/active, donc un handle).
- Échec API Frisbii (`FrisbiiError`) → `logger.exception` +
  `redirect("/compte/abonnement?error=frisbii")`, réutilise l'alerte
  « Une erreur est survenue avec le service de paiement. » déjà gérée par
  `_feedback`.

## Tests

- `tests/subscriptions/` : test de `client.get_payment_info_url` — mock de
  `client.get_subscription` (ou de `_call`), vérifie que `accept_url` et
  `cancel_url` sont bien ajoutés à l'URL, y compris si `payment_info` a déjà
  une query string.
- Test de la route `change_payment_method` : redirect 303 vers l'URL Frisbii
  quand un abonnement actif existe ; 400 si pas d'abonnement.
- Test de `_feedback()` pour les nouvelles clés `carte=succes` / `carte=annule`.

## Hors périmètre (YAGNI)

- Affichage de la carte actuellement enregistrée (marque, 4 derniers
  chiffres) — pourra venir plus tard via `client.get_customer_payment_methods`.
- Bouton pour `cancelled` (cf. Portée ci-dessus).
- Gestion multi-méthodes de paiement (le champ `active_payment_methods` de
  Frisbii ne contient au plus qu'un élément dans notre usage actuel).
