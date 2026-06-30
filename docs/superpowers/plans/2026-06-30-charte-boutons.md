# Charte graphique des boutons — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer les couleurs de boutons dérivées du thème Simplex (danger mauve, secondary gris illisible) par une charte à trois rôles — `primary` terracotta, `secondary` gris ardoise, `danger` rouge — où la couleur encode la fonction et le remplissage l'emphase.

**Architecture:** Override CSS ciblant exclusivement les classes `.btn-*` dans `src/assets/css/style.css` (jamais les variables `--bs-*` racine, pour ne pas affecter alertes/badges). Le code applicatif continue d'utiliser `color="primary|secondary|danger"` + `outline=True|False` natifs de dash-bootstrap-components. Puis audit des boutons existants pour conformer leur usage à la charte.

**Tech Stack:** Dash 3.4, dash-bootstrap-components, Bootstrap 5 (thème Simplex), CSS, pytest + Selenium (DashComposite).

## Global Constraints

- Override **uniquement** les sélecteurs `.btn-*` ; ne **jamais** modifier les variables racine `--bs-primary`, `--bs-danger`, `--bs-secondary` (alertes/badges doivent rester inchangés). Source : spec « Hors périmètre ».
- Imports applicatifs toujours préfixés `src.` (ex. `src.pages.recherche`).
- Palette exacte : terracotta `#b33821`, danger rouge `#c0392b`, secondary texte `#344054` / bord `#5a6570`, disabled bord `#ccc` / texte `#666`.
- `border-radius: 3px` et typographie `Inter` poids 400 conservés sur les boutons.
- Focus clavier visible (`:focus-visible`) sur tous les boutons restylés (accessibilité).
- Respecter `prefers-reduced-motion` pour toute transition de survol.
- Tests : `rtk pytest` (Selenium, nécessite Chrome/Chromium). `DEVELOPMENT=true` est positionné automatiquement.

---

### Task 1: Override CSS des trois rôles de boutons

Redéfinit l'apparence des classes `.btn-primary`, `.btn-outline-primary`, `.btn-secondary`, `.btn-outline-secondary`, `.btn-danger`, `.btn-outline-danger` dans la feuille de style applicative, en conservant l'API dbc native. Ajoute un test Selenium de non-régression vérifiant que la feuille est bien appliquée au bouton primaire de la page d'accueil (publique).

**Files:**

- Modify: `src/assets/css/style.css` (bloc « Base Button Styles » autour des lignes 42-79)
- Test: `tests/test_boutons.py` (créer)

**Interfaces:**

- Consumes: rien (première tâche).
- Produces: classes CSS restylées `.btn-primary`, `.btn-outline-primary`, `.btn-secondary`, `.btn-outline-secondary`, `.btn-danger`, `.btn-outline-danger`. Aucun symbole Python.

