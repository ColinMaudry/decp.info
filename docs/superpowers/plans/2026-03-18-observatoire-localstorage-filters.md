# Observatoire localStorage Filter Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist all 10 observatoire filter values in `localStorage` so they survive navigation and page reloads; URL params (`acheteur_id` / `titulaire_id`) override stored values.

**Architecture:** Add `dcc.Store(storage_type="local", id="observatoire-filters")` to the observatoire layout. A new save callback writes all 10 filter values to the store on any change (`prevent_initial_call=True` to avoid wiping localStorage on page mount). The existing `restore_filters_from_url` callback is expanded: it now outputs all 10 filters, accepts the store as `State`, and prioritises URL params over stored values.

**Tech Stack:** Dash 3.4 `dcc.Store` with `storage_type="local"`, Dash callbacks (Input / Output / State), pytest + Selenium (`DashComposite`).

---

## File Map

| Action | File                                                                  |
| ------ | --------------------------------------------------------------------- |
| Modify | `src/pages/observatoire.py` — layout + 2 callbacks                    |
| Modify | `tests/test_main.py` — add `test_009_observatoire_filter_persistence` |

---

### Task 1: Write a failing integration test

**Files:**

- Modify: `tests/test_main.py`

- [ ] **Step 1: Add test_009 at the end of `tests/test_main.py`**

```python
def test_009_observatoire_filter_persistence(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)

    # Clear localStorage to start from a clean state
    dash_duo.driver.execute_script("localStorage.clear()")

    # Navigate to observatoire without URL params
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire")
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    # Set the acheteur_id text input
    # dcc.Input without debounce fires the save callback on every keystroke,
    # so the value is written to localStorage as soon as typing finishes.
    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    dash_duo.clear_input(acheteur_input)
    acheteur_input.send_keys("999000000000")

    import time
    time.sleep(0.3)  # allow the save callback to complete

    # Navigate away
    dash_duo.wait_for_page(f"{dash_duo.server_url}/")

    # Navigate back without URL params
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire")
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    import time
    time.sleep(0.5)  # allow callback chain to complete

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "999000000000", (
        "acheteur_id should be restored from localStorage after navigating back"
    )

    # Also verify URL params still override localStorage
    dash_duo.wait_for_page(
        f"{dash_duo.server_url}/observatoire?acheteur_id=123"
    )
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)
    time.sleep(0.5)

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "123", (
        "URL param acheteur_id should override the value stored in localStorage"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_main.py::test_009_observatoire_filter_persistence -v
```

