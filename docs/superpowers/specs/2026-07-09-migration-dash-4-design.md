# Migration Dash 3.4 → 4.4 — Design (#101)

> Statut : design validé le 2026-07-09. Prêt pour le plan d'implémentation.
> Issues liées : #101 (cette migration), #41 (AG Grid, suite), #111 (serveur MCP, nécessite Dash ≥ 4.3).

## 1. Objectif & périmètre

Monter la dépendance `dash` de **3.4.0 à 4.4.x**, sans changement fonctionnel de l'application.

**Dans le périmètre :**

- Consolidation et bump de la déclaration `dash` dans `pyproject.toml`.
- Validation et, si nécessaire, bump des libs de l'écosystème Dash (`dash-leaflet`, `dash-extensions`, `dash[testing]`).
- Acceptation du nouveau style des composants DCC de Dash 4 ; retrait du CSS custom qui entre en conflit.
- Corrections des cassures fonctionnelles éventuelles.

**Hors périmètre (issues dédiées) :**

- Migration DataTable → AG Grid → **#41**. Les `dash_table.DataTable` restent en place. Elles sont dépréciées mais fonctionnelles en Dash 4.x (retrait prévu seulement en Dash 5.0).
- Serveur MCP des données sous auth → **#111** (nécessite Dash ≥ 4.3, donc cette migration en est le prérequis).
- Toute nouvelle fonctionnalité tirant parti de Dash 4.

## 2. Contexte technique constaté

- `pyproject.toml` déclare `dash` de façon dédoublée : `"dash==3.4.0"` **et** `"dash[compress]"` (non épinglé). À consolider.
- Version installée : `dash` 3.4.0, `dash-bootstrap-components` 2.0.4, `dash-leaflet` 1.1.3, `dash-extensions` 2.0.5.
- **Aucun** usage de `run_server`, `long_callback`, `LogoutButton`, `_set_react_version` dans `src/` ni `run.py` → les ruptures Dash 3.0 sont déjà absorbées. React 18.3.1 est déjà le défaut depuis Dash 3.
- Composants DCC utilisés que Dash 4 restyle : `dcc.Dropdown` (×11, filtres et sélecteurs de colonnes), `dcc.Input` (×23), `dcc.Loading` (×5), `dcc.Checklist` (×2), `dcc.RadioItems` (×1). Pas de `Slider`, `DatePicker`, `Tabs`, `TextArea` → surface visuelle limitée.
- `DataTable` est utilisé dans `recherche`, `tableau`, `acheteur`, `titulaire`, `observatoire`, `admin/liste`, et sous-classé dans `src/figures.py` (`class DataTable(dash_table.DataTable)`). `src/utils/table_sql.py` traduit le DSL de filtre DataTable en SQL DuckDB. Tout cela reste inchangé (relève de #41).

## 3. Décisions de design

- **Régressions visuelles : accepter le look Dash 4.** On ne corrige que les cassures fonctionnelles (débordement, illisibilité, comportement rompu). Le CSS custom qui entre en conflit avec le restyling DCC est **retiré** plutôt que patché.
- **Épinglage :** pin exact sur la dernière 4.4.x, cohérent avec le style actuel (`dash==3.4.0`). Ligne consolidée en `"dash[compress]==4.4.x"`.
- **Bump des libs tierces : seulement si nécessaire.** On ne monte `dash-leaflet` / `dash-extensions` que si la compat Dash 4 l'exige.
- **Approche de séquencement : bump groupé (A), dans un worktree isolé basé sur `dev`.** Une seule PR. Justifié par le périmètre contenu et l'absence de ruptures majeures.

## 4. Étapes d'implémentation (haut niveau)

Le détail sera produit par le skill `writing-plans`. Séquence prévue :

1. **Validation de compat (premier, car seul vrai risque).** Dans le worktree : consolider/bumper `dash` dans `pyproject.toml`, `uv sync`, `uv run run.py`. Observer la résolution des dépendances et le démarrage. Point le plus à risque : les cartes **Leaflet** (`dash-leaflet` + clustering via `dash-extensions`). Bumper ces libs si cassées.
   - Si un blocage dur apparaît (lib tierce sans release compatible Dash 4), **arrêt et réévaluation** avant d'aller plus loin.
2. **Corrections fonctionnelles.** Vérifier les 11 `dcc.Dropdown` face aux nouveaux défauts Dash 4 (`optionHeight='auto'`, `closeOnSelect` distinct en multi-select) ; corriger uniquement si comportement cassé.
3. **Nettoyage CSS.** Retirer de `src/assets/css/` les overrides devenus inutiles ou cassants suite au restyling DCC.
4. **Alignement `dash[testing]`** sur la même version dans le groupe `dev`.

## 5. Vérification (definition of done)

- `pre-commit` exécuté (ruff) avant tout `git add` / commit (cf. CLAUDE.md).
- `uv run pytest` vert (suite pytest/Selenium, nécessite Chrome/Chromium).
- `uv run run.py` démarre l'app sans erreur.
- Smoke test manuel local des 6 pages principales : `/`, `/acheteur`, `/titulaire`, `/tableau`, `/marche`, `/observatoire`, **plus** cartes Leaflet et exports (xlsx/csv).

## 6. Livraison

- Worktree isolé basé sur `dev` → une PR vers `dev`.
- Le merge dans `dev` déclenche l'auto-deploy vers **test.colibre.fr** (validation en conditions réelles = bonus, hors DoD strict).

## 7. Risques & mitigations

| Risque                                                  | Mitigation                                                                         |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `dash-leaflet` / `dash-extensions` incompatibles Dash 4 | Étape 1 le révèle tôt ; bump ciblé ; blocage dur → réévaluation avant de continuer |
| Régressions des cartes non couvertes par les tests      | Smoke manuel explicite dans la DoD (cartes Leaflet)                                |
| CSS custom cassant un composant DCC restylé             | Retrait de l'override plutôt que patch                                             |
| Conflits de peer-dependencies (React/Dash) à `uv sync`  | Détectés à l'étape 1 ; résolus par alignement des versions écosystème              |
