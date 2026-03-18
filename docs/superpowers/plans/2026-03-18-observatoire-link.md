# Observatoire Link from Search & Tableau Results — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users jump from search/tableau results to the observatoire page, pre-filtered for a given organization, via a 📊 link in the `_nom` columns.

**Architecture:** Modify `add_links()` in `src/utils.py` to append an observatoire link to `_nom` columns. Add two callbacks to `src/pages/observatoire.py` for bidirectional URL ↔ filter sync using the existing `dcc.Location(id="dashboard_url")`. Add a share URL input and clipboard button to the observatoire layout.

**Tech Stack:** Dash 3.4, Polars, `urllib.parse`, `dcc.Location`, `dcc.Clipboard`

**Spec:** `docs/superpowers/specs/2026-03-18-observatoire-link-from-search-design.md`

---

### Task 1: Add observatoire link to `acheteur_nom` in `add_links()`

**Files:**

- Modify: `src/utils.py:82-91` (the `acheteur_` block inside `add_links()`)
- Test: `tests/test_main.py`

**Context:** The `add_links()` function loops over column names. The `if col.startswith("acheteur_")` block (lines 82-91) currently wraps both `acheteur_nom` and `acheteur_id` in a detail page link. We must only append the observatoire link when `col == "acheteur_nom"`.

- [ ] **Step 1: Write a unit test for the observatoire link in acheteur_nom**

In `tests/test_main.py`, add a test that calls `add_links()` on a minimal DataFrame and checks the `acheteur_nom` column contains both the detail link and the observatoire link, while `acheteur_id` does NOT contain the observatoire link.

```python
def test_004_add_links_observatoire_acheteur():
    import polars as pl

    from src.utils import add_links

    dff = pl.DataFrame(
        {
            "acheteur_id": ["a1"],
            "acheteur_nom": ["ACHETEUR 1"],
        }
    )
    result = add_links(dff)
    nom_value = result["acheteur_nom"][0]
    id_value = result["acheteur_id"][0]

    # acheteur_nom should contain detail link + observatoire link
    assert "/acheteurs/a1" in nom_value
    assert "ACHETEUR 1" in nom_value
    assert '/observatoire?acheteur_id=a1' in nom_value
    assert "📊" in nom_value

    # acheteur_id should NOT contain observatoire link
    assert "/observatoire" not in id_value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_004_add_links_observatoire_acheteur -v`
Expected: FAIL — `'/observatoire?acheteur_id=a1'` not found in the output string.

- [ ] **Step 3: Implement the observatoire link for acheteur_nom**

In `src/utils.py`, modify the `if col.startswith("acheteur_")` block (lines 82-91). Gate the observatoire link append on `col == "acheteur_nom"`:

```python
            if col.startswith("acheteur_"):
                detail_link = (
                    '<a href = "/acheteurs/'
                    + pl.col("acheteur_id")
                    + '">'
                    + pl.col(col)
                    + "</a>"
                )
                if col == "acheteur_nom":
                    detail_link = (
                        detail_link
                        + ' <a href="/observatoire?acheteur_id='
                        + pl.col("acheteur_id")
                        + '" title="Voir dans l\'observatoire">📊</a>'
                    )
                dff = dff.with_columns(detail_link.alias(col))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_004_add_links_observatoire_acheteur -v`
Expected: PASS

- [ ] **Step 5: Update `test_001` to account for the new emoji in cell text**

The existing `test_001` asserts `result_table.find_element(...).text == name` for `acheteur_nom`. The cell text now includes "📊" from the observatoire link. Update the assertion in `tests/test_main.py` to use `startswith` instead of exact match:

```python
        assert result_table.find_element(
            by=By.CSS_SELECTOR, value=f'td[data-dash-column="{org_type}_nom"]'
        ).text.startswith(
            name
        ), f"The search result should have the right {org_type} name"
```

