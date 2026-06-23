# Défilement horizontal ergonomique des tableaux (#82) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre le défilement horizontal des tableaux toujours accessible (barre miroir en haut, synchronisée) et garder les en-têtes de colonnes visibles pendant le défilement vertical de la page.

**Architecture:** Option B (sticky au niveau page). Le tableau reste dans le flux de la page. CSS rend les en-têtes `position: sticky; top: 0`. Une barre de défilement « miroir » est injectée par JS au-dessus de chaque tableau, sticky en haut, et synchronisée avec le conteneur scrollable du tableau. Aucun scroll vertical imbriqué.

**Tech Stack:** Dash 3.4 `dash_table.DataTable`, CSS (`src/assets/css/style.css`), JS vanilla auto-chargé depuis `src/assets/` (pattern existant : MutationObserver, cf. `dash_clientside.js`), tests Selenium (`dash[testing]` / `DashComposite`).

## Global Constraints

- Importer les modules de l'app avec le préfixe `src.` (ex. `src.figures`), jamais `figures`.
- UI en français.
- Cibler la classe partagée `marches_table` (présente sur les 4 pages : `/tableau`, `/acheteur`, `/titulaire`, `/observatoire`) — pas de duplication par page.
- Ne pas modifier la hauteur du tableau ni introduire de conteneur à hauteur fixe (option A explicitement écartée).
- Les commits référencent `#82`.
- Le pre-commit hook lance `prettier` (CSS/JS/MD) et `ruff` (Python) et **modifie les fichiers** : après un échec dû au reformatage, refaire `git add` puis recommiter.
- Terminer chaque message de commit par : `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

| Fichier                                                                         | Responsabilité                                                                                                                                         | Action   |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| `src/assets/css/style.css`                                                      | En-têtes sticky + neutralisation overflow interne Dash + styles de la barre miroir                                                                     | Modifier |
| `src/assets/table_hscroll.js`                                                   | Injecter la barre miroir au-dessus de chaque `.marches_table`, synchroniser le scroll, masquer si pas de débordement, recalculer au resize / re-render | Créer    |
| `tests/test_tableau_hscroll.py`                                                 | Test Selenium : barre miroir présente + en-tête sticky sur `/tableau`                                                                                  | Créer    |
| `docs/superpowers/specs/2026-06-23-tableaux-scroll-horizontal-sticky-design.md` | Consigner le verdict du spike (Task 1)                                                                                                                 | Modifier |

**Décision DOM clé :** la barre miroir est **injectée par JS** (et non ajoutée dans le markup Python), ce qui évite de toucher au markup des 4 pages et fonctionne quel que soit le wrapper. Le conteneur scrollable du tableau est l'élément Dash `.dash-spreadsheet-container` (ou son parent direct), confirmé au spike.

---

## Task 1 : Spike — vérifier le DOM réel et la technique sticky

**But :** lever l'inconnue principale (structure DOM de DataTable + compatibilité `position: sticky` des en-têtes avec un conteneur `overflow-x`). Produit un verdict écrit qui pilote les tâches suivantes.

**Files:**

- Modify: `docs/superpowers/specs/2026-06-23-tableaux-scroll-horizontal-sticky-design.md` (section « Verdict du spike »)

- [ ] **Step 1 : Lancer l'app**

```bash
source .venv/bin/activate
python run.py
```

Ouvrir `http://127.0.0.1:8050/tableau` dans le navigateur.

- [ ] **Step 2 : Inspecter le DOM du tableau**

Dans les DevTools, sur le tableau, relever et noter :

- l'élément qui porte la **largeur totale** du tableau (table `.cell-table`) et sa largeur (`scrollWidth`) vs. celle de son parent (`clientWidth`) → confirme le débordement ;
- l'élément qui (le cas échéant) porte déjà un `overflow`/`overflow-x` (regarder `.dash-spreadsheet-container`, `.dash-spreadsheet-inner`) via l'onglet _Computed_ ;
- le sélecteur exact de la ligne d'en-tête (attendu : `th.dash-header` dans un `tr`).

- [ ] **Step 3 : Tester l'hypothèse sticky en live**

Dans la console DevTools, appliquer à chaud :

```js
document
  .querySelectorAll(
    ".marches_table .dash-spreadsheet-container, .marches_table .dash-spreadsheet-inner"
  )
  .forEach((e) => (e.style.overflow = "visible"));
document.querySelectorAll(".marches_table th.dash-header").forEach((e) => {
  e.style.position = "sticky";
  e.style.top = "0";
  e.style.zIndex = "10";
  e.style.background = "#fff";
});
```

Scroller verticalement la page → **les en-têtes restent-ils collés en haut ?**

- [ ] **Step 4 : Consigner le verdict**

Ajouter une section « Verdict du spike » à la spec, répondant à :

- sélecteur exact de l'en-tête et du conteneur scrollable ;
- l'astuce `overflow: visible` sur les conteneurs Dash suffit-elle à faire fonctionner le sticky page ? (attendu : oui) ;
- si **non** : noter que les en-têtes sticky devront être pilotés en JS (repositionnement au scroll) — le reste du plan reste valable, seul l'implémentation du sticky de la Task 2 change.

