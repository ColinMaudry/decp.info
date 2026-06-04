# Page `/etapes` — « Quelles données pour quelles étapes et quels seuils ? » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Créer une page statique `/etapes` qui affiche un graphique HTML/CSS montrant quelles données (Approch, Journaux d'annonces légales, BOAMP, JOUE, DECP) sont publiées à chaque étape de la passation d'un marché public et à partir de quel seuil réglementaire.

**Architecture:** Une nouvelle page Dash auto-enregistrée (`src/pages/etapes.py`) qui expose un `layout` composé uniquement de `html.Div`/`dcc.Markdown` (aucun callback, aucune donnée dynamique). La page rend **deux représentations des mêmes données** basculées par media query : sur desktop/tablette, un graphique en grille CSS (1 colonne de libellés + 5 colonnes de seuils) où chaque publication est une barre positionnée en pourcentage ; sur mobile portrait (< 768 px), une liste verticale par étape. Le style vit dans `src/assets/css/style.css` (auto-chargé par Dash). L'URL est ajoutée au sitemap mais pas à la navbar.

**Tech Stack:** Python 3, Dash 3.4 (pages API), CSS (grille + positionnement absolu), Flask (route sitemap existante).

---

## Contexte pour l'engineer (à lire avant de commencer)

- decp.info est une app Dash multi-pages. Chaque page est un module dans `src/pages/` qui appelle `register_page(...)` au niveau du module et expose une variable `layout`. Dash découvre ces pages automatiquement grâce à `use_pages=True` (voir `src/app.py:30`).
- **Imports** : toujours importer les modules de l'app avec le préfixe `src.` (ex. `from src.utils.seo import META_CONTENT`).
- La navbar (`src/app.py:170-182`) est construite à partir d'une **liste blanche de noms** : `["Recherche", "À propos", "Tableau", "Observatoire"]`. Une page dont le `name` n'est pas dans cette liste **n'apparaît pas** dans la navbar. On ne touche donc PAS à la navbar.
- Le sitemap (`src/app.py:70-86`) est une **liste d'URLs codée en dur**. Il faut y ajouter `/etapes`.
- Le CSS personnalisé est dans `src/assets/css/style.css` (Dash charge automatiquement tout ce qui est dans `src/assets/`). On y ajoute les règles du graphique.
- **Pré-requis commit** : ce dépôt utilise `pre-commit` (prettier, ruff). Les hooks ne tournent que si le virtualenv est activé. Avant chaque `git commit`, faire `source .venv/bin/activate` dans la même commande shell. Prettier peut reformater les fichiers Markdown/CSS : si un commit échoue parce que des fichiers ont été modifiés par un hook, refaire `git add` puis `git commit`.
- **Référence visuelle** : la maquette validée est `.superpowers/brainstorm/80498-1780599135/content/chart-concept-v3.html`. Le code HTML/CSS ci-dessous en est la transposition.
- Ce projet n'a **pas** de test automatisé pour cette page (contenu 100 % statique). La vérification est manuelle via `python run.py`. Les tâches ci-dessous remplacent donc le cycle TDD par des vérifications de rendu explicites.

---

## File Structure

- **Create** `src/pages/etapes.py` — la page : `register_page(...)` + `layout`. Contient `build_chart()` (graphique grille desktop), `build_mobile()` (liste verticale mobile, alimentée par la structure `STAGES_MOBILE`) et `build_legend()`, pour garder le `layout` lisible. Responsabilité unique : décrire la page `/etapes`.
- **Modify** `src/app.py` — ajouter `"/etapes"` à la liste `pages` de la fonction `sitemap()`.
- **Modify** `src/assets/css/style.css` — ajouter un bloc de règles préfixées `.etapes-*` : graphique en grille, liste mobile `.etapes-m-*`, et media query de bascule à 768 px.

---

## Task 1 : Squelette de la page `/etapes`

**Files:**

- Create: `src/pages/etapes.py`

