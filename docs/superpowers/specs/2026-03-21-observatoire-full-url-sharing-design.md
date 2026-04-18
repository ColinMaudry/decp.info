# Observatoire: Full URL Sharing for All Filters

## Problem

The "Partager" button on `/observatoire` currently only encodes `acheteur_id` and `titulaire_id` in the shareable URL. The other 15 filter parameters are lost, so a shared link does not reproduce the sender's filtered view.

## Goal

Extend URL sharing so that **all 17 filter parameters** are encoded in the URL and restored when a recipient opens it. The recipient sees exactly what the sender intended — URL params replace all local filter state.

## Approach

Flat query parameters with short, readable keys. Multi-value filters use repeated keys (native to `urllib.parse`). Only non-default values appear in the URL.

## URL Parameter Mapping

| Component ID                                       | URL key          | Type            | Default (omitted) |
| -------------------------------------------------- | ---------------- | --------------- | ----------------- |
| `dashboard_year`                                   | `annee`          | single          | `None`            |
| `dashboard_acheteur_id`                            | `acheteur_id`    | single          | `None`            |
| `dashboard_acheteur_categorie`                     | `acheteur_cat`   | single          | `None`            |
| `dashboard_acheteur_departement_code`              | `acheteur_dept`  | multi           | `[]`/`None`       |
| `dashboard_titulaire_id`                           | `titulaire_id`   | single          | `None`            |
| `dashboard_titulaire_categorie`                    | `titulaire_cat`  | single          | `None`            |
| `dashboard_titulaire_departement_code`             | `titulaire_dept` | multi           | `[]`/`None`       |
| `dashboard_marche_type`                            | `type`           | single          | `None`            |
| `dashboard_marche_objet`                           | `objet`          | single          | `None`            |
| `dashboard_marche_code_cpv`                        | `cpv`            | single          | `None`            |
| `dashboard_montant_min`                            | `montant_min`    | single (number) | `None`            |
| `dashboard_montant_max`                            | `montant_max`    | single (number) | `None`            |
| `dashboard_marche_techniques`                      | `techniques`     | multi           | `[]`/`None`       |
| `dashboard_marche_innovant`                        | `innovant`       | single          | `"all"`           |
| `dashboard_marche_sousTraitanceDeclaree`           | `sous_traitance` | single          | `"all"`           |
| `dashboard_marche_considerationsSociales`          | `social`         | multi           | `[]`/`None`       |
| `dashboard_marche_considerationsEnvironnementales` | `env`            | multi           | `[]`/`None`       |

Example URL:

```
/observatoire?annee=2024&acheteur_id=12345678901234&acheteur_dept=75&acheteur_dept=13&montant_min=10000&innovant=oui
```

## Data Structure

A list of tuples defines the mapping, used by both callbacks to avoid scattered string literals:

```python
FILTER_PARAMS = [
    # (component_id, url_key, is_multi, default_value)
    ("dashboard_year", "annee", False, None),
    ("dashboard_acheteur_id", "acheteur_id", False, None),
    ("dashboard_acheteur_categorie", "acheteur_cat", False, None),
    ("dashboard_acheteur_departement_code", "acheteur_dept", True, None),
    ("dashboard_titulaire_id", "titulaire_id", False, None),
    ("dashboard_titulaire_categorie", "titulaire_cat", False, None),
    ("dashboard_titulaire_departement_code", "titulaire_dept", True, None),
    ("dashboard_marche_type", "type", False, None),
    ("dashboard_marche_objet", "objet", False, None),
    ("dashboard_marche_code_cpv", "cpv", False, None),
    ("dashboard_montant_min", "montant_min", False, None),
    ("dashboard_montant_max", "montant_max", False, None),
    ("dashboard_marche_techniques", "techniques", True, None),
    ("dashboard_marche_innovant", "innovant", False, "all"),
    ("dashboard_marche_sousTraitanceDeclaree", "sous_traitance", False, "all"),
    ("dashboard_marche_considerationsSociales", "social", True, None),
    ("dashboard_marche_considerationsEnvironnementales", "env", True, None),
]
```

## Callback Changes

### 1. `sync_observatoire_share_url` (line 575)

**Current:** Takes `acheteur_id` and `titulaire_id` as Inputs.

**New:** Takes all 17 filter values as Inputs (same as `udpate_dashboard_cards`). Builds the URL using `FILTER_PARAMS`, skipping default values. Uses `urllib.parse.urlencode(params, doseq=True)` for multi-value params.

### 2. `restore_filters` (line 539)

**Current:** Extracts only `acheteur_id` and `titulaire_id` from URL.

**New:**

- Iterates over `FILTER_PARAMS` to extract all values from `parse_qs`
- For multi-value params: reads the full list from `parse_qs` (returns lists natively)
- For number params (`montant_min`, `montant_max`): casts to `float`
- The guard condition changes from `if acheteur_id or titulaire_id` to "if any URL param is present" — this is necessary so URLs like `?annee=2024&montant_min=10000` (without an ID) work correctly
- When **any** URL param is present: returns explicit values for all 17 outputs — the URL value for params present, `None`/default for params absent. This ensures "URL replaces all" semantics.
- When **no** URL params are present: returns `(no_update,) * 17` (preserving local persistence)
- Radio buttons (`innovant`, `sous_traitance`): value from URL if present, otherwise `"all"` (their default)

### 3. Layout bug fix

Remove the duplicate `dcc.Input(id="observatoire-share-url")` (lines 413-422 — two identical elements).

## Backward Compatibility

Old URLs with only `?acheteur_id=...` or `?titulaire_id=...` continue to work — the new `restore_filters` will read those keys and reset all others to defaults, which is the same effective behavior as before.

Links generated by `add_links()` in `src/utils.py` (used on search results to link to `/observatoire?acheteur_id=...`) are unaffected.

## Test Changes

### Fix broken test `test_010_observatoire_montant_filter`

This test imports `_apply_filters` from `pages.observatoire`, which no longer exists (replaced by `prepare_dashboard_data` in `src/utils.py`). Fix:

- Replace import with `from src.utils import prepare_dashboard_data`
- Update the call to match `prepare_dashboard_data`'s signature: rename `marche_type` keyword to `type`, and add missing params `objet`, `code_cpv`, `techniques`, `marche_innovant`, `sous_traitance_declaree` (all as `None`)

### New test: multi-param URL round-trip

Add a test that navigates to `/observatoire?annee=2024&acheteur_id=<test_id>&montant_min=10000` and verifies that:

- `dashboard_year` dropdown shows "2024"
- `dashboard_acheteur_id` input contains the test ID
- `dashboard_montant_min` input contains "10000"

### Update existing tests

Tests `test_006` and `test_007` validate `acheteur_id` round-trip. These should continue to pass without changes since `acheteur_id` keeps the same URL key.
