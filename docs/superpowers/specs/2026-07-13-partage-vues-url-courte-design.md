# Partage de vues sauvegardées par URL courte (#112)

**Date :** 2026-07-13
**Issue :** #112 — dépend de #41 (migration AG Grid, DSL d'URL retiré), à articuler avec #97.
**Dépend de :** vues sauvegardées existantes (voir `2026-06-29-vues-sauvegardees-design.md`).

## Contexte

Avec la migration vers AG Grid (#41), on abandonne l'encodage complet d'une vue
(filtres + tris + colonnes) dans l'URL via l'ancien DSL de la DataTable. Pas de
rétro-compatibilité (version majeure).

Le rappel / partage d'une vue repose désormais sur les **vues sauvegardées** (déjà
réservées aux abonnés), référencées par une URL courte. La brique de sauvegarde
existe déjà (`src/saved_views/`, table `saved_views`, application in-page via le
menu déroulant du tableau). Il manque : une URL partageable qui résout et applique
une vue côté serveur, et l'affordance pour récupérer/coller cette URL.

## Décisions de cadrage

- **Créer une vue** : abonnés uniquement (déjà en place, inchangé).
- **Ouvrir une vue par son URL** : **public** — toute personne disposant du lien,
  même non connectée. C'est le sens d'un partage par URL.
- **Anti-énumération** : l'URL n'expose **pas** le `user_id` (séquentiel, devinable)
  et le nom de vue seul n'est **pas** une clé (devinable). La clé réelle est un
  **jeton aléatoire** non devinable.

## Format d'URL

```
https://colibre.fr/tableau?vue=<slug>_<token>
```

- `token` : **6 caractères base62** (`[0-9a-zA-Z]`) générés par `secrets`. ~5,7×10¹⁰
  combinaisons → énumération inutile. C'est l'**identifiant réel et immuable** de la
  vue (clé de lookup, unique globalement).
- `slug` : dérivé du nom de la vue, purement **cosmétique** et **ignoré** à la
  résolution. Régénéré depuis le nom à chaque construction d'URL (le renommage
  d'une vue change le slug mais **pas** le lien, qui reste valide via le jeton).
- Le jeton base62 ne contient jamais de `_`, donc le dernier segment après `rsplit("_", 1)`
  est toujours le jeton. Formes équivalentes qui résolvent la même vue :
  - `?vue=mes_marches_abc123` → jeton `abc123`
  - `?vue=ZZZ_abc123` → jeton `abc123`
  - `?vue=abc123` → jeton `abc123` (slug optionnel)

(Pattern GitHub / Medium / Notion : slug lisible + id qui fait foi.)

## Modèle de données

Une seule colonne ajoutée à `saved_views` :

- **`token TEXT`** — jeton base62(6). Aucune colonne `slug` (recalculé à la volée).
- Unicité : `CREATE UNIQUE INDEX IF NOT EXISTS idx_saved_views_token ON saved_views(token)`.
  (Un index UNIQUE, pas une contrainte de colonne : autorise plusieurs `NULL`
  transitoires pendant le backfill — SQLite traite les NULL comme distincts.)

### Migration

Pattern existant (`src/migrations.py` + `SCHEMA` dans `src/saved_views/db.py`) :

- `_MIGRATIONS += ("0012_add_token_to_saved_views", "ALTER TABLE saved_views ADD COLUMN token TEXT")`
  - Sur DB fraîche : la migration s'exécute **avant** `saved_views_db.init_schema()`
    (ordre dans `app.py` : `init_subscriptions` → `apply_pending` en premier), donc
    « no such table » → toléré par `apply_pending`. La colonne est aussi présente
    dans `SCHEMA`, donc créée par `init_schema`.
  - Sur DB existante : `ADD COLUMN` ajoute la colonne (NULL pour les lignes existantes).
- `SCHEMA` (dans `db.py`) : ajouter `token TEXT` à la définition de table + la création
  de l'index unique.

### Backfill

Le SQL statique ne peut pas générer un aléatoire par ligne. Dans `init_schema()`,
après création/altération : boucle Python sur les lignes `token IS NULL`, attribue
un jeton unique à chacune, `UPDATE`. Idempotent (ne touche que les lignes NULL) →
sans effet aux démarrages suivants.

## Couche d'accès (`src/saved_views/db.py`)

- `generate_token() -> str` : 6 caractères base62 via `secrets.choice`. Regénère en
  cas de collision (extrêmement rare) — la boucle vérifie l'absence en base.
- `upsert(user_id, table_name, name, query)` : à l'**insertion**, génère et stocke un
  jeton. À l'**écrasement** d'une vue existante (`ON CONFLICT(user_id, table_name, name)`),
  le `DO UPDATE SET` ne touche **pas** `token` → le lien reste stable.
- `get_by_token(token) -> Row | None` : lookup public par jeton, **sans** filtre
  `user_id`. Renvoie `None` si inconnu.

## Slugification (`src/saved_views/ui.py` ou util dédié)

`slugify(name) -> str` :

- minuscules,
- accents translittérés (ASCII fold),
- caractères non-alphanumériques → `_`,
- collapse des `_` répétés, trim des `_` en bord.