- [ ] **Step 1: Créer le fichier avec l'enregistrement de page et un layout minimal**

Créer `src/pages/etapes.py` avec exactement ce contenu (le graphique sera ajouté en Task 2) :

```python
from dash import dcc, html, register_page

from src.utils.seo import META_CONTENT

NAME = "Quelles données pour quelles étapes et quels seuils ?"

register_page(
    __name__,
    path="/etapes",
    title=f"{NAME} | decp.info",
    name="Étapes et données",
    description=(
        "À chaque étape d'un marché public (programmation, publicité, "
        "attribution), quelles données sont publiées et à partir de quel "
        "seuil : DECP, BOAMP, JOUE, journaux d'annonces légales, Approch."
    ),
    image_url=META_CONTENT["image_url"],
)

layout = html.Div(
    className="container",
    children=[
        html.H2(NAME),
        dcc.Markdown(
            "Un marché public passe par plusieurs étapes. À chacune, des "
            "données peuvent être publiées — selon le montant du marché et "
            "des obligations réglementaires. Ce graphique situe les "
            "principales publications de données par **étape** (de haut en "
            "bas) et par **seuil** (de gauche à droite, en euros hors taxes)."
        ),
        # Le graphique sera inséré ici en Task 2
        dcc.Markdown(
            "**À noter :** l'axe horizontal n'est pas linéaire — les seuils "
            "sont espacés régulièrement pour rester lisibles. Les étapes "
            "*Contrat* et *Paiement* n'ont aujourd'hui aucune donnée publiée "
            "en open data.",
            className="etapes-note",
        ),
    ],
)
```

- [ ] **Step 2: Lancer l'app et vérifier que la page se charge**

Run :

```bash
source .venv/bin/activate && python run.py
```

Puis ouvrir `http://127.0.0.1:8050/etapes` dans un navigateur.
Expected : la page affiche le titre « Quelles données pour quelles étapes et quels seuils ? », le paragraphe d'intro et la note, avec le bandeau de navigation en haut. Aucune erreur dans la console du serveur. Arrêter le serveur (Ctrl-C).

- [ ] **Step 3: Vérifier l'absence dans la navbar**

Sur n'importe quelle page, vérifier visuellement que « Étapes et données » **n'apparaît pas** dans la barre de navigation (la liste blanche `src/app.py:181` ne la contient pas).
Expected : la navbar montre uniquement Recherche / Tableau / Observatoire / À propos.

- [ ] **Step 4: Commit**

```bash
source .venv/bin/activate && git add src/pages/etapes.py && git commit -m "feat(etapes): squelette de la page /etapes"
```

(Si le commit échoue car un hook a reformaté le fichier : refaire `git add src/pages/etapes.py && git commit -m "feat(etapes): squelette de la page /etapes"`.)

---

## Task 2 : Le graphique HTML/CSS

**Files:**

- Modify: `src/pages/etapes.py`

Le graphique est une grille de 6 colonnes : 1 colonne de libellés d'étape (150 px) + 5 colonnes de seuils égales. L'en-tête X et chaque ligne d'étape occupent les colonnes 2 → 6 (`grid-column: 2 / -1`). À l'intérieur d'une ligne, les barres sont positionnées en `position:absolute` avec `left`/`right` en pourcentage, où chaque segment de seuil = 20 % de la largeur :

- Segment 1 (0 € → 40 k€) : 0 % – 20 %
- Segment 2 (40 k€ → 90 k€) : 20 % – 40 %
- Segment 3 (90 k€ → 140/216 k€) : 40 % – 60 %
- Segment 4 (140/216 k€ → 5,404 M€) : 60 % – 80 %
- Segment 5 (≥ 5,404 M€) : 80 % – 100 %

Une barre qui « commence à 40 k€ et va jusqu'à l'infini » s'écrit donc `left:20%; right:2%` (les `2%` de marge évitent de coller au bord). Une barre qui remplit la case 90 k€ → seuil formalisé s'écrit `left:40%; right:40%`.