- [ ] **Step 5 : Commit**

```bash
git add docs/superpowers/specs/2026-06-23-tableaux-scroll-horizontal-sticky-design.md
git commit -m "docs: verdict spike DOM tableaux #82

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2 : En-têtes collants (CSS)

**But :** les en-têtes de colonnes restent visibles en haut de la fenêtre pendant le défilement vertical de la page.

**Files:**

- Modify: `src/assets/css/style.css` (ajouter après le bloc `.marches_table.stuck`, vers la ligne 360)

**Interfaces:**

- Consumes: sélecteurs confirmés au spike (Task 1) : `.marches_table th.dash-header`, conteneurs `.dash-spreadsheet-container` / `.dash-spreadsheet-inner`.
- Produces: classe `marches_table` dont les conteneurs Dash internes sont en `overflow: visible` et dont les en-têtes sont sticky — la Task 3 (JS) s'appuie dessus pour poser le conteneur scrollable et la barre miroir.

- [ ] **Step 1 : Écrire le CSS des en-têtes sticky**

Dans `src/assets/css/style.css`, ajouter :

```css
/* ===== Tableaux : en-têtes collants + scroll horizontal (#82) ===== */

/* Neutraliser l'overflow interne de Dash pour que le sticky se cale sur la page */
.marches_table .dash-spreadsheet-container,
.marches_table .dash-spreadsheet-inner {
  overflow: visible !important;
}

/* En-têtes de colonnes collants en haut de la fenêtre */
.marches_table th.dash-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background-color: #fff;
}
```

> Si le verdict du spike indique que le sticky CSS ne tient pas, remplacer ce bloc par le repositionnement JS décrit dans la spec et le porter en Task 3 ; documenter le choix dans le commit.

- [ ] **Step 2 : Vérifier dans le navigateur**

App lancée (`python run.py`), sur `/tableau` : scroller verticalement → l'en-tête reste figé en haut, sur fond opaque, au-dessus des lignes. Vérifier aussi `/acheteur` et `/observatoire`.

- [ ] **Step 3 : Commit**

```bash
git add src/assets/css/style.css
git commit -m "feat(tableaux): en-têtes de colonnes collants #82

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3 : Barre de défilement miroir (JS + CSS)

**But :** une barre de défilement horizontale toujours visible en haut du tableau, synchronisée avec le défilement horizontal du tableau, masquée si le tableau ne déborde pas.

**Files:**

- Create: `src/assets/table_hscroll.js`
- Modify: `src/assets/css/style.css` (styles de `.dt-hscroll`)

**Interfaces:**

- Consumes: les `.marches_table` rendues par Dash ; le conteneur scrollable interne (`.dash-spreadsheet-container`, confirmé au spike) dont on lit `scrollWidth`/`clientWidth` et qu'on pilote via `scrollLeft`.
- Produces: pour chaque `.marches_table`, un nœud `<div class="dt-hscroll">` inséré en première position, contenant `<div class="dt-hscroll-inner">` dont la largeur = largeur totale du tableau.

- [ ] **Step 1 : Écrire le CSS de la barre miroir**

Dans `src/assets/css/style.css`, à la suite du bloc de la Task 2 :

```css
/* Barre de défilement horizontale miroir, collée en haut */
.marches_table .dt-hscroll {
  position: sticky;
  top: 0;
  z-index: 11; /* au-dessus des en-têtes sticky */
  overflow-x: auto;
  overflow-y: hidden;
  height: 14px;
}

.marches_table .dt-hscroll-inner {
  height: 1px;
}

.marches_table .dt-hscroll.is-hidden {
  display: none;
}
```

- [ ] **Step 2 : Écrire le JS de synchronisation**

Créer `src/assets/table_hscroll.js` :

```js
// Barre de défilement horizontale miroir pour les tableaux (.marches_table) — #82
(function () {
  "use strict";

  // Renvoie le conteneur réellement scrollable horizontalement du tableau.
  function getScrollEl(wrapper) {
    return wrapper.querySelector(".dash-spreadsheet-container") || wrapper;
  }

  function setup(wrapper) {
    if (wrapper.dataset.hscrollReady === "1") return;
    const scrollEl = getScrollEl(wrapper);
    if (!scrollEl) return;

    const bar = document.createElement("div");
    bar.className = "dt-hscroll is-hidden";
    const inner = document.createElement("div");
    inner.className = "dt-hscroll-inner";
    bar.appendChild(inner);
    wrapper.insertBefore(bar, wrapper.firstChild);

    let syncing = false;
    const onBar = () => {
      if (syncing) return;
      syncing = true;
      scrollEl.scrollLeft = bar.scrollLeft;
      syncing = false;
    };
    const onTable = () => {
      if (syncing) return;
      syncing = true;
      bar.scrollLeft = scrollEl.scrollLeft;
      syncing = false;
    };
    bar.addEventListener("scroll", onBar);
    scrollEl.addEventListener("scroll", onTable);

    const refresh = () => {
      const total = scrollEl.scrollWidth;
      const visible = scrollEl.clientWidth;
      inner.style.width = total + "px";
      bar.classList.toggle("is-hidden", total <= visible + 1);
      bar.scrollLeft = scrollEl.scrollLeft;
    };

    // Recalcule quand le tableau change (pagination, tri, filtre, données).
    const obs = new MutationObserver(() => refresh());
    obs.observe(scrollEl, { childList: true, subtree: true, attributes: true });
    window.addEventListener("resize", refresh);

    wrapper.dataset.hscrollReady = "1";
    refresh();
  }

  function scan() {
    document.querySelectorAll(".marches_table").forEach(setup);
  }

  // Les tableaux apparaissent après le rendu Dash : observer le body.
  const rootObs = new MutationObserver(() => scan());
  rootObs.observe(document.body, { childList: true, subtree: true });
  scan();
})();
```

