# 404 HTTP pour les URLs inconnues (issue #125)

## Problème

Toute URL inconnue renvoie aujourd'hui **200** avec la coquille HTML de Dash
(~10 ko) : `/db`, `/db/decp.csv` (héritées de l'ancien decp.info), `/acheteur`
au singulier, ou n'importe quoi d'autre. Le routage des pages Dash est fait côté
client, et Dash enregistre un catch-all `<path:path>` côté serveur
(`dash/backends/_flask.py:191`) qui sert l'index pour tous les chemins.

Conséquences : les moteurs indexent des URLs mortes, les outils de supervision
ne voient jamais d'erreur, et le visiteur reçoit `html.H1("404 - Page not found")` — le repli anglais brut de Dash (`dash/dash.py:2659`), affiché faute
d'une page nommée `not_found_404` dans le registre.

## Périmètre

**Dans le périmètre** : les chemins qui ne correspondent à aucune page
enregistrée.

**Hors périmètre** : les entités introuvables sur une page à gabarit
(`/marches/uid-inexistant`, `/acheteurs/9999`). Ça imposerait une requête DuckDB
par requête HTTP avant rendu, et de décider du comportement quand la base est
indisponible. À traiter séparément si le besoin se confirme.

## Conception

### Discriminant : la règle Flask appariée

Les requêtes inconnues portent toutes la règle `/<path:path>`, alors que les
routes réelles ont la leur (`/robots.txt` → `/robots.txt`, `/assets/x.css` →
`/assets/<path:filename>`). Vérifié à l'exécution sur l'app.

Un `before_request` qui n'agit **que** sur cette règle laisse donc intacts
`/api/…`, `/_dash-*`, `/_mcp`, `/oauth/*`, `/.well-known/*`, `/assets/*`, les
sitemaps et `robots.txt`, y compris leurs propres 404.

### Correspondance des chemins

Réutilisation de `dash._pages._path_to_page()`, la fonction que Dash utilise
lui-même pour router. C'est la seule façon de garantir qu'on renvoie 404
exactement sur ce que Dash aurait affiché comme introuvable, gabarits compris
(`/marches/<uid>`, `/departements/<code>/<org_type>/<org_id>`).

API privée assumée : les tests épinglent son comportement, donc une montée de
version de Dash qui la déplacerait casse la CI avant déploiement. L'alternative
— réécrire la correspondance sur le `page_registry` public — évite la
dépendance mais diverge silencieusement des règles de Dash (leur regex de
gabarit est `(.*)`, gourmande à travers les `/`).

La page `not_found_404` elle-même est traitée comme inconnue : son URL propre
renvoie 404, pas 200.

### Deux surfaces, deux réponses

| Entrée                                                      | Réponse                                                  |
| ----------------------------------------------------------- | -------------------------------------------------------- |
| Requête HTTP directe (crawler, lien externe, ancienne URL)  | `src/assets/404.html`, statut 404                        |
| Navigation interne dans la SPA (pas d'aller-retour serveur) | `src/pages/not_found_404.py`, rendue par le routeur Dash |

`404.html` reprend la charte de `src/assets/5xx.html` (Bunny Fonts, en-tête avec
logo, carte centrée). `5xx.html` est servie par nginx, configuration hors dépôt ;
`404.html` est servie par l'app, car nginx ne peut pas savoir quels chemins sont
des pages Dash valides. C'est donc une reprise de charte, pas de mécanisme.

Dash reconnaît la page par le **nom de module** `not_found_404`
(`dash/dash.py:2654`), pas par son `path`.

## Fichiers

| Fichier                      | Rôle                                               |
| ---------------------------- | -------------------------------------------------- |
| `src/assets/404.html`        | page statique, charte `5xx.html`                   |
| `src/pages/not_found_404.py` | page Dash pour la navigation interne               |
| `src/not_found.py`           | `init_not_found(server)` + `page_exists(pathname)` |
| `src/app.py`                 | câblage, à côté de `init_auth` / `init_api`        |
| `tests/test_404.py`          | tests                                              |

## Tests

- 404 sur `/db`, `/db/decp.csv`, `/acheteur` (singulier), `/nimportequoi`
- 200 maintenu sur `/`, `/tableau`, `/a-propos/contact`
- 200 maintenu sur les gabarits : `/marches/abc`, `/acheteurs/123`,
  `/departements/44`
- non-régression : `/robots.txt` et `/sitemap.xml` en 200,
  `/assets/inexistant.css` en 404 servi par Dash
- la page `not_found_404` est bien enregistrée sous ce nom de module, sinon Dash
  retombe sur son `H1` anglais