- [ ] **Step 1: Ajouter la fonction `build_chart()` au-dessus de `layout`**

Dans `src/pages/etapes.py`, insérer cette fonction entre le bloc `register_page(...)` et la définition de `layout` :

```python
def _lane(*bars):
    """Une ligne d'étape : fond segmenté en 5 + barres positionnées."""
    return html.Div(
        className="etapes-lane",
        children=[
            html.Div(
                className="etapes-segs",
                children=[html.Div() for _ in range(5)],
            ),
            *bars,
        ],
    )


def _bar(label, color, style):
    base = {"backgroundColor": color}
    base.update(style)
    return html.Div(label, className="etapes-bar", style=base)


def build_chart():
    return html.Div(
        className="etapes-chart-scroll",
        children=html.Div(
            className="etapes-chart",
            children=[
                # En-tête : coin vide + 5 marqueurs de seuils
                html.Div(className="etapes-corner"),
                html.Div(
                    className="etapes-xhead",
                    children=[
                        html.Div("0 €", className="etapes-xcell"),
                        html.Div(
                            [html.Strong("40 000 €"), "seuil DECP"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("90 000 €"), "publicité"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("140 k€ / 216 k€"), "seuils formalisés (UE)"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("5,404 M€"), "travaux (UE)"],
                            className="etapes-xcell",
                        ),
                    ],
                ),
                # Programmation
                html.Div("Programmation", className="etapes-stage"),
                _lane(
                    _bar(
                        "Approch — sourcing / préinformation (non réglementaire)",
                        "#7c5cff",
                        {"left": "2%", "right": "2%"},
                    ),
                ),
                # Publicité (appel d'offres)
                html.Div(
                    ["Publicité ", html.Small("(appel d'offres)")],
                    className="etapes-stage",
                ),
                _lane(
                    _bar(
                        "Journaux d'annonces légales",
                        "#f79009",
                        {"left": "40%", "right": "40%", "top": "6px", "height": "20px"},
                    ),
                    _bar(
                        "BOAMP",
                        "#1570ef",
                        {"left": "40%", "right": "2%", "top": "28px", "height": "20px"},
                    ),
                    _bar(
                        "JOUE — avis de marché",
                        "#0e9384",
                        {"left": "60%", "right": "2%", "top": "6px", "height": "20px"},
                    ),
                ),
                # Attribution
                html.Div("Attribution", className="etapes-stage"),
                _lane(
                    _bar(
                        "DECP — données essentielles",
                        "#12b76a",
                        {"left": "20%", "right": "2%", "top": "6px", "height": "20px"},
                    ),
                    _bar(
                        "JOUE — avis d'attribution",
                        "#0e9384",
                        {"left": "60%", "right": "2%", "top": "28px", "height": "20px"},
                    ),
                ),
                # Contrat (vide)
                html.Div("Contrat", className="etapes-stage"),
                html.Div(
                    "— aucune donnée publiée aujourd'hui —",
                    className="etapes-lane etapes-empty",
                ),
                # Paiement (vide)
                html.Div("Paiement", className="etapes-stage"),
                html.Div(
                    "— aucune donnée publiée aujourd'hui —",
                    className="etapes-lane etapes-empty",
                ),
            ],
        ),
    )


def build_legend():
    items = [
        ("Approch", "#7c5cff"),
        ("Journaux d'annonces légales", "#f79009"),
        ("BOAMP", "#1570ef"),
        ("JOUE", "#0e9384"),
        ("DECP", "#12b76a"),
    ]
    return html.Div(
        className="etapes-legend",
        children=[
            html.Span(
                [
                    html.I(style={"backgroundColor": color}),
                    label,
                ]
            )
            for label, color in items
        ],
    )
```

- [ ] **Step 2: Insérer le graphique et la légende dans `layout`**

Dans `layout`, remplacer la ligne de commentaire `# Le graphique sera inséré ici en Task 2` par :

