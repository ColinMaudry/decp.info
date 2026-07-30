# Pagination et rendu serveur des pages SEO — design

Issue : [#128](https://github.com/ColinMaudry/colibre/issues/128) — « Paginer les pages SEO d'acheteurs et de départements »

## Problème

`/departements/06` et `/departements/06/<org_id>` affichent des milliers d'entrées
et font planter la page. Mesures sur `decp_prod.parquet` (1,5 M lignes) :

| Page                                         | Entrées sur la page la plus chargée | Pages > 100 entrées                |
| -------------------------------------------- | ----------------------------------- | ---------------------------------- |
| `/departements/<code>` — acheteurs           | 637 (Nord)                          | 98 départements                    |
| `/departements/<code>` — titulaires          | 13 511 (Paris)                      | 104 départements                   |
| `/departements/<code>/<type>/<id>` — marchés | 15 337 (Ville de Paris)             | 3 225 acheteurs + 2 613 titulaires |

Ce sont des volumes **par page**, pas des totaux : la base compte 28 706
acheteurs et 213 299 titulaires, soit 242 005 fiches d'organisme.

`/departements/75` rend donc ~14 000 `<li>` en un seul callback, les deux listes
confondues. La médiane des marchés par acheteur est de 6, le p90 de 118 : c'est
la queue de distribution qui casse, pas le cas courant.

L'exploration a mis au jour trois défauts plus profonds que la taille des pages.

**Aucune page de l'arbre n'est rendue côté serveur.** `/departements/06` sert
10,5 Ko — la coquille Dash, sans `<ul>`. Le contenu vient d'un callback. Ces
pages n'existent que pour les crawlers, et seuls ceux qui exécutent le JS les
voient. Bing et l'essentiel des crawlers IA n'y trouvent rien.

**Les fiches organisme sont faiblement indexables.** Pour
`/acheteurs/21750001600019` (Ville de Paris), le HTML servi contient :

| Signal                       | Valeur servie                                                        | État                             |
| ---------------------------- | -------------------------------------------------------------------- | -------------------------------- |
| `<title>`                    | `Colibre`                                                            | générique sur les 242 005 fiches |
| `meta description`           | « Consultez les marchés publics attribués par cet acheteur. »        | identique partout                |
| `og:title` / `twitter:title` | « Marchés publics attribués par VILLE DE PARIS (MAIRIE) \| colibre » | correct                          |
| corps de page                | rien, pas même le squelette                                          | absent                           |
| JSON-LD organisme            | balise `<script>` vide                                               | posé par callback                |
| `canonical`                  | `href` vide                                                          | posé par JS                      |

Le nom de l'organisme n'atteint donc un crawler sans JS que par `og:title`, une
balise sociale que Google n'utilise pas comme titre de résultat. Or les requêtes
visées sont des noms d'organismes : c'est le `<title>` qui compte.

**La pagination serait incorrecte en l'état.** `liste_marches_org.py:83` n'a pas
d'`ORDER BY`. Sans ordre déterministe, un `LIMIT/OFFSET` peut afficher un même
marché sur deux pages et en omettre un autre.

Enfin, `liste_marches_org.py:67-68` lit `url.split("/")[-2]` et `[-1]` : le
segment `<code>` du département n'est jamais utilisé. `/departements/06/acheteur/X`
et `/departements/99/acheteur/X` rendent la même page.

## Objectif

Rendre explorable sans JavaScript la chaîne qui va du sitemap aux 1,5 M de
fiches marché, et rendre les fiches organisme — les pages à référencer —
réellement indexables sur les requêtes par nom.

## Architecture retenue

Les pages de liste deviennent des **routes Flask rendues côté serveur**, pas des
pages Dash. Ce sont des listes de liens pures : aucune interactivité, aucun
graphique, aucun filtre. Les faire passer par Dash coûte un aller-retour
`_dash-layout` plus un callback, et livre une coquille vide à tout crawler sans
JS. `src/not_found.py` documente déjà que les vraies routes Flask échappent au
catch-all Dash.

Contrepartie assumée : ces pages n'ont ni la navbar Dash ni le comportement SPA.
Elles reprennent le CSS du site et portent un lien de retour vers la fiche
organisme.

### Chaîne d'exploration cible

```
sitemap
 ├→ /departements                              hub, 101 départements × 2 liens
 ├→ /departements/<code>/acheteurs?page=N      SSR, 100/page →   344 pages
 │     ├→ /acheteurs/<id>                      fiche organisme (page à référencer)
 │     └→ /acheteurs/<id>/marches?page=N       SSR, 100/page
 │           └→ /marches/<uid>
 └→ /departements/<code>/titulaires?page=N     SSR, 100/page → 2 190 pages
```

Chaque ligne d'index porte **deux** liens : le nom de l'organisme pointe vers sa
fiche, un lien « liste des marchés » pointe vers `/<type>s/<id>/marches` (page 1,
sans paramètre). Les deux sont nécessaires : la fiche affichera bien un lien vers
sa propre liste pour l'humain, mais ce lien vit dans un callback, donc un crawler
sans JS ne le voit pas. Dans l'autre sens, la liste porte un lien de retour vers
la fiche, ce qui lui donne un lien entrant explorable depuis une page
thématiquement proche.

Ces listes existent pour **tous** les organismes, y compris ceux qui n'ont que
six marchés. Elles restent l'unique chemin explorable vers leurs fiches marché.
Leur `<title>` est distinct (« Les N marchés remportés par X ») pour qu'elles ne
se ressemblent pas toutes.

## Composants

### 1. Listes de marchés par organisme

Routes : `/acheteurs/<org_id>/marches` et `/titulaires/<org_id>/marches`,
page suivante via `?page=N`.

Le paramètre de requête est préféré à un segment (`/marches/page/2`) parce que la
page 1 reste la même URL avec ou sans paramètre, ce qui rend le canonical
trivial. Chaque page paginée porte un canonical **auto-référent** — `?page=2`
pointe sur lui-même, pas sur la page 1 — conformément à la position de Google
depuis l'abandon de `rel=prev/next` comme signal d'indexation.

100 marchés par page : Ville de Paris fait 154 pages, la médiane des organismes
tient sur une seule.

Requête, avec l'`ORDER BY` manquant :

```sql
SELECT uid, objet FROM acheteurs_marches
WHERE acheteur_id = ? ORDER BY uid LIMIT 100 OFFSET ?
```

### 2. Index d'organismes par département

Routes : `/departements`, `/departements/<code>/acheteurs`,
`/departements/<code>/titulaires`, paginées de la même façon.

Chaque ligne affiche le **nombre de marchés** de l'organisme, tri par nombre
décroissant. Deux raisons : sans cet agrégat, 2 190 pages ne contenant qu'une
colonne de raisons sociales se ressemblent toutes et risquent d'être jugées trop
pauvres pour être indexées — or c'est leur fréquence de crawl qui fait vivre le
maillage en dessous. Et le tri décroissant place les organismes importants du
département en page 1, là où le crawl passe le plus souvent.

**Pas de montants.** `/a-propos/donnees` indique que le comptage de marchés est
fiable mais que les agrégats financiers sont faussés par les montants aberrants
(1 €, 1 milliard). Afficher un montant total sur 2 500 pages diffuserait à grande
échelle des chiffres que le site qualifie lui-même de non fiables.

Un chapeau d'une phrase donne le département et le nombre total d'organismes. Le
`<title>` porte le département, le type et le rang de page — « Titulaires de
marchés publics des Alpes-Maritimes (page 2 sur 42) | colibre » — pour que deux
pages d'une même série ne partagent pas le même titre.

**Organismes sans département** — 373 acheteurs et 13 956 titulaires, soit 6,5 %
des titulaires. `WHERE departement_code = ?` ne matche jamais NULL, ils n'ont donc
aujourd'hui aucun chemin. Ils sont servis sous le segment réservé
`/departements/non-renseigne/<type>`.

### 3. Métadonnées rendues côté serveur

| Signal                          | Cause                                                                                                | Correctif                                                                                                                      |
| ------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `<title>` générique             | Dash résout le vrai titre pour `og:title` (`_pages.py:394-396`) mais passe `app.title` à `{%title%}` | surcharger `kwargs["title"]` dans `_interpolate_index_per_request`, avec la même résolution                                    |
| `description` identique partout | les pages déclarent une **chaîne** statique                                                          | Dash résout déjà les descriptions **callables** côté serveur (`_pages.py:398-400`) : en faire des fonctions, comme `get_title` |
| `canonical` posé par JS         | balise vide plus script                                                                              | émettre la balise servie, depuis `request.base_url`                                                                            |
| schéma `http` en production     | nginx envoie `X-Forwarded-Proto`, Flask ne le lit pas                                                | `ProxyFix(x_proto=1, x_host=1)`                                                                                                |

Le dernier point n'est pas cosmétique : sans lui le canonical serait servi en
`http://colibre.fr/...`, pointant toutes les pages vers une URL qui redirige.
C'est déjà le cas de `og:url` aujourd'hui.

`_path_to_page` est une API privée de Dash, mais `not_found.py:20` l'importe déjà
avec un commentaire qui assume le choix et des tests qui l'épinglent. Même
précédent ici, et `_page_meta_tags` prouve que Dash l'utilise lui-même sur le
chemin de requête. La résolution est factorisée dans `src/utils/seo.py` pour que
`not_found.py` et `app.py` partagent un seul point de contact avec cette API.

Les descriptions sont calculées à chaque requête, y compris pour chaque hit de
crawler : elles doivent rester bon marché. Pas de `COUNT` sur les 1,5 M de
lignes — le `nb_marches` matérialisé (composant 4) est réutilisé.

Résultat attendu :

```html
<title>Marchés publics attribués par VILLE DE PARIS (MAIRIE) | colibre</title>
<meta
  name="description"
  content="Les 15 337 marchés publics attribués par VILLE DE PARIS (MAIRIE) : objets, montants, titulaires."
/>
<link rel="canonical" href="https://colibre.fr/acheteurs/21750001600019" />
```

Le JSON-LD organisme reçoit une version minimale servie dans le HTML :

```json
{
  "@context": "https://schema.org",
  "@type": "GovernmentOrganization",
  "name": "VILLE DE PARIS (MAIRIE)",
  "identifier": "21750001600019",
  "url": "https://colibre.fr/acheteurs/21750001600019"
}
```

Le callback existant continue d'enrichir avec l'adresse côté client. Ce n'est pas
le JSON-LD qui motive l'appel à l'Annuaire : `acheteur.py:260` l'exécute déjà
pour le panneau d'infos et le lien « annuaire-entreprises » de la fiche, puis
passe le résultat à `make_org_jsonld(..., annuaire_data=data)` — c'est la raison
d'être du paramètre, documentée dans `seo.py:16-17`. L'adresse est donc obtenue
sans appel supplémentaire. La servir côté serveur exigerait en revanche un appel
HTTP **bloquant** pendant le rendu de chaque page, y compris pour chaque hit de
crawler : c'est cela qu'on évite.

### 4. Données

`db.py:150-169` : les quatre tables matérialisées passent de `SELECT DISTINCT` à
un `GROUP BY` portant `nb_marches`. Elles sont reconstruites au démarrage depuis
le parquet, donc il n'y a rien à migrer.

### 5. Sitemap

`/departements` sort de `NON_INDEXABLE_PREFIXES` dans `src/utils/sitemap.py` : le
commentaire « on met en avant marchés et organismes » devient faux et doit être
retiré.

Un sous-sitemap `/sitemap-arbre.xml` liste `/departements` et les ~2 534 pages
d'index — largement sous la limite de 50 000 URLs par fichier. Cela met les index
à profondeur 0, donc les fiches organisme à 1 et les listes de marchés à 2, au
lieu de 3 et 4 si l'on ne déclarait que `/departements`.

Les listes de marchés n'entrent pas dans le sitemap : elles sont atteignables
depuis les index, et les déclarer doublerait le sitemap sans rien gagner.

Le test-garde `test_sitemap_couvre_toutes_les_pages_publiques` ne couvre que
`dash.page_registry`. Les nouvelles routes étant des routes Flask, elles lui
échappent : leur couverture est vérifiée par des tests dédiés.

### 6. Cache

Les index et les listes sont mémoïsés avec le `cache` existant, clé
`(route, id, page)`, avec le même `timeout=3600 * 24` que les identifiants du
sitemap : les données ne changent qu'à la reconstruction de la base. Les crawlers
tapent les mêmes URLs en rafale.

**`get_annuaire_data` doit être mise en cache** (`src/utils/data.py:16`). Elle
émet aujourd'hui un `get()` brut vers `recherche-entreprises.api.gouv.fr` à
chaque exécution du callback, sans mémoïsation. C'est supportable au trafic
actuel, mais tout l'objet de ce chantier est de faire crawler les 242 005 fiches
organisme — et Googlebot exécute le JS, donc déclenche le callback. On enverrait
des centaines de milliers d'appels non cachés vers une API publique à quota par
IP, avec pour conséquence un throttling et un ralentissement de chaque fiche.
C'est ce chantier qui crée le risque, il porte donc le correctif : un
`@cache.memoize` sur la fonction, les données d'établissement ne bougeant
quasiment jamais.

#### Contrainte du backend actuel, et cible Redis

`CACHE_THRESHOLD` vaut 300 (`app.py:84`). `set()` appelle `_prune()` à chaque
écriture, et `_prune()` déclenche `_remove_older()`, qui supprime les entrées les
plus anciennes jusqu'à repasser sous le seuil. Le cache plafonne donc à ~300
entrées : mémoïser 242 005 SIRET contre ce plafond ne servirait à rien, et
au-delà du seuil chaque écriture provoque un parcours complet du répertoire avec
un `open` sur chaque fichier pour les trier par date.

Correctif retenu **à court terme** : relever `CACHE_THRESHOLD` à 300 000, pilotable
par variable d'environnement. `_over_threshold()` s'appuie sur un compteur
maintenu, donc tant qu'on reste sous le seuil il n'y a aucun parcours de
répertoire. Contreparties assumées : ~242 000 fichiers dans `CACHE_DIR`, effacés
à chaque démarrage par le `rmtree` de `app.py:74` — donc cache froid après chaque
déploiement, et Googlebot rappelle l'API. À vérifier au déploiement : si `/tmp`
est un tmpfs sur le serveur cible, ces fichiers vivent en RAM et `CACHE_DIR` doit
pointer ailleurs.

**Cible** : le backend Redis prévu par [#62](https://github.com/ColinMaudry/colibre/issues/62),
introduit par [#123](https://github.com/ColinMaudry/colibre/issues/123) (limitation
de débit). Le passage se fait par configuration — `CACHE_TYPE` — sans toucher aux
décorateurs `@cache.memoize`, qui sont agnostiques du backend. Rien à prévoir ici
au-delà de ne pas construire de mécanisme concurrent.

À noter pour ces deux issues : le commentaire de #62 justifie Redis par le fait
que `FileSystemCache` donne « un cache distinct par processus ». Ce n'est pas le
cas dans cette configuration — `CACHE_DIR` est un chemin fixe partagé et les noms
de fichiers dérivent d'un hash de la clé, donc les workers partagent le même
cache, avec des écritures atomiques par `os.replace`. Les motifs valables du
passage à Redis sont le plafond d'entrées, la persistance au redémarrage et
l'emplacement du stockage.

## Migration des URLs

| URL actuelle                       | Devenir                                                                                                    |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `/departements/<code>/<type>/<id>` | **301** vers `/<type>s/<id>/marches` — le segment `<code>` était déjà ignoré, la correspondance est exacte |
| `/departements/<code>`             | **301** vers `/departements/<code>/acheteurs`                                                              |
| `/departements`                    | URL conservée, servie par une route Flask au lieu d'une page Dash                                          |

Les trois modules de `src/pages/arbre/` sont supprimés : `/departements` change
d'implémentation, pas d'adresse. Le lien « Marchés par département » de
`mentions_legales.py:154` reste donc valide.

## Cas limites

| Cas                                             | Réponse                    |
| ----------------------------------------------- | -------------------------- |
| organisme inconnu                               | 404                        |
| `?page=0`, `?page=abc`, page au-delà du dernier | 404                        |
| organisme sans aucun marché                     | 200, liste vide et message |
| département inconnu                             | 404                        |

Ces choix sont cohérents avec `sitemap.build_org_page`, qui renvoie déjà 404 hors
limites.

## Tests

| Fichier                                      | Couverture                                                                                                                                                                   |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_seo.py`                          | `<title>` résolu par page dans le HTML servi, descriptions distinctes entre deux organismes, canonical présent et en `https`, JSON-LD servi                                  |
| `tests/seo/test_pages_ssr.py` _(nouveau)_    | 100 entrées par page, bornes (`?page=0`, `abc`, hors limite → 404), organisme sans marché → 200, ordre déterministe, présence des deux liens par ligne, `nb_marches` affiché |
| `tests/seo/test_redirections.py` _(nouveau)_ | `/departements/<code>/<type>/<id>` → 301 vers `/<type>s/<id>/marches`, `/departements/<code>` → 301                                                                          |
| `tests/cache/`                               | `get_annuaire_data` mémoïsée : deux appels pour le même SIRET ne déclenchent qu'une requête HTTP                                                                             |

Le test le plus important est celui de l'ordre déterministe : c'est le défaut que
la pagination introduirait si l'on gardait la requête actuelle. Il est écrit en
TDD, avant l'implémentation — deux pages consécutives, aucun `uid` en commun,
union égale au total.

## Hors périmètre

- Rendu serveur du corps des pages Dash. Seules les métadonnées sont traitées ;
  le contenu des fiches reste rendu côté client.
- JSON-LD enrichi par l'Annuaire des entreprises, qui reste posé par callback.
- Les 373 acheteurs et 13 956 titulaires sans département sont rendus
  explorables, mais la correction de la donnée manquante elle-même relève de
  `decp-processing`.
- Le passage du cache à Redis, qui relève de #123 puis #62. Ce spec se contente
  de relever le seuil du backend fichier et de n'introduire aucun mécanisme de
  cache concurrent.