Purement cosmétique. `build_view_url(name, token) -> str` :
`f"https://{DOMAIN_NAME}/tableau?vue={slugify(name)}_{token}"` (réutilise
`DOMAIN_NAME` de `src/utils/__init__.py`, qui vaut `test.colibre.fr` ou `colibre.fr`).

## Résolution `?vue=` sur `/tableau`

Nouveau callback, `Input("tableau_url", "search")` :

1. Parse le param `vue` ; extrait `token = value.rsplit("_", 1)[-1]`.
2. `get_by_token(token)` :
   - **trouvé** : décode `{ast, columnState}` (même logique que `apply_saved_view`),
     applique `filterModel` + `columnState` + `tableau-hidden-columns`, renseigne le
     store `active_view` `{token, url}` et pose `suppress_next=1` (voir §Dérive).
   - **introuvable / param malformé / vue supprimée** : tableau à l'état par défaut +
     **alerte discrète non bloquante** : « Cette vue est introuvable ou a été
     supprimée. » — **message identique dans tous les cas** (ne confirme pas
     l'existence d'un compte ; anti-énumération, au prix d'un diagnostic moins précis
     pour l'utilisateur légitime).

Aucun contrôle d'abonnement sur ce chemin (ouverture publique).

## UI de partage

### `/tableau`

Sous la barre de boutons (Colonnes, etc.) : un bloc masqué par défaut contenant

- label « URL directe vers cette vue : »,
- un `dcc.Input` **lecture seule** affichant l'URL complète,
- un `dcc.Clipboard` accolé (icône presse-papier, **infobulle au survol**) copiant
  le contenu de l'input.

Affiché **quand une vue vient d'être sauvegardée ou ouverte** (URL ou menu), masqué
**à la première modification** de filtre/tri/colonne.

### `/compte/vues`

- Bouton **« Ouvrir »** existant : pointe désormais vers la vraie URL courte
  (`build_view_url`) au lieu de `/tableau` nu → applique effectivement la vue.
- Ajout d'un **`dcc.Clipboard`** par vue (même composant que `/tableau` : icône +
  infobulle) copiant l'URL courte de la vue. Pas de bouton texte « Copier le lien ».

## Détection de dérive (bloc de partage `/tableau`)

Verrou **« sale » à sens unique**, sans comparaison d'état : c'est le fait de
**changer** un paramètre qui masque la box, pas le fait que l'état diffère. Elle ne
réapparaît pas si l'état revient à celui de la vue.

Écueil : appliquer une vue modifie elle-même `filterModel`/`columnState` (« écho »),
ce qui déclencherait le masquage immédiat. Neutralisé par un drapeau one-shot.

- Stores : `active_view` `{token, url}`, `suppress_next` (compteur).
- **Application/ouverture** (URL ou menu) : renseigne `active_view`, affiche la box,
  pose `suppress_next=1` (modifie la grille → un écho attendu).
- **Sauvegarde** : affiche la box, `suppress_next=0` (ne modifie pas la grille, pas
  d'écho).
- **Callback « changement → masquer »** (Input `filterModel` + `columnState`) : si
  `suppress_next > 0` → le décrémente/consomme et **garde** la box ; sinon → **masque**
  (sens unique).
- **Hypothèse à valider par test** : l'application produit **une seule** invocation
  coalescée de ce callback (Dash regroupe les Inputs `filterModel` + `columnState`
  modifiés dans le même retour de callback). Si AG Grid émet deux mises à jour
  distinctes, `suppress_next` devra valoir 2 à l'application.

## Gating (récapitulatif)

| Action                                      | Contrôle                                  |
| ------------------------------------------- | ----------------------------------------- |
| Sauvegarder / créer une vue                 | Abonné connecté (existant, inchangé)      |
| Menu des vues in-page                       | Abonné connecté (existant, inchangé)      |
| Ouvrir `?vue=<token>`                       | **Public**                                |
| Copier le lien (`/tableau`, `/compte/vues`) | Propriétaire abonné (surfaces déjà gated) |

## Tests

- `slugify` : accents, espaces, casse, caractères spéciaux, collapse/trim.
- `build_view_url` : forme attendue avec `DOMAIN_NAME`.
- Parsing du jeton : `slug_token`, `token` nu, `_` dans le slug, param vide/malformé.
- `generate_token` : longueur/alphabet, unicité (mock collision).
- `get_by_token` : trouvé / inconnu.
- `upsert` : insertion génère un jeton ; écrasement (même nom) **préserve** le jeton.
- Backfill : lignes NULL reçoivent un jeton, idempotence au second appel.
- Résolution : `?vue=<token valide>` applique filtres/colonnes ; `?vue=inexistant`
  et param malformé → état par défaut + alerte (message identique).
- Dérive (E2E léger) : après ouverture/sauvegarde, box visible ; après un changement
  de filtre/tri/colonne, box masquée ; ne réapparaît pas au retour à l'état initial ;
  valider le comportement d'écho (une seule invocation coalescée).

## Hors périmètre (YAGNI)

- Rétro-compatibilité avec l'ancien DSL d'URL (`?filtres=…&tris=…&colonnes=…`).
- Migration automatique des vues pré-AG-Grid (déjà géré : dégradation propre).
- Rate-limiting HTTP sur la résolution (le jeton non devinable suffit ; à revoir si
  besoin avec #97).
- Vues publiques « découvrables » / listées : le partage reste par lien uniquement.
