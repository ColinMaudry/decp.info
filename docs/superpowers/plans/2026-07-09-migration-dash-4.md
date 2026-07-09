# Migration Dash 3.4 → 4.4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire passer l'application de `dash==3.4.0` à Dash 4.4.x sans changement fonctionnel, en acceptant le nouveau style des composants DCC.

**Architecture:** Bump groupé des dépendances de l'écosystème Dash dans un worktree isolé basé sur `dev`, puis on laisse la suite de tests et le smoke test manuel révéler les cassures, qu'on corrige au fil de l'eau. Une seule PR vers `dev`.

**Tech Stack:** Dash 4.4, `uv` (gestion des dépendances), pytest + Selenium (`dash[testing]`), `dash-leaflet` + `dash-extensions` (cartes), `dash-bootstrap-components`.

**Spec de référence:** `docs/superpowers/specs/2026-07-09-migration-dash-4-design.md`

## Global Constraints

- **Base worktree :** créer le worktree depuis `dev` (PAS `origin/main`, qui est en retard sur `dev`).
- **Version cible :** `dash` épinglé en **exact** sur la dernière 4.4.x (style d'épinglage existant `dash==3.4.0`).
- **DataTable reste :** ne PAS toucher aux `dash_table.DataTable` ni à `src/figures.py`/`src/utils/table_sql.py` (relève de #41).
- **Régressions visuelles :** accepter le look Dash 4 ; ne corriger que les cassures fonctionnelles ; **retirer** le CSS custom en conflit plutôt que le patcher.
- **Bump libs tierces :** seulement si la compat Dash 4 l'exige.
- **Tests :** toujours via `uv run pytest` (l'activation du venv dans le shell n'est pas fiable ici).
- **Avant chaque commit :** exécuter `pre-commit` (ruff + prettier) — cf. CLAUDE.md.
- **Imports :** modules de l'app toujours préfixés `src.` (ne pas régresser vers `utils.`/`pages.`).

---

### Task 1: Bump Dash et résoudre les dépendances (portail de compat)

C'est le portail de risque : la résolution `uv` et le démarrage de l'app révèlent immédiatement toute incompatibilité de `dash-leaflet` / `dash-extensions` / `dbc` avec Dash 4.

**Files:**

- Modify: `pyproject.toml` (bloc `dependencies` et groupe `dev`)
- Modify: `uv.lock` (régénéré par `uv`)

**Interfaces:**

- Produces: environnement résolu sur Dash 4.4.x avec l'app qui démarre. Les tâches suivantes s'appuient sur cet état.

- [ ] **Step 1: Déterminer la dernière version 4.4.x**

Run: `uv run python -c "import urllib.request, json; d=json.load(urllib.request.urlopen('https://pypi.org/pypi/dash/json')); print([v for v in d['releases'] if v.startswith('4.4.')][-1])"`
Expected: une version type `4.4.x`. Noter cette valeur (ci-après `<DASH_VERSION>`).

- [ ] **Step 2: Consolider la déclaration `dash` dans `pyproject.toml`**

Dans le bloc `dependencies`, remplacer les DEUX lignes actuelles :

```toml
  "dash==3.4.0",
  "dash[compress]",
```

par une seule ligne épinglée :

```toml
  "dash[compress]==<DASH_VERSION>",
```

Dans le groupe `[dependency-groups].dev`, remplacer :

```toml
  "dash[testing]",
```

par :

```toml
  "dash[testing]==<DASH_VERSION>",
```

- [ ] **Step 3: Résoudre l'environnement**

Run: `uv sync`
Expected: résolution réussie. **Si** échec de résolution mentionnant `dash-leaflet`, `dash-extensions` ou `dash-bootstrap-components` (peer-deps React/Dash) : bumper la lib en cause vers sa dernière version (`uv add 'dash-leaflet@latest'` et/ou `uv add 'dash-extensions@latest'`) puis relancer `uv sync`.

- [ ] **Step 4: Vérifier l'import et la version**

Run: `uv run python -c "import dash, dash_leaflet, dash_extensions, dash_bootstrap_components as dbc; print(dash.__version__, dash_leaflet.__version__, dash_extensions.__version__, dbc.__version__)"`
Expected: `dash.__version__` commence par `4.4`, aucun ImportError.

- [ ] **Step 5: Vérifier le démarrage de l'app**

Run: `DEVELOPMENT=true uv run run.py` puis attendre le log de démarrage et arrêter (Ctrl-C).
Expected: l'app démarre sans traceback (le serveur écoute). Un warning de dépréciation sur `DataTable` est attendu et normal.

- [ ] **Step 6: Commit**

```bash
pre-commit run --files pyproject.toml || true
git add pyproject.toml uv.lock
git commit -m "build: bump dash 3.4 -> 4.4 et résolution des dépendances (#101)"
```

---

### Task 2: Rendre la suite de tests verte sur Dash 4

Le restyling DCC de Dash 4 peut casser des sélecteurs Selenium (classes CSS changées) ou des assertions. On fait passer toute la suite.

**Files:**

- Modify: fichiers de `tests/` dont les assertions/sélecteurs cassent (inconnus a priori)

**Interfaces:**

- Consumes: environnement Dash 4.4 de la Task 1.
- Produces: `uv run pytest` intégralement vert.

- [ ] **Step 1: Lancer la suite complète pour cartographier les cassures**

Run: `uv run pytest`
Expected: soit tout vert (idéal → aller directement au Step 4), soit des échecs. Noter chaque test en échec et sa cause (sélecteur introuvable, timeout, assertion).

- [ ] **Step 2: Corriger chaque test en échec**

Pour chaque échec, appliquer la correction minimale :

- **Sélecteur Selenium cassé** (une classe/structure DCC a changé en Dash 4) : mettre à jour le sélecteur pour cibler la nouvelle structure rendue. Inspecter le DOM réel via `DEVELOPMENT=true uv run run.py` si besoin.
- **Assertion sur du texte/markup restylé** : ajuster l'attendu à la sortie Dash 4.
- **Ne PAS** contourner un échec qui révèle une vraie régression fonctionnelle : le noter pour la Task 3/4.

- [ ] **Step 3: Relancer les tests corrigés**

Run: `uv run pytest <chemins des tests précédemment en échec>`
Expected: PASS pour les tests corrigés.

- [ ] **Step 4: Confirmer la suite complète**

Run: `uv run pytest`
Expected: intégralement vert.

- [ ] **Step 5: Commit**

```bash
pre-commit run --files <fichiers de test modifiés> || true
git add tests/
git commit -m "test: adapter la suite au rendu Dash 4 (#101)"
```

Si aucun test n'a nécessité de modification, ne pas créer de commit vide — passer directement à la Task 3.

---

### Task 3: Vérifier le comportement des Dropdown et nettoyer le CSS en conflit

Dash 4 change deux défauts de `dcc.Dropdown` (`optionHeight='auto'`, `closeOnSelect=False` en multi-select) et restyle les DCC. On vérifie les 11 Dropdown et on retire les overrides CSS devenus inutiles/cassants.

**Files:**

- Modify (si nécessaire) : `src/pages/recherche.py`, `src/pages/tableau.py`, et autres pages contenant des `dcc.Dropdown`
- Modify: `src/assets/css/style.css` (et autres fichiers de `src/assets/css/`) — retrait des overrides en conflit

**Interfaces:**

- Consumes: environnement Dash 4.4, suite verte (Tasks 1-2).
- Produces: Dropdown fonctionnels, CSS sans override cassant.

- [ ] **Step 1: Lister les Dropdown et repérer ceux en multi-select**

Run: `grep -rn "dcc.Dropdown" src/ | grep -v __pycache__`
Puis pour le contexte multi : `grep -rn "multi=True" src/ | grep -v __pycache__`
Expected: la liste des 11 emplacements ; identifier ceux en `multi=True` (impactés par le changement `closeOnSelect`).

- [ ] **Step 2: Vérifier visuellement les Dropdown impactés**

Run: `DEVELOPMENT=true uv run run.py` et ouvrir les pages concernées (notamment `/` recherche et `/tableau` filtres/sélecteur de colonnes).
Expected: les Dropdown s'ouvrent, filtrent, et se ferment correctement. Un multi-select qui reste ouvert après sélection est le nouveau défaut Dash 4 — **acceptable** (ne pas corriger sauf si réellement cassé). Ne corriger (ex. forcer `optionHeight` numérique) que si l'affichage est rompu.

- [ ] **Step 3: Repérer les overrides CSS en conflit avec le restyling DCC**

Run: `grep -rn "Select\|dropdown\|Checklist\|RadioItems\|dash-loading\|input" src/assets/css/`
Expected: liste des règles ciblant les DCC. Pour chacune, juger via le rendu (Step 2) si elle entre en conflit avec le nouveau style Dash 4.

- [ ] **Step 4: Retirer les overrides devenus inutiles ou cassants**

Supprimer (pas commenter) les règles CSS qui cassent ou déforment un composant DCC restylé. Conserver celles qui restent utiles et sans conflit. Ne PAS toucher au bloc CSS lié à `dash_table`/DataTable (hors périmètre, cf. `style.css:512`).

- [ ] **Step 5: Re-vérifier le rendu après nettoyage**

Run: `DEVELOPMENT=true uv run run.py` et re-parcourir les pages modifiées.
Expected: aucun composant cassé ; le rendu adopte le style Dash 4.

- [ ] **Step 6: Commit**

```bash
pre-commit run --files <fichiers modifiés> || true
git add src/
git commit -m "style: accepter le rendu DCC Dash 4 et retirer le CSS en conflit (#101)"
```

Si aucune modification n'a été nécessaire, ne pas créer de commit vide.

---

### Task 4: Smoke test complet et ouverture de la PR

Vérification finale (definition of done) : suite verte + parcours manuel des 6 pages + cartes Leaflet + exports.

**Files:** aucun a priori (corrections de dernière minute possibles selon findings).

**Interfaces:**

- Consumes: état des Tasks 1-3.
- Produces: PR vers `dev`.

- [ ] **Step 1: Suite de tests finale**

Run: `uv run pytest`
Expected: intégralement vert.

- [ ] **Step 2: Smoke test manuel des 6 pages**

Run: `DEVELOPMENT=true uv run run.py` et parcourir : `/` (recherche), `/acheteur`, `/titulaire`, `/tableau`, `/marche`, `/observatoire`.
Expected: chaque page se charge sans erreur console/serveur ; les tableaux DataTable s'affichent et filtrent ; les graphiques Plotly s'affichent.

- [ ] **Step 3: Vérifier spécifiquement les cartes Leaflet et le clustering**

Sur `/acheteur` et `/titulaire` (pages avec cartes), vérifier que la carte Leaflet s'affiche et que le clustering de marqueurs fonctionne (zoom/dézoom regroupe/éclate les marqueurs).
Expected: cartes rendues et interactives. **Si cassé** : bumper `dash-leaflet`/`dash-extensions` (cf. Task 1 Step 3), re-`uv sync`, re-tester, et amender le commit de la Task 1.

- [ ] **Step 4: Vérifier les exports**

Depuis `/tableau`, déclencher un export xlsx et un export csv.
Expected: fichiers téléchargés et ouvrables, contenu cohérent.

- [ ] **Step 5: Corriger les cassures résiduelles éventuelles**

Pour toute cassure trouvée aux Steps 2-4, appliquer la correction minimale et commiter séparément :

```bash
pre-commit run --files <fichiers> || true
git add <fichiers>
git commit -m "fix: <cassure corrigée> sur Dash 4 (#101)"
```

- [ ] **Step 6: Ouvrir la PR vers `dev`**

```bash
git push -u origin <branche-worktree>
gh pr create --base dev --title "Migration Dash 3.4 → 4.4 (#101)" --body "$(cat <<'EOF'
Migration de `dash==3.4.0` vers Dash 4.4.x (pure montée de version, cf. spec `docs/superpowers/specs/2026-07-09-migration-dash-4-design.md`).

## Périmètre
- Bump `dash` + libs écosystème si nécessaire
- Acceptation du look DCC Dash 4, retrait du CSS en conflit
- DataTable inchangées (→ #41), MCP hors périmètre (→ #111)

## Vérification
- `uv run pytest` vert
- Smoke manuel : 6 pages + cartes Leaflet + exports xlsx/csv

Closes #101

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR créée vers `dev`. Le merge déclenchera l'auto-deploy vers test.colibre.fr.

---

## Notes d'exécution

- La migration est **réactive** : les Tasks 2-4 corrigent ce que le bump casse. Si le bump ne casse rien (plausible vu que les ruptures Dash 3.0 sont déjà absorbées), plusieurs tasks se réduisent à leur étape de vérification, sans commit.
- Le point de bascule risqué est concentré dans la Task 1 (résolution/boot) et la Task 4 Step 3 (cartes). En cas de blocage dur d'une lib tierce sans release Dash 4 : arrêter et réévaluer avec le mainteneur du plan.
