# Distance Histogram — Design Spec

**Date:** 2026-03-18
**Branch:** feature/65_observatoire

## Goal

Display the distribution of distances (in km) between buyers and winning contractors, to help users assess whether a buyer or contractor tends to deal locally or at a national scale.

## Data

- Column: `titulaire_distance` (`Int64`, km)
- Measured at address level — values are always > 0, no zero-handling needed
- Already selected in the observatoire LazyFrame via `cs.starts_with("titulaire")`
- Already available on acheteur and titulaire detail pages

## Figure Function

**Location:** `src/figures.py`

**Signature:**

```python
def get_distance_histogram(lff: pl.LazyFrame) -> dcc.Graph:
```

**Behaviour:**

- Collects `titulaire_distance` from the LazyFrame, drops nulls
- If the resulting DataFrame is empty after dropping nulls, `px.histogram` produces a blank figure without errors — no guard logic needed. The order of operations must be: drop nulls → log-transform → histogram
- Drop nulls first, then pre-log-transform the column (`pl.col("titulaire_distance").log(10)`) so bins are truly equal-width on a log scale. Use `px.histogram` with `nbins=50` on the transformed values
- Set custom X-axis tick values at powers of 10 (1, 10, 100, 1000, 10000) with km labels, using `fig.update_xaxes(tickvals=[0,1,2,3,4], ticktext=["1","10","100","1 000","10 000"])`
- Y axis: count of contracts
- French axis labels: x = `"Distance (km)"`, y = `"Nombre de marchés"`
- Returns a `dcc.Graph`

## Integration

### Observatoire (`src/pages/observatoire.py`)

- `get_distance_histogram` imported and called inside `udpate_dashboard_cards`
- Result wrapped in `make_card(title="Distance acheteur–titulaire", subtitle="en nombre de marchés, échelle logarithmique", fig=...)`
- Card appended to the `cards` list alongside existing donuts and charts
- No changes to the data pipeline — `titulaire_distance` is already in the LazyFrame

### Acheteur page (`src/pages/acheteur.py`)

The acheteur page uses a `dcc.Store` (`acheteur_data`) that holds serialised contract rows as a list of dicts. The integration follows the existing pattern used by other chart callbacks on this page:

- Add a new `html.Div(id="acheteur-distance-histogram")` placeholder in the layout
- Add a new callback with `Input("acheteur_data", "data")` that:
  - Reconstructs `pl.LazyFrame(data)` from the store
  - Calls `get_distance_histogram(lff)`
  - Wraps the result in `make_card(...)` and returns it to the placeholder div

### Titulaire page (`src/pages/titulaire.py`)

Same pattern as acheteur: `dcc.Store` (`titulaire_data`) → new callback → `html.Div` placeholder.

## Out of Scope

- Filtering by distance range (could be a future filter on the observatoire page)
- Showing distance on a map or as a trend over time
- Bucket-based (named zone) grouping
