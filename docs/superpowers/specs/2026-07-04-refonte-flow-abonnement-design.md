# Refonte du tunnel d'abonnement — abonnement public

## Contexte et objectif

Aujourd'hui, pour s'abonner, un visiteur doit : (1) créer un compte, (2) valider
son email, (3) se connecter, (4) seulement là découvrir et entamer le tunnel
d'abonnement. Les cards d'abonnement vivent derrière l'authentification, dans
`/compte/abonnement`. Ce parcours est trop long et masque l'offre aux visiteurs.

Objectif : **rendre l'offre d'abonnement visible aux visiteurs non connectés** et
raccourcir le tunnel, tout en préservant l'accès des anciens abonnés à leur compte
(factures) même s'ils ne sont plus abonnés.

## Principes

- **Se connecter ≠ être abonné.** La connexion ne requiert pas d'abonnement (déjà le
  cas). Un ancien abonné garde l'accès à `/compte/admin` et `/compte/abonnement`
  (guards en `require_subscription=False`). Il perd seulement l'accès aux sections
  réservées (`/compte/vues`, `/compte/roadmap`).
- **L'offre est publique.** La page `/a-propos/abonnement` (URL inchangée, au
  singulier) présente les cards et un unique bouton d'entrée dans le tunnel.
- **Le choix du plan (simple/soutien) se fait dans `mes-infos`**, pas sur la card.
  Cela évite de transporter le plan à travers inscription → email → mes-infos.

## Flow cible

```
Visiteur
  └─ navbar "Connexion" ─────────────► /connexion (formulaire + lien vers offre)
  └─ /a-propos/abonnement (public) ──► cards + explainer + bouton "Je m'abonne"
        │
        ├─ non connecté ────────────► /inscription
        │      ├─ email : signup → email de validation
        │      │        └─ clic lien ► /auth/verify-email : auto-login
        │      │                        └─► /compte/abonnement/mes-infos
        │      └─ LinkedIn (next=mes-infos) ─► /compte/abonnement/mes-infos
        │
        └─ déjà connecté, non abonné ► /compte/abonnement/mes-infos

/compte/abonnement/mes-infos
  └─ radios plan (simple/soutien, défaut simple) + rappel tarifs
     + infos facturation + cases CGU
        └─ POST /subscriptions/subscribe ► checkout Frisbii

/compte/abonnement (connecté)
  ├─ abonné actif ──────► vue de gestion (inchangée)
  └─ non abonné ────────► texte + bouton :
         ├─ has_used_trial → "Me réabonner" ─► /a-propos/abonnement
         └─ sinon           → "M'abonner"   ─► /a-propos/abonnement
```

## Décisions actées