- [ ] **Step 6: Run `test_001` to verify it still passes**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_001_logo_and_search -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/utils.py tests/test_main.py
git commit -m "Ajout du lien observatoire dans acheteur_nom via add_links() #65"
```

---

### Task 2: Add observatoire link to `titulaire_nom` in `add_links()`

**Files:**

- Modify: `src/utils.py:64-81` (the `titulaire_` block inside `add_links()`)
- Test: `tests/test_main.py`

**Context:** The `titulaire_` block (lines 64-81) uses a `pl.when().then().otherwise()` pattern because it guards on `titulaire_typeIdentifiant` being SIRET or null. The observatoire link must be appended inside the `.then()` branch, and only when `col == "titulaire_nom"`. Note: this block requires `titulaire_typeIdentifiant` to be present in the DataFrame.

- [ ] **Step 1: Write a unit test for the observatoire link in titulaire_nom**

```python
def test_005_add_links_observatoire_titulaire():
    import polars as pl

    from src.utils import add_links

    dff = pl.DataFrame(
        {
            "titulaire_id": ["t1"],
            "titulaire_nom": ["TITULAIRE 1"],
            "titulaire_typeIdentifiant": ["SIRET"],
        }
    )
    result = add_links(dff)
    nom_value = result["titulaire_nom"][0]
    id_value = result["titulaire_id"][0]

    # titulaire_nom should contain detail link + observatoire link
    assert "/titulaires/t1" in nom_value
    assert "TITULAIRE 1" in nom_value
    assert '/observatoire?titulaire_id=t1' in nom_value
    assert "📊" in nom_value

    # titulaire_id should NOT contain observatoire link
    assert "/observatoire" not in id_value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_005_add_links_observatoire_titulaire -v`
Expected: FAIL — `'/observatoire?titulaire_id=t1'` not found.

- [ ] **Step 3: Implement the observatoire link for titulaire_nom**

In `src/utils.py`, modify the `if col.startswith("titulaire_")` block (lines 64-81). The `.then()` branch must build the link differently when `col == "titulaire_nom"`:

```python
            if col.startswith("titulaire_"):
                detail_link = (
                    '<a href = "/titulaires/'
                    + pl.col("titulaire_id")
                    + '">'
                    + pl.col(col)
                    + "</a>"
                )
                if col == "titulaire_nom":
                    detail_link = (
                        detail_link
                        + ' <a href="/observatoire?titulaire_id='
                        + pl.col("titulaire_id")
                        + '" title="Voir dans l\'observatoire">📊</a>'
                    )
                dff = dff.with_columns(
                    pl.when(
                        pl.Expr.or_(
                            pl.col("titulaire_typeIdentifiant").is_null(),
                            pl.col("titulaire_typeIdentifiant") == "SIRET",
                        )
                    )
                    .then(detail_link)
                    .otherwise(pl.col(col))
                    .alias(col)
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_005_add_links_observatoire_titulaire -v`
Expected: PASS

- [ ] **Step 5: Run all tests so far to check for regressions**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_004_add_links_observatoire_acheteur tests/test_main.py::test_005_add_links_observatoire_titulaire -v`
Expected: both PASS

- [ ] **Step 6: Commit**

```bash
git add src/utils.py tests/test_main.py
git commit -m "Ajout du lien observatoire dans titulaire_nom via add_links() #65"
```

---

### Task 3: Observatoire Callback A — URL → Inputs (page load)

**Files:**

- Modify: `src/pages/observatoire.py` (add import + new callback after line 281)
- Test: `tests/test_main.py`

**Context:** The existing `dcc.Location(id="dashboard_url")` is in the observatoire layout. A new callback reads `dashboard_url.search` on page load, parses query params, and sets `dashboard_acheteur_id.value` and/or `dashboard_titulaire_id.value`. It also clears `dashboard_url.search` to `""` to prevent re-triggering. Two imports must be added: `import urllib.parse` at the top of the file, and `no_update` to the existing `from dash import ...` line (currently: `from dash import ALL, Input, Output, State, callback, ctx, dcc, html, register_page` — add `no_update` to this).

- [ ] **Step 1: Write a Selenium test for URL → Input sync**

This test navigates to `/observatoire?acheteur_id=a1` and verifies the SIRET input gets populated.

```python
def test_006_observatoire_url_to_input(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)

    # Navigate to observatoire with acheteur_id query param
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire?acheteur_id=a1")
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    dash_duo.wait_for_text_to_equal(
        "#dashboard_acheteur_id", "", timeout=4
    )  # Wait for callback
    import time
    time.sleep(1)  # Allow callback chain to complete

    assert acheteur_input.get_attribute("value") == "a1", (
        "acheteur_id input should be populated from URL param"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_006_observatoire_url_to_input -v`
Expected: FAIL — the input value is empty because no callback reads URL params yet.

- [ ] **Step 3: Implement Callback A**

Add `import urllib.parse` to the imports at the top of `src/pages/observatoire.py` (after line 1). Also add `no_update` to the existing dash import line:

```python
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update, register_page
```

Add the callback after the `layout` list ends, before existing callbacks:

```python
@callback(
    Output("dashboard_acheteur_id", "value"),
    Output("dashboard_titulaire_id", "value"),
    Output("dashboard_url", "search"),
    Input("dashboard_url", "search"),
)
def restore_filters_from_url(search):
    if not search:
        return no_update, no_update, no_update

    params = urllib.parse.parse_qs(search.lstrip("?"))

    acheteur_id = params.get("acheteur_id", [None])[0] or no_update
    titulaire_id = params.get("titulaire_id", [None])[0] or no_update

    return acheteur_id, titulaire_id, ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_006_observatoire_url_to_input -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pages/observatoire.py tests/test_main.py
git commit -m "Callback URL → filtres sur la page observatoire #65"
```

---

### Task 4: Observatoire Callback B — Inputs → shareable URL + layout

**Files:**

- Modify: `src/pages/observatoire.py` (add layout components + new callback)
- Test: `tests/test_main.py`

**Context:** Following the tableau.py pattern (lines 237-238 for layout, lines 399-450 for callback), add a hidden `share-url` input and a `copy-container` div to the observatoire layout. The callback listens to the ID inputs and builds a shareable URL. Component IDs must be unique across the app, so use `observatoire-share-url` and `observatoire-copy-container` to avoid collisions with tableau's `share-url` and `copy-container`.

- [ ] **Step 1: Write a test for the shareable URL generation**

```python
def test_007_observatoire_share_url(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)

    # Navigate to observatoire with acheteur_id query param
    dash_duo.wait_for_page(f"{dash_duo.server_url}/observatoire?acheteur_id=a1")
    dash_duo.wait_for_element("#observatoire-share-url", timeout=4)

    import time
    time.sleep(1)  # Allow callback chain to complete

    share_url_input = dash_duo.find_element("#observatoire-share-url")
    share_url_value = share_url_input.get_attribute("value")

    assert "acheteur_id=a1" in share_url_value, (
        f"Share URL should contain acheteur_id param, got: {share_url_value}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_007_observatoire_share_url -v`
Expected: FAIL — `#observatoire-share-url` element does not exist yet.

- [ ] **Step 3: Add layout components to observatoire**

In `src/pages/observatoire.py`, add the share URL input and copy container inside the filters column (after the download button, before the closing `]` of the `id="filters"` children list, around line 264):

```python
                                    dcc.Input(
                                        id="observatoire-share-url",
                                        readOnly=True,
                                        style={"display": "none"},
                                    ),
                                    html.Div(id="observatoire-copy-container"),
```

- [ ] **Step 4: Implement Callback B**

Add after Callback A in `src/pages/observatoire.py`:

```python
@callback(
    Output("observatoire-share-url", "value"),
    Output("observatoire-copy-container", "children"),
    Input("dashboard_acheteur_id", "value"),
    Input("dashboard_titulaire_id", "value"),
    State("dashboard_url", "href"),
    prevent_initial_call=True,
)
def sync_observatoire_share_url(acheteur_id, titulaire_id, href):
    if not href:
        return no_update, no_update

    base_url = href.split("?")[0]

    params = {}
    if acheteur_id:
        params["acheteur_id"] = acheteur_id
    if titulaire_id:
        params["titulaire_id"] = titulaire_id

    query_string = urllib.parse.urlencode(params)
    full_url = f"{base_url}?{query_string}" if query_string else base_url

    copy_button = dcc.Clipboard(
        id="btn-copy-observatoire-url",
        target_id="observatoire-share-url",
        title="Copier l'URL de cette vue",
        style={
            "display": "inline-block",
            "fontSize": 20,
            "verticalAlign": "top",
            "cursor": "pointer",
        },
        className="fa fa-link",
        children=[
            dbc.Button(
                "Partager",
                className="btn btn-primary mt-2",
                title="Copier l'adresse de cette vue filtrée pour la partager.",
            )
        ],
    )

    return full_url, copy_button
```

- [ ] **Step 5: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_007_observatoire_share_url -v`
Expected: PASS

- [ ] **Step 6: Run all tests to check for regressions**

Run: `source .venv/bin/activate && pytest tests/test_main.py -v`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/pages/observatoire.py tests/test_main.py
git commit -m "URL partageable pour la page observatoire #65"
```

---

### Task 5: End-to-end integration test

**Files:**

- Test: `tests/test_main.py`

**Context:** Verify the full flow: search for an organization on the homepage, see the 📊 link in results, click it, arrive on the observatoire with the correct input populated.

- [ ] **Step 1: Write end-to-end test**

```python
def test_008_search_to_observatoire(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.wait_for_text_to_equal(".logo > h1", "decp.info", timeout=4)

    # Search for an acheteur
    search_bar = dash_duo.find_element("#search")
    search_bar.send_keys("ACHETEUR 1")
    search_bar.send_keys(Keys.ENTER)

    dash_duo.wait_for_element("#results_acheteur_datatable", timeout=2)

    # Find the observatoire link in acheteur_nom column
    observatoire_link = dash_duo.find_element(
        '#results_acheteur_datatable td[data-dash-column="acheteur_nom"] a[href*="observatoire"]'
    )
    assert "📊" in observatoire_link.text

    # Click the observatoire link
    observatoire_link.click()

    # Wait for observatoire page to load
    dash_duo.wait_for_element("#dashboard_acheteur_id", timeout=4)

    import time
    time.sleep(1)  # Allow callback chain to complete

    acheteur_input = dash_duo.find_element("#dashboard_acheteur_id")
    assert acheteur_input.get_attribute("value") == "a1", (
        "acheteur_id input should be populated after navigating from search"
    )
```

- [ ] **Step 2: Run end-to-end test**

Run: `source .venv/bin/activate && pytest tests/test_main.py::test_008_search_to_observatoire -v`
Expected: PASS

- [ ] **Step 3: Run the full test suite**

Run: `source .venv/bin/activate && pytest tests/test_main.py -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_main.py
git commit -m "Test e2e : recherche → observatoire #65"
```
