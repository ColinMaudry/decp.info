# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**decp.info** is a French public procurement data explorer — a Dash (Python) web app for browsing, filtering, and visualizing _Données Essentielles de la Commande Publique_ (DECP). The UI is in French.

## Commands

### Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install ".[dev]"
cp template.env .env   # then customize .env
```

### Development

```bash
uv run run.py         # starts Dash with debug=True and hot reload
```

### Production

```bash
gunicorn app:server
```

### Tests

```bash
uv run pytest                  # run all tests (Selenium-based integration tests)
uv run pytest tests/test_main.py::test_001_logo_and_search   # run a single test
```

Tests require a running Chrome/Chromium browser. They use `DashComposite` from `dash[testing]` with Selenium WebDriver.

## Architecture

### Multi-page Dash app

- `src/app.py` — creates the Dash app instance, navbar, SEO endpoints (robots.txt, sitemap.xml), Matomo analytics
- `src/pages/*.py` — each page registers itself with `@register_page()` and owns its own layout and callbacks
- `run.py` — dev entry point; exports `server` (Flask) for gunicorn

### Module imports

- always import modules from the app starting with `src.` (e.g. `src.utils.`, `src.pages.recherche`, etc.)

### Key pages

| Page              | URL             | Purpose                                |
| ----------------- | --------------- | -------------------------------------- |
| `recherche.py`    | `/`             | Search homepage for buyers/contractors |
| `acheteur.py`     | `/acheteur`     | Buyer detail with stats, charts, maps  |
| `titulaire.py`    | `/titulaire`    | Contractor detail                      |
| `tableau.py`      | `/tableau`      | Filterable data table with exports     |
| `marche.py`       | `/marche`       | Individual contract detail             |
| `observatoire.py` | `/observatoire` | An interactive analytics dashboard     |

### Data layer

- Data is stored as **Parquet** and loaded with **Polars** (fast columnar operations)
- Path set via `DATA_FILE_PARQUET_PATH` env var; tests use `tests/test.parquet`
- `src/utils.py` — filtering helpers, search (`search_org`), link generation, geographic data loading
- `src/callbacks.py` — shared Dash callbacks (e.g. `get_top_org_table`)
- `src/figures.py` — chart and map components (Plotly Express, Dash Leaflet with marker clustering)
- a Parquet file with production data is located at `../decp-processing/decp_prod.parquet` (~ 1,5 million records)
- the TableSchema of the dataset with the list of field and their definition is located at `../decp-processing/reference/base_schema.json`
- `tests/test.parquet` is very small and may not contain all possible columns, only those necessary for testing

### UI stack

- **Dash 3.4** + **Dash Bootstrap Components** for layout
- **Plotly Express** for charts
- **Dash Leaflet** + **Dash Extensions** for interactive maps with clustering
- Custom CSS in `src/assets/css/`

### Environment

- `DEVELOPMENT=true` enables debug logging and is set automatically during tests
- `.env` file is required at runtime (copy from `template.env`)

### Deployment

- `main` branch → manual deploy to decp.info via GitHub Actions
- `dev` branch → auto-deploy to test.decp.info via GitHub Actions