- [ ] **Step 1: Écrire le test de non-régression (échoue d'abord car couleur cible non garantie)**

Créer `tests/test_boutons.py`. Le bouton « Rechercher » de la page d'accueil (`/`, public, `className="btn btn-primary"` dans `src/pages/recherche.py:56`) doit être rendu terracotta plein (le dégradé existant a `rgb(179, 56, 33)` en couleur médiane → on vérifie une composante rouge dominante et un fond non transparent).

```python
from dash.testing.composite import DashComposite


def _rgb_tuple(css_color: str) -> tuple[int, int, int]:
    """Parse 'rgb(r, g, b)' ou 'rgba(r, g, b, a)' en (r, g, b)."""
    inner = css_color[css_color.index("(") + 1 : css_color.index(")")]
    parts = [p.strip() for p in inner.split(",")]
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def test_btn_primary_is_terracotta(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_element("a.btn.btn-primary, button.btn.btn-primary", timeout=10)
    btn = dash_duo.find_element("a.btn.btn-primary, button.btn.btn-primary")

    # Le dégradé terracotta est posé via background-image ; la couleur de
    # repli background-color ne doit pas être le bleu Bootstrap par défaut.
    bg_image = btn.value_of_css_property("background-image")
    color = btn.value_of_css_property("color")

    assert "gradient" in bg_image  # dégradé terracotta appliqué
    r, g, b = _rgb_tuple(color)
    assert (r, g, b) == (255, 255, 255)  # texte blanc
```

- [ ] **Step 2: Lancer le test pour vérifier l'état initial**

Run: `rtk pytest tests/test_boutons.py::test_btn_primary_is_terracotta -v`
Expected: PASS si le `.btn-primary` actuel s'applique déjà (dégradé + texte blanc déjà présents lignes 51-65). Ce test sert de **garde de non-régression** : il doit rester vert après le refactor CSS. S'il échoue ici, c'est que la feuille n'est pas chargée → investiguer avant de continuer.

- [ ] **Step 3: Réécrire le bloc boutons dans `style.css`**

Remplacer le bloc commenté/partiel « Base Button Styles » (lignes ~42-79 : le commentaire mort, `button.btn.btn-primary, button.show-hide { … }`, son `:hover`, et `button[disabled]`) par la charte complète ci-dessous. Conserver le dégradé terracotta existant pour `.btn-primary` et le `button.show-hide` (qui réutilise ce style).

```css
/* ==========================================================================
   Boutons — charte à 3 rôles (couleur = fonction, remplissage = emphase)
   Voir docs/superpowers/specs/2026-06-30-charte-boutons-design.md
   Override scopé aux classes .btn-* uniquement (n'affecte pas les alertes).
   ========================================================================== */

:root {
  --btn-terracotta: #b33821;
  --btn-terracotta-text: #fff;
  --btn-secondary-text: #344054;
  --btn-secondary-border: #5a6570;
  --btn-secondary-hover-bg: #f1f3f5;
  --btn-danger: #c0392b;
  --btn-danger-text: #fff;
}

/* Base commune : rayon + typo */
.btn {
  border-radius: 3px;
  font-family: "Inter", sans-serif;
  font-weight: 400;
}

/* --- PRIMARY plein : action principale validante (1 par contexte) --- */
button.btn.btn-primary,
a.btn.btn-primary,
button.show-hide {
  display: block;
  outline: 0;
  color: var(--btn-terracotta-text);
  border: 0;
  background-image: linear-gradient(
    rgb(209, 96, 73),
    rgb(179, 56, 33) 26%,
    rgb(159, 36, 22)
  );
}

button.btn.btn-primary:hover,
a.btn.btn-primary:hover,
button.show-hide:hover {
  color: var(--btn-terracotta-text);
  background-image: linear-gradient(
    rgb(239, 126, 103),
    rgb(209, 86, 63) 26%,
    rgb(189, 66, 52)
  );
}

/* --- PRIMARY outline : action affirmative de moindre emphase --- */
.btn.btn-outline-primary {
  color: var(--btn-terracotta);
  border: 1px solid var(--btn-terracotta);
  background-color: transparent;
  background-image: none;
}

.btn.btn-outline-primary:hover,
.btn.btn-outline-primary:focus-visible {
  color: var(--btn-terracotta-text);
  background-color: var(--btn-terracotta);
  border-color: var(--btn-terracotta);
}

/* --- SECONDARY : action neutre / alternative (gris ardoise) --- */
.btn.btn-secondary,
.btn.btn-outline-secondary {
  color: var(--btn-secondary-text);
  border: 1px solid var(--btn-secondary-border);
  background-color: transparent;
  background-image: none;
}

.btn.btn-secondary:hover,
.btn.btn-secondary:focus-visible,
.btn.btn-outline-secondary:hover,
.btn.btn-outline-secondary:focus-visible {
  color: var(--btn-secondary-text);
  background-color: var(--btn-secondary-hover-bg);
  border-color: var(--btn-secondary-border);
}

/* --- DANGER outline : action destructive dans le flux courant --- */
.btn.btn-outline-danger {
  color: var(--btn-danger);
  border: 1px solid var(--btn-danger);
  background-color: transparent;
  background-image: none;
}

.btn.btn-outline-danger:hover,
.btn.btn-outline-danger:focus-visible {
  color: var(--btn-danger-text);
  background-color: var(--btn-danger);
  border-color: var(--btn-danger);
}

/* --- DANGER plein : confirmation finale destructive (modale) --- */
.btn.btn-danger {
  color: var(--btn-danger-text);
  border: 1px solid var(--btn-danger);
  background-color: var(--btn-danger);
  background-image: none;
}

.btn.btn-danger:hover,
.btn.btn-danger:focus-visible {
  color: var(--btn-danger-text);
  background-color: #a93226;
  border-color: #a93226;
}

/* --- État désactivé commun (conserve l'existant) --- */
.btn[disabled],
button[disabled] {
  border-color: #ccc;
  color: #666;
  background-image: none;
}

@media (prefers-reduced-motion: no-preference) {
  .btn {
    transition: background-color 0.15s ease, color 0.15s ease,
      border-color 0.15s ease;
  }
}
```

- [ ] **Step 4: Relancer le test de non-régression**

Run: `rtk pytest tests/test_boutons.py::test_btn_primary_is_terracotta -v`
Expected: PASS (le `.btn-primary` conserve son dégradé terracotta et son texte blanc).

- [ ] **Step 5: Vérifier l'absence de régression sur la suite complète**

Run: `rtk pytest`
Expected: PASS (aucune régression introduite par le CSS).

- [ ] **Step 6: Vérification visuelle des trois rôles**

Lancer l'app (`python run.py`), se connecter, ouvrir `/compte/vues`. Vérifier :

- « Renommer » : gris ardoise lisible (texte `#344054`, bord `#5a6570`), plus de gris clair illisible ;
- « Supprimer » : rouge `#c0392b` en outline, plus aucun mauve ; au survol, plein rouge texte blanc ;
- focus clavier (Tab) : anneau/fond visible sur chaque bouton.
  Prendre une capture pour comparaison avec la capture initiale.

- [ ] **Step 7: Commit** (différé — voir note d'intégration en fin de plan : spec + plan + code committés ensemble)

---

### Task 2: Audit et conformation des boutons existants

Passe en revue les ~46 occurrences `color=…` et 8 `outline=True` pour s'assurer qu'elles respectent la charte : une seule action `primary` pleine par contexte, destructif outline par défaut sauf confirmation finale en modale (plein rouge), neutre en `secondary` outline.

**Files:**

- Inspect: `src/saved_views/ui.py`, `src/pages/compte_vues.py`, `src/pages/compte_abonnement.py`, `src/pages/compte_abonnement_mes_infos.py`, `src/pages/mot_de_passe_oublie.py`, `src/pages/recherche.py`, `src/pages/tableau.py`, `src/app.py`
- Modify: uniquement les fichiers dont un bouton enfreint la charte (à déterminer pendant l'audit)
- Test: `tests/test_boutons.py` (réutilise la garde de non-régression de Task 1)

**Interfaces:**

- Consumes: classes CSS restylées de Task 1.
- Produces: aucun symbole ; usages de boutons conformes à la charte.

- [ ] **Step 1: Recenser les boutons et leur rôle**

Run: `grep -rn 'dbc.Button\|className="btn' src/ --include=*.py`
Pour chaque bouton, noter (page, libellé, `color`, `outline`) et confronter à la charte :

| Cas                                                                                   | Attendu                           |
| ------------------------------------------------------------------------------------- | --------------------------------- |
| Action principale d'un écran/formulaire (Rechercher, Enregistrer, Envoyer, S'abonner) | `color="primary"` plein           |
| Déclencheur destructif dans une liste (Supprimer, Se désabonner)                      | `color="danger", outline=True`    |
| Confirmation destructive finale en modale                                             | `color="danger"` plein            |
| Action neutre (Renommer, Annuler, navigation)                                         | `color="secondary", outline=True` |

Vérifier en particulier : aucun écran ne doit présenter **deux** boutons `primary` pleins en concurrence.

- [ ] **Step 2: Corriger les boutons non conformes**

Éditer uniquement les boutons divergents. Exemple de correction type (n'appliquer que si un cas réel est trouvé) :

```python
# Avant — déclencheur de suppression en plein rouge dans une liste
dbc.Button("Supprimer", id={"type": "vue-delete", "index": vid}, color="danger")
# Après — outline par défaut hors confirmation finale
dbc.Button("Supprimer", id={"type": "vue-delete", "index": vid}, color="danger", outline=True)
```

Si l'audit ne révèle aucune divergence (les usages de `src/saved_views/ui.py` sont déjà conformes : Renommer = `secondary`+outline, Supprimer = `danger`+outline ; la confirmation modale `vue-rename-confirm` = `primary`), documenter « aucun changement nécessaire » dans le message de commit et passer au Step 3.

- [ ] **Step 3: Vérifier la non-régression**

Run: `rtk pytest`
Expected: PASS.

- [ ] **Step 4: Vérification visuelle multi-pages**

Lancer l'app, parcourir `/compte/vues`, `/compte/abonnement`, `/` et `/tableau`. Confirmer que chaque bouton respecte son rôle et qu'il n'y a pas deux `primary` pleins concurrents par écran.

- [ ] **Step 5: Commit** (différé — voir note d'intégration ci-dessous)

---

## Note d'intégration

Sur demande explicite de l'utilisateur, le **spec + le plan + le code** sont
committés **ensemble** (pas de commit intermédiaire). Après validation des deux
tâches, faire un unique commit :

```bash
git add docs/superpowers/specs/2026-06-30-charte-boutons-design.md \
        docs/superpowers/plans/2026-06-30-charte-boutons.md \
        src/assets/css/style.css tests/test_boutons.py
# + tout fichier page modifié pendant l'audit (Task 2)
git commit -m "feat: charte graphique des boutons (primary/secondary/danger) #<issue>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Branche courante : `dev` (auto-déploie sur test.decp.info). Ne pas pousser sans
demande explicite.