```python
        build_chart(),
        build_legend(),
```

- [ ] **Step 3: Lancer l'app et vérifier le rendu**

Run :

```bash
source .venv/bin/activate && python run.py
```

Ouvrir `http://127.0.0.1:8050/etapes`.
Expected (comparer à la maquette `.superpowers/brainstorm/80498-1780599135/content/chart-concept-v3.html`) :

- En-tête X : `0 € · 40 000 € (seuil DECP) · 90 000 € (publicité) · 140 k€/216 k€ (seuils formalisés UE) · 5,404 M€ (travaux UE)`.
- Lignes de haut en bas : Programmation (barre Approch pleine largeur), Publicité (Journaux d'annonces légales + BOAMP + JOUE), Attribution (DECP + JOUE), Contrat (vide), Paiement (vide).
- La barre « Journaux d'annonces légales » occupe la case 90 k€ → seuil formalisé ; DECP démarre à 40 k€ ; JOUE et BOAMP démarrent aux bons segments.
- La légende sous le graphique liste les 5 publications avec leurs couleurs.

À ce stade le style brut (couleurs des barres) doit déjà être visible car appliqué inline ; la mise en page de la grille sera finalisée en Task 4. Si la grille n'est pas encore correcte (colonnes non alignées), c'est attendu — continuer. Arrêter le serveur.

- [ ] **Step 4: Commit**

```bash
source .venv/bin/activate && git add src/pages/etapes.py && git commit -m "feat(etapes): graphique données par étape et par seuil"
```

(Si échec dû à un hook : refaire `git add` puis `git commit`.)

---

## Task 3 : Vue mobile (liste verticale par étape)

**Files:**

- Modify: `src/pages/etapes.py`

Sur écran portrait étroit, le graphique en grille n'est pas lisible (vue d'ensemble perdue). On ajoute une **liste verticale par étape** qui décrit les mêmes données en texte. Le basculement entre les deux rendus se fera en CSS (Task 4). Pour éviter la duplication, les publications de chaque étape sont décrites dans une structure de données Python consommée par le rendu mobile.

- [ ] **Step 1: Ajouter la structure de données et `build_mobile()`**

Dans `src/pages/etapes.py`, ajouter ce bloc juste avant la fonction `build_legend()` :

```python
# Données par étape, partagées par la vue mobile.
# Chaque item : (libellé, couleur, plage de seuils en texte).
STAGES_MOBILE = [
    (
        "Programmation",
        [
            ("Approch", "#7c5cff", "tous montants — publication non réglementaire"),
        ],
    ),
    (
        "Publicité (appel d'offres)",
        [
            ("Journaux d'annonces légales", "#f79009", "de 90 000 € au seuil formalisé"),
            ("BOAMP", "#1570ef", "à partir de 90 000 €"),
            (
                "JOUE — avis de marché",
                "#0e9384",
                "à partir des seuils formalisés (140 k€ / 216 k€)",
            ),
        ],
    ),
    (
        "Attribution",
        [
            ("DECP — données essentielles", "#12b76a", "à partir de 40 000 €"),
            ("JOUE — avis d'attribution", "#0e9384", "à partir des seuils formalisés"),
        ],
    ),
    ("Contrat", []),
    ("Paiement", []),
]


def build_mobile():
    blocks = []
    for stage, items in STAGES_MOBILE:
        if items:
            children = [
                html.Div(
                    [
                        html.I(style={"backgroundColor": color}),
                        html.Span(label, className="etapes-m-label"),
                        html.Span(seuil, className="etapes-m-seuil"),
                    ],
                    className="etapes-m-item",
                )
                for label, color, seuil in items
            ]
        else:
            children = [
                html.Div(
                    "aucune donnée publiée aujourd'hui",
                    className="etapes-m-item etapes-m-empty",
                )
            ]
        blocks.append(
            html.Div(
                [html.H4(stage, className="etapes-m-stage"), *children],
                className="etapes-m-block",
            )
        )
    return html.Div(blocks, className="etapes-mobile")
```