1. **Bouton unique « Je m'abonne »** centré sous les 2 cards de la page publique.
   Les cards deviennent purement informatives (plus de bouton « S'abonner » par card).
2. **Choix du plan par boutons radio dans `mes-infos`** (défaut « simple »), avec
   rappel des tarifs. Aucun plan transporté depuis la card.
3. **URL de la page publique inchangée** : `/a-propos/abonnement` (singulier). Pas de
   renommage ni de redirect.
4. **Cible du bouton conditionnelle à l'état de connexion** (voir détail §2).
5. **`/compte/abonnement` non-abonné** : plus de cards, un bouton « M'abonner » /
   « Me réabonner » selon `has_used_trial(user_id)`.
6. **Signal « déjà abonné » = `has_used_trial`** (True quand un abonnement a atteint
   `trial`/`active`). Un checkout Frisbii abandonné (`pending`/`failed`, aucun accès)
   → considéré « jamais abonné » → « M'abonner ».
7. **Validation d'email = auto-login** puis redirection vers `mes-infos`.
8. **`linkedin_button` paramétrable par `next`** : la connexion garde son
   comportement, l'inscription route vers `mes-infos`.

## Changements par fichier

### 1. `src/pages/a_propos/abonnement.py` — page publique

Devient le foyer unique des composants cards (refactor depuis `compte/abonnement.py`).

- **Remonter** ici (auth-agnostiques) : `_plan_card`, `_plan_cards`, `_explainer`.
  - `_plan_card` : **retirer le bouton « S'abonner » par card**. La carte n'affiche
    plus que label, tarif, description et le badge d'essai générique
    (`trial_days(key)` jours, sans personnalisation `trial_used`).
- `layout()` devient dynamique (appelé par requête, peut lire `current_user`) et
  assemble de haut en bas :
  1. `_plan_cards()` + `_explainer()`
  2. le bouton **« Je m'abonne »** centré (voir §2)
  3. `subscription_terms` (CGU existantes)
- **Contenu** : la sous-section « Fonctionnalités incluses » + `abonnement_features`
  de `subscription_terms` fait désormais doublon avec `_explainer` juste au-dessus.
  → **la retirer de `subscription_terms`** (garder le reste des CGU tel quel).

### 2. Bouton « Je m'abonne » (dans `a_propos/abonnement.py`)

Une fonction dédiée qui décide libellé + cible selon l'état :

| État                               | Libellé                     | Cible                                  |
| ---------------------------------- | --------------------------- | -------------------------------------- |
| `TOUS_ABONNES`                     | « Je m'abonne » (désactivé) | `#` + bannière (comme cards actuelles) |
| non authentifié                    | « Je m'abonne »             | `/inscription`                         |
| authentifié, sans abonnement actif | « Je m'abonne »             | `/compte/abonnement/mes-infos`         |
| authentifié, abonnement actif      | « Gérer mon abonnement »    | `/compte/abonnement`                   |

Bouton centré, `btn btn-primary`, largeur ajustée.

### 3. `src/pages/compte/abonnement.py`

- **Supprimer** `_plan_card`, `_plan_cards`, `_explainer` (déplacés en §1) et l'import
  `from src.pages.a_propos.abonnement import abonnement_features`.
- La branche « non-abonné » (`else` de `layout`, aujourd'hui cards + explainer)
  devient un court texte d'invitation + un bouton :
  - `db.has_used_trial(current_user.id)` → « Me réabonner »
  - sinon → « M'abonner »
  - href → `/a-propos/abonnement` dans les deux cas.
  - Le message « Votre abonnement a expiré » (cas `status == "expired"`) est conservé.
- La vue « abonné actif » (`_active_view`, résiliation, feedback paiement,
  `_salaire_modal`, `_tous_abonnes_banner`) est **inchangée**.

### 4. `src/pages/compte/abonnement_mes_infos.py`

- **Retirer** la redirection « pas de `?plan=` » (lignes 53-55) : la page est
  accessible directement.
- **Ajouter en tête de formulaire** une sélection de formule sous forme de **cartes
  cliquables** (réutilisation de `_plan_card` de la page publique), avec rappel des
  tarifs (20 € HT / 50 € HT). UX voulue : aucune formule sélectionnée par défaut, un
  texte « Choisissez votre formule » invite l'utilisateur ; la carte sélectionnée
  prend un fond légèrement teinté. Mécanisme (le POST du `html.Form` ne soumet
  nativement qu'un champ portant `name`) :
  - deux cartes, chacune enveloppée dans un `html.Div` cliquable
    (`id="plan-card-simple"|"plan-card-soutien"`, `n_clicks`, classe `plan-selectable`) ;
  - un `dcc.Input(type="hidden", id="inf-plan-hidden", name="plan", value="")` — vide
    au départ ; c'est CE champ, natif, qui est soumis (même mécanisme que le champ
    caché `plan` actuel, déjà lu par `subscribe()`) ;
  - un callback sur le `n_clicks` des deux cartes qui écrit la formule dans le champ
    caché, applique la classe `selected` à la carte choisie (retirée de l'autre) et
    masque l'invite ;
  - un texte d'invite `id="inf-plan-invite"` visible tant qu'aucune formule n'est choisie.
- **Style** : ajouter dans `src/assets/css/style.css`
  `.plan-selectable { cursor: pointer }` et
  `.plan-selectable.selected .card { background-color: var(--bs-primary-bg-subtle); border-color: var(--bs-primary) }`.
- **Gating du bouton d'envoi** : `_toggle_submit` exige désormais aussi qu'une formule
  soit sélectionnée (en plus des deux cases rétractation/CGU). Sans plan → désactivé.
- **Remplacer** le `dcc.Input(type="hidden", name="plan", value=plan)` fixe (ligne 232) par le champ caché vide synchronisé ci-dessus.
- Le reste (prefill Frisbii, SIRET, cases rétractation/CGU) est inchangé.
  `subscribe()` lit toujours `request.form.get("plan")` → compatible.

### 5. `src/auth/routes.py` — `verify_email()`

Après `db.set_email_verified(user_id)` :

```python
user = User(db.get_user_by_id(user_id))
login_user(user, remember=True)
return redirect("/compte/abonnement/mes-infos")
```

(`login_user` et `User` sont déjà importés.) La page `/verification-email` reste
utilisée pour le seul cas `error=invalid_token`.

### 6. `src/pages/connexion.py`

- `linkedin_button` accepte un paramètre `next_url` optionnel :

  ```python
  def linkedin_button(next_url: str | None = None):
      href = "/auth/linkedin"
      if next_url:
          href += f"?next={next_url}"
      # ... inchangé
  ```

- Le CTA du bas de `/connexion` (« Créer un compte avec mon adresse email » →
  `/inscription`) devient un lien vers `/a-propos/abonnement` (« Pas encore de
  compte ? Voir les abonnements »).

### 7. `src/pages/inscription.py`

- Appelle `linkedin_button("/compte/abonnement/mes-infos")` pour que l'inscription
  via LinkedIn finisse dans le tunnel (au lieu de `/compte/admin`).
- Le reste (formulaire email, lien « Déjà un compte ? ») inchangé.

## Sécurité

- **Redirection de retour LinkedIn** : `safe_next` (`auth/setup.py:16-19`) n'autorise
  qu'un chemin interne commençant par un seul `/` (rejette `//` et les URLs
  absolues). Le `next=/compte/abonnement/mes-infos` passé par l'inscription est un
  chemin interne valide, filtré à l'entrée (`linkedin_login`) et à la sortie (callback).
  Pas d'open redirect introduit.
- **Auto-login via lien email** : le token de vérification est à usage unique et
  consommé (`consume_verification_token`). L'auto-login qui en découle est un
  magic-link classique, acceptable.

## Cas limites

- **Abandon sur mes-infos** : l'utilisateur a un compte fonctionnel sans abonnement.
  `get_current` renvoie `None`, `has_used_trial` False → `/compte/abonnement` affiche
  « M'abonner ». Cohérent.
- **Ancien abonné (expiré/résilié)** : `has_used_trial` True → « Me réabonner ».
- **Abonné actif visitant `/a-propos/abonnement`** : bouton « Gérer mon abonnement »
  → `/compte/abonnement` (pas de « Je m'abonne » trompeur).
- **`TOUS_ABONNES`** : bouton public désactivé + bannière, comme les cards
  actuelles ; `mes-infos`/`subscribe` déjà gérés en amont.
- **Email déjà pris à l'inscription** : comportement existant (`email_taken`),
  l'utilisateur est invité à se connecter.

## Tests

Étendre `tests/` (Selenium `DashComposite`) :

- Visiteur non connecté : `/a-propos/abonnement` affiche les cards + « Je m'abonne »
  pointant vers `/inscription`.
- Utilisateur connecté sans abonnement : « Je m'abonne » pointe vers `mes-infos` ;
  `/compte/abonnement` affiche « M'abonner ».
- Utilisateur ayant déjà été abonné (`trial_used=1`) : `/compte/abonnement` affiche
  « Me réabonner ».
- `mes-infos` accessible sans `?plan=` ; radios présents, « simple » par défaut ;
  soumission POST envoie bien `plan`.
- `verify_email` : après consommation du token, session authentifiée et redirection
  vers `mes-infos`.
- `safe_next` : `next` externe (`//evil.com`, `https://…`) ignoré au profit du fallback.

## Hors périmètre

- Refonte visuelle des cards / de la page publique (on réutilise l'existant).
- Modification du parcours de paiement Frisbii lui-même.
- Gestion des factures (déjà côté Frisbii, inchangée).
