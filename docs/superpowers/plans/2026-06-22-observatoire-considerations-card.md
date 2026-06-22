# Tuile « Considérations sociales et environnementales » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter dans `/observatoire`, juste après la tuile « Type d'achat », une tuile montrant via deux barres de progression la part des marchés filtrés comportant au moins une considération sociale (rouge) et au moins une considération environnementale (vert).

**Architecture:** Une fonction pure de calcul (`compute_considerations_stats`) dans `src/figures.py`, testée directement, alimente une fonction de rendu (`get_considerations_card_content`) qui produit un `html.Div` de deux `dbc.Progress`. La tuile est ajoutée dans `_compute_dashboard_children` via le `make_card` existant.

**Tech Stack:** Polars (LazyFrame), Dash / Dash Bootstrap Components (`dbc.Progress`), pytest.

## Global Constraints

- Imports internes toujours préfixés `src.` (ex. `from src.figures import ...`), jamais `figures` ou `utils`.
- Dédoublonnage **par `uid`** : un marché compté une fois (première valeur par `uid`).
- « Au moins une considération » = la valeur de colonne **contient** (insensible casse) `Clause`, `Critère` ou `Marché réservé`. Regex exacte : `(?i)Clause|Critère|Marché réservé`.
- Dénominateur = **tous** les marchés filtrés (uid distincts), y compris `Sans objet` et non renseignés.
- `pct = round(100 * numérateur / dénominateur)` ; si dénominateur = 0 → `pct = 0`.
- Couleurs issues de `px.colors.qualitative.Safe` : sociales = `rgb(204, 102, 119)` (index 1, rouge) ; environnementales = `rgb(17, 119, 51)` (index 3, vert).
- Robustesse : si une colonne `considerations*` est absente du schéma, son `(count, pct)` vaut `(0, 0)` sans exception.

---

### Task 1: Fonction de calcul `compute_considerations_stats`

**Files:**

- Modify: `src/figures.py` (ajouter la fonction après `get_dashboard_summary_table`, ~ ligne 729)
- Test: `tests/test_figures.py` (créer)

**Interfaces:**

- Consumes: rien (fonction pure prenant un `pl.LazyFrame`).
- Produces: `compute_considerations_stats(lff: pl.LazyFrame) -> dict[str, tuple[int, int]]` renvoyant `{"sociales": (count, pct), "environnementales": (count, pct)}` où `count` = nombre de marchés (uid distincts) avec au moins une considération et `pct` = pourcentage entier sur le total des uid distincts.

- [ ] **Step 1: Write the failing test**

Créer `tests/test_figures.py` :

```python
import polars as pl


def _make_lff(rows):
    return pl.LazyFrame(rows)


def test_compute_considerations_stats_basic():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            # uid u1 : social oui (Clause), env non (Sans objet)
            {"uid": "u1", "considerationsSociales": "Clause sociale", "considerationsEnvironnementales": "Sans objet"},
            # uid u2 : social non (Sans objet), env oui (Critère)
            {"uid": "u2", "considerationsSociales": "Sans objet", "considerationsEnvironnementales": "Critère environnemental"},
            # uid u3 : social oui (Marché réservé compte), env null
            {"uid": "u3", "considerationsSociales": "Marché réservé", "considerationsEnvironnementales": None},
            # uid u4 : aucune considération
            {"uid": "u4", "considerationsSociales": "Pas de considération sociale", "considerationsEnvironnementales": "Sans objet"},
        ]
    )

    stats = compute_considerations_stats(lff)

    # 4 marchés au total. Social : u1, u3 -> 2/4 = 50%. Env : u2 -> 1/4 = 25%.
    assert stats["sociales"] == (2, 50)
    assert stats["environnementales"] == (1, 25)


def test_compute_considerations_stats_dedup_per_uid():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            # uid u1 présent 2 fois (2 titulaires) -> compté une seule fois
            {"uid": "u1", "considerationsSociales": "Clause sociale", "considerationsEnvironnementales": "Sans objet"},
            {"uid": "u1", "considerationsSociales": "Clause sociale", "considerationsEnvironnementales": "Sans objet"},
            {"uid": "u2", "considerationsSociales": "Sans objet", "considerationsEnvironnementales": "Sans objet"},
        ]
    )

    stats = compute_considerations_stats(lff)

    # 2 marchés distincts. Social : u1 -> 1/2 = 50%.
    assert stats["sociales"] == (1, 50)
    assert stats["environnementales"] == (0, 0)


def test_compute_considerations_stats_missing_column():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            {"uid": "u1", "considerationsSociales": "Clause sociale"},
            {"uid": "u2", "considerationsSociales": "Sans objet"},
        ]
    )

    stats = compute_considerations_stats(lff)

    # Colonne env absente -> (0, 0) sans exception. Social : 1/2 = 50%.
    assert stats["sociales"] == (1, 50)
    assert stats["environnementales"] == (0, 0)


def test_compute_considerations_stats_empty():
    from src.figures import compute_considerations_stats

    lff = pl.LazyFrame(
        {
            "uid": pl.Series([], dtype=pl.String),
            "considerationsSociales": pl.Series([], dtype=pl.String),
            "considerationsEnvironnementales": pl.Series([], dtype=pl.String),
        }
    )

    stats = compute_considerations_stats(lff)

    assert stats["sociales"] == (0, 0)
    assert stats["environnementales"] == (0, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_figures.py -v`