- [ ] **Step 2: Insérer `build_mobile()` dans `layout`**

Dans `layout`, la ligne `build_chart(),` (insérée en Task 2) est suivie de `build_mobile(),`, soit :

```python
        build_chart(),
        build_mobile(),
        build_legend(),
```

- [ ] **Step 3: Lancer l'app et vérifier (rendu brut, avant CSS de bascule)**

Run :

```bash
source .venv/bin/activate && python run.py
```

Ouvrir `http://127.0.0.1:8050/etapes`. À ce stade les deux rendus s'affichent l'un sous l'autre (la bascule CSS arrive en Task 4) : sous le graphique, la liste affiche Programmation (Approch…), Publicité (3 publications), Attribution (2 publications), puis Contrat et Paiement avec « aucune donnée publiée aujourd'hui ». C'est attendu. Arrêter le serveur.

- [ ] **Step 4: Commit**

```bash
source .venv/bin/activate && git add src/pages/etapes.py && git commit -m "feat(etapes): vue mobile liste par étape"
```

(Si échec dû à un hook : refaire `git add` puis `git commit`.)

---

## Task 4 : CSS du graphique + bascule mobile

**Files:**

- Modify: `src/assets/css/style.css`

- [ ] **Step 1: Ajouter le bloc CSS à la fin de `src/assets/css/style.css`**

Ajouter à la fin du fichier :

```css
/* ===== Page /etapes : graphique données par étape et par seuil ===== */

.etapes-chart-scroll {
  overflow-x: auto;
  margin: 1rem 0;
}

.etapes-chart {
  min-width: 720px;
  background: #fff;
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  overflow: hidden;
  font-size: 13px;
  display: grid;
  grid-template-columns: 150px repeat(5, 1fr);
}

.etapes-corner {
  border-bottom: 2px solid #344054;
}

.etapes-xhead {
  grid-column: 2 / -1;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  border-bottom: 2px solid #344054;
}

.etapes-xcell {
  text-align: center;
  padding: 6px 2px;
  font-size: 11px;
  color: #475467;
  border-left: 1px dashed #d0d5dd;
}

.etapes-xcell strong {
  display: block;
  color: #101828;
  font-size: 12px;
}

.etapes-stage {
  padding: 14px 10px;
  font-weight: 600;
  color: #101828;
  border-bottom: 1px solid #eaecf0;
  display: flex;
  align-items: center;
}

.etapes-stage small {
  font-weight: 400;
  color: #667085;
}

.etapes-lane {
  grid-column: 2 / -1;
  position: relative;
  border-bottom: 1px solid #eaecf0;
  min-height: 52px;
}

.etapes-segs {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
}

.etapes-segs > div {
  border-left: 1px dashed #eaecf0;
}

.etapes-bar {
  position: absolute;
  top: 9px;
  height: 32px;
  border-radius: 6px;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  padding: 0 10px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  white-space: nowrap;
  overflow: hidden;
}

.etapes-empty {
  color: #98a2b3;
  font-style: italic;
  padding: 14px;
  display: flex;
  align-items: center;
}

.etapes-legend {
  margin-top: 14px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 12px;
}

.etapes-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.etapes-legend i {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  display: inline-block;
}

.etapes-note {
  margin-top: 8px;
  color: #667085;
  font-size: 13px;
}

/* --- Vue mobile (liste par étape) : masquée par défaut --- */

.etapes-mobile {
  display: none;
  margin: 1rem 0;
}

.etapes-m-block {
  border: 1px solid #d0d5dd;
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}

.etapes-m-stage {
  margin: 0;
  padding: 10px 12px;
  background: #f9fafb;
  border-bottom: 1px solid #eaecf0;
  font-size: 15px;
  color: #101828;
}

.etapes-m-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #f2f4f7;
  font-size: 13px;
}

.etapes-m-item:last-child {
  border-bottom: none;
}

.etapes-m-item i {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex: 0 0 auto;
  position: relative;
  top: 2px;
}

.etapes-m-label {
  font-weight: 600;
  color: #101828;
}

.etapes-m-seuil {
  color: #667085;
}

.etapes-m-empty {
  color: #98a2b3;
  font-style: italic;
}

/* --- Bascule desktop / mobile au point de rupture 768 px --- */

@media (max-width: 768px) {
  .etapes-chart-scroll,
  .etapes-legend {
    display: none;
  }
  .etapes-mobile {
    display: block;
  }
}
```