Expected: **FAIL** — the input value after navigating back will be `""`, not `"999000000000"`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_main.py
git commit -m "test: failing test for observatoire localStorage filter persistence #65"
```

---

### Task 2: Add `dcc.Store` to the layout and debounce the text inputs

**Files:**

- Modify: `src/pages/observatoire.py`

- [ ] **Step 1: Add the Store component to the layout**

In `src/pages/observatoire.py`, add this line immediately after the existing `dcc.Location` (line 123):

```python
dcc.Store(id="observatoire-filters", storage_type="local"),
```

So the top of the `layout` list becomes:

```python
layout = [
    dcc.Location(id="dashboard_url", refresh="callback-nav"),
    dcc.Store(id="observatoire-filters", storage_type="local"),
    dbc.Modal(
        ...
```

- [ ] **Step 2: Add `debounce=True` to both text inputs**

`dcc.Input` without debounce fires on every keystroke, which would trigger the save callback (and the existing heavy `udpate_dashboard_cards` callback) on every character typed. `debounce=True` delays the callback until the user presses Enter or moves focus away.

Change `dashboard_acheteur_id` (around line 178):

```python
dcc.Input(
    id="dashboard_acheteur_id",
    placeholder="SIRET",
    debounce=True,
    style={"width": "100%"},
),
```

Change `dashboard_titulaire_id` (around line 209):

```python
dcc.Input(
    id="dashboard_titulaire_id",
    placeholder="SIRET",
    debounce=True,
    style={"width": "100%"},
),
```

- [ ] **Step 3: Run the test — still fails (restore not implemented yet)**

```bash
pytest tests/test_main.py::test_009_observatoire_filter_persistence -v
```

Expected: still **FAIL**.

- [ ] **Step 4: Commit**

```bash
git add src/pages/observatoire.py
git commit -m "feat: add dcc.Store and debounce text inputs on observatoire page #65"
```

---

### Task 3: Add a save-to-localStorage callback

**Files:**

- Modify: `src/pages/observatoire.py`

- [ ] **Step 1: Add the save callback after the existing `restore_filters_from_url` callback**

```python
@callback(
    Output("observatoire-filters", "data"),
    Input("dashboard_year", "value"),
    Input("dashboard_acheteur_id", "value"),
    Input("dashboard_acheteur_categorie", "value"),
    Input("dashboard_acheteur_departement_code", "value"),
    Input("dashboard_titulaire_id", "value"),
    Input("dashboard_titulaire_categorie", "value"),
    Input("dashboard_titulaire_departement_code", "value"),
    Input("dashboard_marche_type", "value"),
    Input("dashboard_marche_considerationsSociales", "value"),
    Input("dashboard_marche_considerationsEnvironnementales", "value"),
    prevent_initial_call=True,
)
def save_filters_to_storage(
    year,
    acheteur_id,
    acheteur_categorie,
    acheteur_departement_code,
    titulaire_id,
    titulaire_categorie,
    titulaire_departement_code,
    marche_type,
    considerations_sociales,
    considerations_environnementales,
):
    return {
        "year": year,
        "acheteur_id": acheteur_id,
        "acheteur_categorie": acheteur_categorie,
        "acheteur_departement_code": acheteur_departement_code,
        "titulaire_id": titulaire_id,
        "titulaire_categorie": titulaire_categorie,
        "titulaire_departement_code": titulaire_departement_code,
        "marche_type": marche_type,
        "considerations_sociales": considerations_sociales,
        "considerations_environnementales": considerations_environnementales,
    }
```

**Why `prevent_initial_call=True`:** Without it, this callback fires on every page load with all-`None` values (the component defaults), immediately overwriting any saved filters. Setting `prevent_initial_call=True` skips that first call; subsequent user-driven changes still fire normally.

- [ ] **Step 2: Run the test — still fails (restore callback not updated yet)**

```bash
pytest tests/test_main.py::test_009_observatoire_filter_persistence -v
```

Expected: still **FAIL**.

- [ ] **Step 3: Commit**

```bash
git add src/pages/observatoire.py
git commit -m "feat: save observatoire filters to localStorage on change #65"
```

---

### Task 4: Update the restore callback to read from localStorage

**Files:**

- Modify: `src/pages/observatoire.py`

This is the core change. Replace the existing `restore_filters_from_url` callback entirely.

- [ ] **Step 1: Replace the existing callback**

Remove the current `restore_filters_from_url` function and its `@callback` decorator (lines 302–323) and replace with:

```python
@callback(
    Output("dashboard_year", "value"),
    Output("dashboard_acheteur_id", "value"),
    Output("dashboard_acheteur_categorie", "value"),
    Output("dashboard_acheteur_departement_code", "value"),
    Output("dashboard_titulaire_id", "value"),
    Output("dashboard_titulaire_categorie", "value"),
    Output("dashboard_titulaire_departement_code", "value"),
    Output("dashboard_marche_type", "value"),
    Output("dashboard_marche_considerationsSociales", "value"),
    Output("dashboard_marche_considerationsEnvironnementales", "value"),
    Input("dashboard_url", "search"),
    Input("dashboard_url", "pathname"),
    State("observatoire-filters", "data"),
)
def restore_filters(search, _pathname, stored_filters):
    # URL params take absolute priority: clear all other filters and apply only
    # the values present in the URL (acheteur_id and/or titulaire_id).
    if search:
        params = urllib.parse.parse_qs(search.lstrip("?"))
        acheteur_id = (params.get("acheteur_id") or [None])[0] or None
        titulaire_id = (params.get("titulaire_id") or [None])[0] or None
        if acheteur_id or titulaire_id:
            return None, acheteur_id, None, None, titulaire_id, None, None, None, None, None

    # No URL params: restore from localStorage if available.
    if stored_filters:
        return (
            stored_filters.get("year"),
            stored_filters.get("acheteur_id"),
            stored_filters.get("acheteur_categorie"),
            stored_filters.get("acheteur_departement_code"),
            stored_filters.get("titulaire_id"),
            stored_filters.get("titulaire_categorie"),
            stored_filters.get("titulaire_departement_code"),
            stored_filters.get("marche_type"),
            stored_filters.get("considerations_sociales"),
            stored_filters.get("considerations_environnementales"),
        )

    return (no_update,) * 10
```

**Key design decisions:**

- `Input("dashboard_url", "pathname")` added alongside `search`: guarantees the callback fires on every navigation to the observatoire page, even when `search` stays `""` (no query string) across two navigations. The `_pathname` value itself is unused in the body; it exists only as a trigger.
- `State("observatoire-filters", "data")` (not `Input`): the store triggers no re-run when the save callback writes to it, avoiding an infinite loop.
- When URL params are present, _all_ non-URL filters are cleared (`None`), which causes the save callback to overwrite localStorage with only the URL-provided values.
- `(no_update,) * 10` when there is nothing to restore: leaves defaults intact.

- [ ] **Step 2: Run the target test**

```bash
pytest tests/test_main.py::test_009_observatoire_filter_persistence -v
```

Expected: **PASS**.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -v
```

Expected: all tests **PASS**. Pay special attention to `test_006` and `test_007` (URL → input / share URL), which exercise the code path that was just rewritten.

- [ ] **Step 4: Commit**

```bash
git add src/pages/observatoire.py
git commit -m "feat: restore observatoire filters from localStorage on page load #65"
```