Expected: FAIL avec `ImportError: cannot import name 'compute_considerations_stats'`.

- [ ] **Step 3: Write minimal implementation**

Dans `src/figures.py`, ajouter après `get_dashboard_summary_table` (avant `make_card`) :

```python
CONSIDERATIONS_REGEX = r"(?i)Clause|Critère|Marché réservé"
CONSIDERATIONS_COLUMNS = {
    "sociales": "considerationsSociales",
    "environnementales": "considerationsEnvironnementales",
}


def compute_considerations_stats(lff: pl.LazyFrame) -> dict[str, tuple[int, int]]:
    """Part des marchés (uid distincts) ayant au moins une considération.

    Renvoie {"sociales": (count, pct), "environnementales": (count, pct)}.
    Dénominateur = tous les uid distincts. Colonne absente -> (0, 0).
    """
    names = lff.collect_schema().names()
    present = {
        key: col for key, col in CONSIDERATIONS_COLUMNS.items() if col in names
    }

    stats = {key: (0, 0) for key in CONSIDERATIONS_COLUMNS}

    if not present:
        return stats

    agg = (
        lff.select(["uid"] + list(present.values()))
        .group_by("uid")
        .agg([pl.col(col).first() for col in present.values()])
        .collect(engine="streaming")
    )

    total = agg.height
    if total == 0:
        return stats

    for key, col in present.items():
        count = agg.filter(
            pl.col(col).str.contains(CONSIDERATIONS_REGEX)
        ).height
        pct = round(100 * count / total)
        stats[key] = (count, pct)

    return stats
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_figures.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/figures.py tests/test_figures.py
git commit -m "feat(observatoire): calcul part marchés avec considération sociale/env

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Rendu de la tuile `get_considerations_card_content`

**Files:**

- Modify: `src/figures.py` (ajouter après `compute_considerations_stats`)
- Test: `tests/test_figures.py` (ajouter au fichier de la Task 1)

**Interfaces:**

- Consumes: `compute_considerations_stats(lff) -> dict[str, tuple[int, int]]` (Task 1) ; `format_number` (déjà importé en tête de `src/figures.py` : `from src.utils.table import add_links, format_number, setup_table_columns`).
- Produces: `get_considerations_card_content(lff: pl.LazyFrame) -> html.Div` : un `html.Div` contenant deux blocs (sociales, environnementales), chacun avec un libellé, un `dbc.Progress` coloré rempli au pourcentage, et le nombre de marchés.

- [ ] **Step 1: Write the failing test**

Ajouter à `tests/test_figures.py` :

```python
def test_get_considerations_card_content_returns_two_progress_bars():
    import dash_bootstrap_components as dbc
    from dash import html

    from src.figures import get_considerations_card_content

    lff = pl.LazyFrame(
        [
            {"uid": "u1", "considerationsSociales": "Clause sociale", "considerationsEnvironnementales": "Sans objet"},
            {"uid": "u2", "considerationsSociales": "Sans objet", "considerationsEnvironnementales": "Critère environnemental"},
        ]
    )

    div = get_considerations_card_content(lff)

    assert isinstance(div, html.Div)

    # Récupère récursivement tous les dbc.Progress
    def find_progress(component, found):
        children = getattr(component, "children", None)
        if isinstance(component, dbc.Progress):
            found.append(component)
        if isinstance(children, (list, tuple)):
            for c in children:
                find_progress(c, found)
        elif children is not None:
            find_progress(children, found)
        return found

    bars = find_progress(div, [])
    assert len(bars) == 2

    # Sociales (rouge) : u1 -> 50%. Environnementales (vert) : u2 -> 50%.
    social_bar, env_bar = bars[0], bars[1]
    assert social_bar.value == 50
    assert social_bar.label == "50 %"
    assert social_bar.style["backgroundColor"] == "rgb(204, 102, 119)"
    assert env_bar.value == 50
    assert env_bar.label == "50 %"
    assert env_bar.style["backgroundColor"] == "rgb(17, 119, 51)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_figures.py::test_get_considerations_card_content_returns_two_progress_bars -v`
Expected: FAIL avec `ImportError: cannot import name 'get_considerations_card_content'`.

- [ ] **Step 3: Write minimal implementation**

Dans `src/figures.py`, ajouter après `compute_considerations_stats` :

