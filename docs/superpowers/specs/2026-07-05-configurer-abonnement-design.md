# Configurer son abonnement (#109)

## Contexte

Sur `/compte/abonnement`, un·e abonné·e `active`, `trial` ou `pending` ne
peut aujourd'hui ni changer de formule (simple ↔ soutien) ni mettre à jour
ses informations de facturation. Cette fonctionnalité l'ajoute, en réutilisant
la page `/compte/abonnement/mes-infos` déjà utilisée pour l'abonnement initial.

On en profite pour afficher le prix (HT + TTC) à côté de la formule courante
sur `/compte/abonnement`.

## Décisions produit

- **Effet du changement de formule** : à la prochaine échéance
  (`timing="renewal"`), sans proratisation ni remboursement. Simple à
  expliquer, aucun mouvement d'argent immédiat.
- **Cas `pending`** (abonnement créé mais sans méthode de paiement, billing
  non démarré) : mise à jour API directe. La formule change avec
  `timing="immediate"` (aucune échéance à laquelle rattacher un `renewal`) et
  les infos de facturation sont mises à jour. L'ajout de carte reste un bouton
  séparé sur `/compte/abonnement`.
- **Hint « prochaine échéance »** sous les cards : affiché uniquement pour
  `active`/`trial`. Rien pour `pending`.

## Architecture : flexibiliser `mes-infos` (pas de nouvelle page)

`/compte/abonnement/mes-infos` sert déjà ~80 % de ce dont on a besoin : le
formulaire de facturation à deux colonnes (10 champs), la recherche SIRET et
son callback, les cards de formule sélectionnables et `_select_plan`, le
préremplissage Frisbii, la modale CGU.

Les deux scénarios ne diffèrent que par : présence des cases à cocher, libellé
du bouton, cible/logique du formulaire, formule présélectionnée.

**Décision : flexibiliser `mes-infos` avec un `mode`** dérivé de l'état de
l'abonnement, plutôt qu'une nouvelle page. En Dash, deux pages ne peuvent pas
partager les mêmes `id` de composants : une page dupliquée forcerait à
renommer chaque `id` **et** à dupliquer les quatre callbacks (`_select_plan`,
`_lookup_siret`, `_toggle_submit`, `_toggle_cgu`) — soit l'essentiel du
fichier dupliqué pour 20 % de différence. `suppress_callback_exceptions=True`
(déjà activé, `src/app.py:88`) rend sûrs les composants rendus
conditionnellement.

**Le `mode` est dérivé de l'état, pas d'un paramètre d'URL.** Le bouton
« Configurer mon abonnement » et le bouton « M'abonner » pointent tous deux
vers `/compte/abonnement/mes-infos` ; la page s'adapte. Cela reprend la logique
du garde déjà présent dans `subscribe()` (refus d'un second abonnement quand
un est actif).

```python
row = db.get_current(current_user.id)
mode = "configure" if row and row["status"] in ("active", "trial", "pending") else "subscribe"
```

## Section 1 — page `/compte/abonnement`

Fichier : `src/pages/compte/abonnement.py`.

1. **Prix à côté de la formule** dans `_active_view`. Réutiliser le motif de
   `src/pages/a_propos/abonnement.py:34-35` :
   `{prix_ht} € HT / mois ({prix_ht * 1.2:g} € TTC)`. `plans.plan_meta()`
   retourne déjà `prix_ht`. Ajouter sous le `html.H3(meta["label"])` un
   paragraphe discret (`<small>`/muted) avec le prix.
2. **Bouton « Configurer mon abonnement »** : un lien
   (`href="/compte/abonnement/mes-infos"`, classe `btn`) ajouté dans les
   branches `active`/`trial`/`pending`, aux côtés de « Changer de méthode de
   paiement » et « Me désabonner ».
3. **Message de succès** : ajouter dans `_feedback()` une entrée
   `maj=succes` → _« Votre abonnement a été mis à jour. »_ (couleur `success`).

## Section 2 — page `/compte/abonnement/mes-infos`

Fichier : `src/pages/compte/abonnement_mes_infos.py`.

`layout()` calcule `row = db.get_current(current_user.id)` et en dérive `mode`.

Rendu conditionnel piloté par `mode` :

| Élément                             | `subscribe` (actuel)              | `configure` (nouveau)                                                   |
| ----------------------------------- | --------------------------------- | ----------------------------------------------------------------------- |
| Cards de formule                    | aucune présélectionnée            | formule courante (`row["plan"]`) présélectionnée via `_selection_state` |
| Cases à cocher (rétractation + CGU) | affichées                         | **omises**                                                              |
| Modale CGU                          | affichée                          | omise                                                                   |
| Libellé du bouton                   | « Ajouter une carte de paiement » | **« Mettre à jour mon abonnement »**                                    |
| `disabled` initial du bouton        | `True`                            | `False` (une formule est déjà sélectionnée)                             |
| `action` du formulaire              | `/subscriptions/subscribe`        | `/subscriptions/update` (nouvelle route)                                |
| Texte d'intro                       | « Choisissez votre formule : »    | « Votre formule : »                                                     |

