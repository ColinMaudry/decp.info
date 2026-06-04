# Page `/etapes` — « Quelles données pour quelles étapes et quels seuils ? »

Date : 2026-06-04
Branche : `dev`

## Objectif

Créer une page pédagogique sur decp.info qui montre, sur un seul graphique, **quelles données sont publiées à chaque étape de la passation d'un marché public** et **à partir de quel seuil réglementaire** (en € HT).

La page aide à comprendre l'écosystème des publications de données de la commande publique et à situer les DECP (le cœur de decp.info) parmi les autres sources.

## Portée

- Une page dédiée à l'URL `/etapes`.
- Layout standard (bandeau de navigation global affiché en haut, comme toutes les pages).
- **Non listée** dans la navbar pour l'instant (on ne sait pas encore comment la lier depuis le reste de l'app — elle n'est pas secrète).
- **Référencée** dans le sitemap pour le SEO.
- Graphique en **HTML/CSS statique** (pas de Plotly, pas de SVG, pas d'interactivité).
- Pas de test automatisé spécifique (contenu statique) ; vérification visuelle via `python run.py`.

Hors portée : tout lien entrant depuis la navbar ou d'autres pages, toute interactivité (survol, filtre), toute donnée dynamique.

## Le graphique

### Axes

- **Axe Y** (de haut en bas) — étapes de la passation :
  1. Programmation
  2. Publicité (appel d'offres)
  3. Attribution
  4. Contrat — _vide_ (« aucune donnée publiée aujourd'hui »)
  5. Paiement — _vide_ (« aucune donnée publiée aujourd'hui »)
- **Axe X** — seuils réglementaires en € HT, **segmenté** (espacement égal entre seuils, pas linéaire, sinon tout serait écrasé entre 40 k€ et 5,4 M€). Marqueurs de colonnes :
  - `0 €`
  - `40 000 €` — seuil DECP
  - `90 000 €` — seuil de publicité
  - `140 000 € / 216 000 €` — seuils formalisés (UE)
  - `5 404 000 €` — travaux (UE)

### Barres (publications de données)

Chaque barre est une bande horizontale colorée, positionnée sur sa ligne d'étape et couvrant la plage de seuils où la publication s'applique.

| Publication                     | Étape(s)                                                      | Plage de seuils               | Note                                                                 |
| ------------------------------- | ------------------------------------------------------------- | ----------------------------- | -------------------------------------------------------------------- |
| **Approch**                     | Programmation                                                 | toute la largeur              | sourcing / préinformation, publication **non réglementaire**         |
| **Journaux d'annonces légales** | Publicité                                                     | 90 000 € → seuil formalisé    | remplit exactement cette case                                        |
| **BOAMP**                       | Publicité                                                     | ≥ 90 000 € (jusqu'à l'infini) | au-delà des seuils UE, publicité obligatoire au BOAMP **et** au JOUE |
| **JOUE**                        | Publicité (avis de marché) + Attribution (avis d'attribution) | ≥ seuils formalisés           | deux barres, une par étape                                           |
| **DECP**                        | Attribution                                                   | ≥ 40 000 € (jusqu'à l'infini) | données essentielles de la commande publique                         |

### Légende

Sous le graphique : une pastille de couleur + le nom complet pour chaque publication (Approch, Journaux d'annonces légales, BOAMP, JOUE, DECP).

## Implémentation

### Nouveau fichier `src/pages/etapes.py`

Enregistrement de la page :

```python
register_page(
    __name__,
    path="/etapes",
    title="Quelles données pour quelles étapes et quels seuils ? | decp.info",
    name="Étapes et données",
    description="À chaque étape d'un marché public (programmation, publicité, attribution), quelles données sont publiées et à partir de quel seuil : DECP, BOAMP, JOUE, journaux d'annonces légales, Approch.",
    image_url=META_CONTENT["image_url"],
)
```

Le `name="Étapes et données"` n'est pas dans la liste blanche de la navbar (`src/app.py:181`), la page reste donc hors navigation tout en étant accessible.

`layout` = `html.Div(className="container", children=[...])` :

1. `html.H2("Quelles données pour quelles étapes et quels seuils ?")`
2. Paragraphe d'intro (`dcc.Markdown`) expliquant ce que montre le graphique.
3. Le graphique (composants `html.Div` reproduisant la maquette v3, barres positionnées en `left`/`right` en `%`).
4. La légende.
5. Note de bas (`dcc.Markdown`) : axe X segmenté (non linéaire) ; Contrat et Paiement sans données ouvertes à ce jour.

### Modification de `src/app.py`

Ajouter `"/etapes"` à la liste des URLs du sitemap (`sitemap()`, ~ligne 73) :

```python
pages = [
    "/",
    "/observatoire",
    "/tableau",
    "/a-propos",
    "/etapes",
]
```

Aucune modification de la navbar.

### CSS

Bloc dédié dans `src/assets/css/` (fichier existant ou nouveau), avec classes préfixées (ex. `.etapes-chart`, `.etapes-lane`, `.etapes-bar`…) pour éviter toute collision.

### Responsive — deux rendus

Le graphique en grille n'est pas lisible sur écran portrait étroit (la vue d'ensemble est perdue). On rend donc **deux représentations des mêmes données**, basculées par media query (point de rupture ~768 px) :

- **Desktop / tablette (≥ 768 px)** : le graphique en grille (maquette v3), enveloppé dans un conteneur `overflow-x:auto` + `min-width` pour les écrans intermédiaires. Le rendu mobile est masqué.
- **Mobile (< 768 px)** : le graphique est masqué et remplacé par une **liste verticale par étape**. Chaque étape est un bloc qui liste ses publications, chacune avec sa pastille de couleur, son nom, et sa **plage de seuils en texte** (ex. « DECP — à partir de 40 000 € »). Les étapes Contrat/Paiement affichent « aucune donnée publiée aujourd'hui ».

Pour éviter la duplication, les publications de chaque étape (libellé, couleur, texte de plage) sont décrites **une seule fois** dans une structure de données Python, consommée par le rendu mobile et la légende. Le graphique en grille garde son positionnement explicite (intrinsèquement spatial).

## Vérification

- `python run.py` puis ouvrir `/etapes` : le graphique s'affiche, fidèle à la maquette v3, avec le bandeau de navigation en haut.
- `/etapes` **absente** de la navbar.
- `/sitemap.xml` **contient** `/etapes`.
- Sur fenêtre intermédiaire : défilement horizontal du graphique, pas d'écrasement.
- Sur écran portrait étroit (< 768 px) : le graphique en grille est masqué, remplacé par la liste verticale par étape, lisible sans défilement horizontal.

## Référence

Maquette validée : `.superpowers/brainstorm/80498-1780599135/content/chart-concept-v3.html`.