```python
CONSIDERATIONS_DISPLAY = [
    # (clé, libellé, couleur Safe)
    ("sociales", "Sociales", "rgb(204, 102, 119)"),
    ("environnementales", "Environnementales", "rgb(17, 119, 51)"),
]


def get_considerations_card_content(lff: pl.LazyFrame) -> html.Div:
    """Deux barres de progression : part des marchés avec considération."""
    stats = compute_considerations_stats(lff)

    blocks = []
    for key, label, color in CONSIDERATIONS_DISPLAY:
        count, pct = stats[key]
        blocks.append(
            html.Div(
                className="mb-3",
                children=[
                    html.Div(
                        className="d-flex justify-content-between",
                        children=[
                            html.Span(label),
                            html.Span(
                                f"{format_number(count)} marchés",
                                className="text-muted",
                            ),
                        ],
                    ),
                    dbc.Progress(
                        value=pct,
                        label=f"{pct} %",
                        style={"backgroundColor": color},
                    ),
                ],
            )
        )

    return html.Div(children=blocks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_figures.py -v`
Expected: tous les tests PASS (5 au total).

- [ ] **Step 5: Commit**

```bash
git add src/figures.py tests/test_figures.py
git commit -m "feat(observatoire): tuile considérations en barres de progression

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Intégration dans l'Observatoire

**Files:**

- Modify: `src/pages/observatoire.py` (import ~ lignes 20-31 ; appel dans `_compute_dashboard_children` après le bloc « Type d'achat », ~ ligne 723)

**Interfaces:**

- Consumes: `get_considerations_card_content(lff) -> html.Div` (Task 2) ; `make_card` (déjà importé).
- Produces: une nouvelle `dbc.Col` (card) insérée dans la liste `cards` entre « Type d'achat » et « Distance acheteur–titulaire ».

- [ ] **Step 1: Ajouter l'import**

Dans `src/pages/observatoire.py`, dans le bloc `from src.figures import (...)` (lignes 20-31), ajouter `get_considerations_card_content` en respectant l'ordre alphabétique existant (après `get_barchart_sources`) :

```python
from src.figures import (
    DataTable,
    get_barchart_sources,
    get_considerations_card_content,
    get_dashboard_summary_table,
    get_distance_histogram,
    get_duplicate_matrix,
    get_geographic_maps,
    get_top_org_table,
    make_card,
    make_column_picker,
    make_donut,
)
```

- [ ] **Step 2: Insérer la tuile après « Type d'achat »**

Dans `_compute_dashboard_children`, juste après le `cards.append(...)` du donut « Type d'achat » (qui se termine ligne ~723) et avant `distance_histogram = ...`, insérer :

```python
    considerations_content = get_considerations_card_content(lff)
    cards.append(
        make_card(
            title="Considérations sociales et environnementales",
            subtitle="part des marchés concernés",
            fig=considerations_content,
        )
    )
```

Le bloc résultant doit ressembler à :

```python
    donut_marche_type = make_donut(lff, "type", per_uid=True, nulls="?")
    cards.append(
        make_card(
            title="Type d'achat",
            subtitle="en nombre de marchés attribués",
            fig=donut_marche_type,
        )
    )

    considerations_content = get_considerations_card_content(lff)
    cards.append(
        make_card(
            title="Considérations sociales et environnementales",
            subtitle="part des marchés concernés",
            fig=considerations_content,
        )
    )

    distance_histogram = get_distance_histogram(lff)
```

- [ ] **Step 3: Vérifier que la page se charge (test d'import/rendu)**

Run: `uv run pytest tests/test_page_loads.py -v`
Expected: PASS (aucune régression sur le chargement des pages). Si `tests/test_page_loads.py` ne couvre pas `/observatoire`, lancer en complément :

Run: `uv run python -c "import src.pages.observatoire"`
Expected: aucune erreur d'import.

- [ ] **Step 4: Lancer l'ensemble de la suite figures + observatoire**

Run: `uv run pytest tests/test_figures.py -v`
Expected: tous PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/observatoire.py
git commit -m "feat(observatoire): afficher la tuile considérations après Type d'achat

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage :**

- Définition « au moins une considération » (regex incl. `Marché réservé`) → Task 1, `CONSIDERATIONS_REGEX`, tests `basic`.
- Dédoublonnage par `uid` → Task 1, test `dedup_per_uid`.
- Dénominateur = tous les marchés filtrés → Task 1 (`total = agg.height`), tests.
- Colonne absente → 0 % → Task 1, test `missing_column` ; cas vide → test `empty`.
- Deux barres `dbc.Progress`, couleurs Safe rouge/vert, labels `XX %` + `N marchés` → Task 2.
- Insertion après « Type d'achat », dimensions par défaut `make_card` → Task 3.
- Hors périmètre (pas de tooltip, pas de filtre) → respecté, rien d'ajouté.

**Placeholder scan :** aucun TODO/TBD ; tout le code est fourni.

**Type consistency :** `compute_considerations_stats` renvoie `dict[str, tuple[int, int]]` clés `sociales`/`environnementales`, consommé tel quel par `get_considerations_card_content` (Task 2) ; `get_considerations_card_content` renvoie `html.Div`, passé à `make_card(fig=...)` (Task 3). Cohérent.