Les colonnes de facturation (`col1`/`col2`), la recherche SIRET et le
préremplissage Frisbii sont identiques dans les deux modes.

### Hint « prochaine échéance »

- Élément message masqué sous les cards : `id="inf-change-hint"`,
  `className="d-none"` au départ (texte discret / info).
- La formule courante et la date d'échéance sont transmises au callback via un
  `dcc.Store` caché rempli dans le layout :
  `{"current_plan": row["plan"], "echeance": format_date_french(row["current_period_end"])}`,
  lu en `State`. En mode `subscribe`, le Store est absent → hint jamais affiché.
- Étendre le callback `_select_plan` (déjà déclenché au clic sur une card) pour
  produire aussi `className` + `children` du hint :
  - formule sélectionnée **==** formule courante → masqué (`d-none`)
  - formule sélectionnée **!=** formule courante **et** statut ∈ {active, trial}
    → affiché : _« Le changement d'abonnement sera appliqué à la prochaine
    échéance : {echeance}. »_
  - statut `pending` → rien (masqué) quelle que soit la sélection

### Callbacks

Les callbacks partagés (`_select_plan`, `_lookup_siret`, `_toggle_cgu`)
référencent des `id` qui existent toujours en mode `configure` (sauf
`_toggle_cgu`, dont les composants sont absents — toléré par
`suppress_callback_exceptions`).

`_toggle_submit` dépend aujourd'hui des deux cases à cocher, absentes en mode
`configure`. En mode `configure` le bouton démarre activé et n'est gardé par
aucune case ; le callback dégrade gracieusement (ses `Input` de cases ne sont
pas rendus). Forme exacte à confirmer à l'écriture du plan (p. ex. retour
`False`/`no_update` quand une formule est présente).

## Section 3 — route `/subscriptions/update` + client

Fichier : `src/subscriptions/routes.py`.

Nouvelle route `update()` (`@login_required`), de forme proche de
`subscribe()` mais **sans redirection vers un checkout** :

1. Charger `row = db.get_current(current_user.id)` ; si absent ou sans
   `frisbii_subscription_handle` → `400`.
2. **Mettre à jour les infos de facturation** : construire le dict `billing`
   depuis `request.form` (mêmes champs que `subscribe`), persister le SIRET via
   `auth_db.set_siret`, appeler `client.update_customer(cust, billing)`.
   (Pas de branche 404 : le customer existe déjà pour tout abo
   active/trial/pending.)
3. **Changer la formule si différente** : lire `plan` dans le formulaire ; si
   `plans.resolve_handle(plan)` diffère de la formule courante
   (`row["plan"]`), appeler `client.change_subscription(...)` avec
   `timing="immediate"` si `row["status"] == "pending"` sinon `"renewal"`.
4. Sur `client.FrisbiiError` → `redirect("/compte/abonnement?error=frisbii")`.
5. Sur succès → `redirect("/compte/abonnement?maj=succes", code=303)`.

Nouvelle fonction client dans `src/subscriptions/client.py` :

```python
def change_subscription(sub_handle: str, plan_handle: str, timing: str = "renewal") -> dict:
    return _call(
        "PUT",
        f"/v1/subscription/{sub_handle}",
        json={"timing": timing, "plan": plan_handle},
    )
```

Corps validé contre le schéma OpenAPI `ChangeSubscription` (endpoint
`PUT /v1/subscription/{handle}`, « Change subscription ») : `timing` est le
seul champ requis ; `plan` déclenche le changement de formule. Aucun paramètre
de proratisation puisque le changement est à la prochaine échéance.

**Note sur le timing des infos de facturation** : `update_customer` s'applique
immédiatement au customer, donc un changement d'adresse/SIRET prend effet tout
de suite même si le changement de _formule_ est différé à l'échéance. C'est
normal (adresse/SIRET ne sont pas liés à une période) ; le message de succès
reste générique (« mis à jour ») plutôt que d'impliquer que tout attend
l'échéance.

## Tests

- Fichier de test dédié à cette fonctionnalité (les champs d'abonnement de
  `tests/test.parquet` ne sont pas concernés ; l'état d'abonnement vit dans
  SQLite).
- Couvrir : dérivation du `mode` selon le statut ; rendu conditionnel
  (cases à cocher présentes/absentes, libellé du bouton, formule
  présélectionnée) ; route `update()` (mise à jour customer + appel
  `change_subscription` avec le bon `timing`, court-circuit si formule
  inchangée, garde 400 sans abonnement) ; affichage du hint selon
  statut/sélection.
- `client.change_subscription` : vérifier le corps JSON envoyé (mock httpx).
