# Observatoire Link from Search & Tableau Results

## Problem

Users searching for an organization (acheteur or titulaire) on the search page or browsing the tableau cannot jump directly to the observatoire page filtered for that organization. They must manually navigate and re-enter the identifier.

## Solution

Extend `add_links()` in `src/utils.py` to append an observatoire link (📊 emoji) to `_nom` columns, and add bidirectional URL parameter sync to the observatoire page.

## Changes

### 1. `src/utils.py` — `add_links()` modification

The existing `add_links()` loop iterates over `["uid", "acheteur_nom", "titulaire_nom", "acheteur_id", "titulaire_id"]`. The `if col.startswith("acheteur_")` and `if col.startswith("titulaire_")` blocks match both `_nom` and `_id` columns. The observatoire link must only be appended to `_nom` columns, so it must be gated on `col == "acheteur_nom"` or `col == "titulaire_nom"` explicitly.

For `acheteur_nom`, append an observatoire link after the existing detail page link:

```
Before: <a href="/acheteurs/12345678901234">Ville de Paris</a>
After:  <a href="/acheteurs/12345678901234">Ville de Paris</a> <a href="/observatoire?acheteur_id=12345678901234" title="Voir dans l'observatoire">📊</a>
```

For `titulaire_nom`, same pattern but only when the existing `typeIdentifiant` guard passes (SIRET or null):

```
Before: <a href="/titulaires/12345678901234">Entreprise X</a>
After:  <a href="/titulaires/12345678901234">Entreprise X</a> <a href="/observatoire?titulaire_id=12345678901234" title="Voir dans l'observatoire">📊</a>
```

The identifier used in the observatoire link (`acheteur_id` / `titulaire_id`) is the same `pl.col("acheteur_id")` / `pl.col("titulaire_id")` column value already used for the detail page link.

The `_id` and `uid` columns are unchanged.

### 2. `src/pages/observatoire.py` — URL parameter handling

#### Callback A: URL → Inputs (page load)

- Trigger: `Input("dashboard_url", "search")`
- Outputs: `Output("dashboard_acheteur_id", "value")`, `Output("dashboard_titulaire_id", "value")`, `Output("dashboard_url", "search")` (to clear it)
- `prevent_initial_call=False` (must fire on page load to read URL params)
- If `search` is empty or None: return `no_update` for all outputs
- Otherwise: parse query params with `urllib.parse.parse_qs`
- Set `dashboard_acheteur_id` from `?acheteur_id=` param, or `no_update` if absent
- Set `dashboard_titulaire_id` from `?titulaire_id=` param, or `no_update` if absent
- Return `""` for `dashboard_url.search` to clear the URL and prevent re-triggering
- No validation of param values — consistent with existing input handling in the observatoire callbacks

#### Callback B: Inputs → shareable URL

- Trigger: `Input("dashboard_acheteur_id", "value")`, `Input("dashboard_titulaire_id", "value")`
- State: `State("dashboard_url", "href")` for base URL
- `prevent_initial_call=True` (avoid generating URL on initial empty state)
- Build query string with `urllib.parse.urlencode`, omitting empty values
- Write full URL to a new `share-url` input component
- Render a `dcc.Clipboard` + share button (same pattern as tableau.py)

#### Callback chain

When navigating from search with `?acheteur_id=123`: Callback A fires on page load, sets input values, clears URL search. The input value changes then trigger both the existing `udpate_dashboard_cards` callback and Callback B. Dash handles this chaining deterministically — no race condition.

#### Layout additions

- A `dcc.Input(id="share-url", ...)` (hidden or read-only) to hold the shareable URL
- A `dcc.Clipboard` share/copy button near the filters

### 3. Reuse of existing `dcc.Location`

The existing `dcc.Location(id="dashboard_url")` component is reused — no new Location component needed.

## Future extension

The bidirectional URL sync pattern is designed to extend to all observatoire filters (year, categories, departments, market type, etc.) by adding more params to both callbacks.

## Files touched

- `src/utils.py` — modify `add_links()`
- `src/pages/observatoire.py` — add 2 callbacks, add share-url + clipboard to layout