- [ ] **Step 3 : Vérifier dans le navigateur**

App lancée, sur `/tableau` : une barre fine apparaît en haut du tableau ; la faire glisser déplace le tableau horizontalement, et inversement. Réduire la fenêtre / élargir → la barre apparaît/disparaît selon le débordement. Changer de page de pagination → la barre se recalcule. Vérifier que `/acheteur`, `/titulaire`, `/observatoire` (tableaux multiples) fonctionnent chacun indépendamment.

- [ ] **Step 4 : Commit**

```bash
git add src/assets/table_hscroll.js src/assets/css/style.css
git commit -m "feat(tableaux): barre de défilement horizontale miroir synchronisée #82

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4 : Test Selenium de non-régression

**But :** garantir que la barre miroir est rendue et que les en-têtes sont sticky, et que rien ne casse le chargement de `/tableau`.

**Files:**

- Create: `tests/test_tableau_hscroll.py`

**Interfaces:**

- Consumes: éléments DOM produits par Task 2 (`th.dash-header` sticky) et Task 3 (`.marches_table .dt-hscroll`).

- [ ] **Step 1 : Écrire le test**

Créer `tests/test_tableau_hscroll.py` (s'aligner sur le style des tests existants dans `tests/`, notamment l'usage de `dash_duo`/`DashComposite` et l'import de l'app) :

```python
from selenium.webdriver.common.by import By


def test_tableau_hscroll_bar_present(dash_duo, start_app):
    """La barre miroir est injectée et l'en-tête est collant sur /tableau."""
    dash_duo.wait_for_element(".marches_table", timeout=20)
    # Barre miroir injectée par table_hscroll.js
    dash_duo.wait_for_element(".marches_table .dt-hscroll", timeout=10)

    header = dash_duo.find_element(".marches_table th.dash-header")
    position = header.value_of_css_property("position")
    assert position == "sticky"
```

> Adapter les fixtures (`dash_duo`, `start_app`, navigation initiale vers `/tableau`) à ce qui existe déjà dans `tests/` : reprendre le mécanisme d'amorçage utilisé par les autres tests (par ex. `tests/test_main.py`) plutôt que d'en inventer un.

- [ ] **Step 2 : Lancer le test et vérifier qu'il échoue si on retire le JS** (sanity)

```bash
rtk pytest tests/test_tableau_hscroll.py -v
```

Expected: PASS avec le JS/CSS en place.

- [ ] **Step 3 : Lancer la suite Selenium impactée**

```bash
rtk pytest tests/test_main.py -v
```

Expected: pas de régression (mêmes résultats qu'avant la branche).

- [ ] **Step 4 : Commit**

```bash
git add tests/test_tableau_hscroll.py
git commit -m "test(tableaux): barre miroir et en-tête sticky sur /tableau #82

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Couverture spec :**

- En-têtes sticky → Task 2. ✓
- Barre miroir synchronisée en haut → Task 3. ✓
- Masquage si pas de débordement → Task 3 (`is-hidden`). ✓
- Recalcul pagination/tri/filtre/resize → Task 3 (MutationObserver + resize). ✓
- Plusieurs tableaux par page → Task 3 (`querySelectorAll` + `dataset.hscrollReady`). ✓
- Contrainte overflow CSS → Task 1 (spike) + Task 2 (`overflow: visible`). ✓
- Portée 4 pages via `marches_table` → ciblage CSS/JS global. ✓
- Validation navigateur + non-régression Selenium → Task 1/2/3 (manuel) + Task 4. ✓

**Placeholders :** les renvois « adapter aux fixtures existantes » de la Task 4 pointent vers `tests/test_main.py` comme référence concrète (les fixtures Selenium du projet ne sont pas réinventées ici à dessein) ; aucun TODO/TBD ailleurs.

**Cohérence des noms :** classes `dt-hscroll` / `dt-hscroll-inner` / `is-hidden` et flag `dataset.hscrollReady` utilisés de façon identique entre CSS (Task 3 step 1) et JS (Task 3 step 2). `marches_table` et `th.dash-header` cohérents entre Task 2 et Task 4.