- [ ] **Step 2: Lancer l'app et vérifier le rendu final**

Run :

```bash
source .venv/bin/activate && python run.py
```

Ouvrir `http://127.0.0.1:8050/etapes` en grand écran (≥ 768 px).
Expected : le graphique est identique à la maquette v3 — colonnes alignées, en-tête X avec ligne de séparation foncée, barres colorées bien positionnées dans chaque segment, lignes Contrat/Paiement grisées en italique, légende sous le graphique. La **liste mobile est masquée** (le graphique seul est visible).

- [ ] **Step 3: Vérifier la bascule responsive**

Dans le navigateur, ouvrir les devtools et passer en mode mobile portrait (largeur < 768 px, ex. iPhone SE 375 px). Tester aussi une largeur intermédiaire (~800 px).
Expected :

- À largeur intermédiaire (~800 px, ≥ 768) : le **graphique** s'affiche, défilable horizontalement (`overflow-x:auto` + `min-width:720px`), barres non écrasées ; liste mobile masquée.
- En portrait (< 768 px) : le graphique **et la légende disparaissent**, remplacés par la **liste verticale par étape** — chaque étape est un bloc avec son titre, et chaque publication a sa pastille de couleur, son nom et sa plage de seuils en texte. Aucun défilement horizontal nécessaire. Contrat/Paiement affichent « aucune donnée publiée aujourd'hui » en italique.

Arrêter le serveur.

- [ ] **Step 4: Commit**

```bash
source .venv/bin/activate && git add src/assets/css/style.css && git commit -m "feat(etapes): styles du graphique étapes/seuils"
```

(Si échec dû à un hook prettier : refaire `git add` puis `git commit`.)

---

## Task 5 : Référencement de la page dans le sitemap

**Files:**

- Modify: `src/app.py` (fonction `sitemap()`, ~ligne 73)

- [ ] **Step 1: Ajouter `/etapes` à la liste des URLs du sitemap**

Dans `src/app.py`, dans la fonction `sitemap()`, modifier la liste `pages` :

```python
    pages = [
        "/",
        "/observatoire",
        "/tableau",
        "/a-propos",
        "/etapes",
    ]
```

- [ ] **Step 2: Vérifier le sitemap**

Run :

```bash
source .venv/bin/activate && python run.py
```

Ouvrir `http://127.0.0.1:8050/sitemap.xml`.
Expected : le XML contient désormais une entrée `<loc>https://decp.info/etapes</loc>`. Arrêter le serveur.

- [ ] **Step 3: Commit**

```bash
source .venv/bin/activate && git add src/app.py && git commit -m "feat(etapes): référencement de /etapes dans le sitemap"
```

---

## Vérification finale (checklist de la spec)

- [ ] `/etapes` affiche le graphique fidèle à la maquette v3, avec le bandeau de navigation global en haut.
- [ ] La page est **absente** de la navbar.
- [ ] `/sitemap.xml` **contient** `/etapes`.
- [ ] Sur fenêtre intermédiaire (≥ 768 px), le graphique défile horizontalement sans s'écraser.
- [ ] Sur écran portrait étroit (< 768 px), le graphique est masqué et remplacé par la liste verticale par étape, lisible sans défilement horizontal.
- [ ] Titre H2 de la page = « Quelles données pour quelles étapes et quels seuils ? ».
- [ ] `name` de la page = « Étapes et données ».
