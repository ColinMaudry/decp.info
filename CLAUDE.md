# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**decp.info** is a French public procurement data explorer — a Dash (Python) web app for browsing, filtering, and visualizing _Données Essentielles de la Commande Publique_ (DECP). The UI is in French.

## Commands

### Setup

Setting up the virtual environment:

```bash
python -m venv .venv # s'il n'existe pas déjà
source .venv/bin/activate
rtk pip install -U pip > /dev/null 2>&1
rtk pip install -e . --group=dev
```

Environment variables:

```bash
cp .template.env .env   # then customize .env
```

### Development

```bash
python run.py         # starts Dash app
```

### Production

```bash
gunicorn app:server
```

### Tests

```bash
rtk pytest                  # run all tests (some are Selenium-based integration tests)
rtk pytest tests/test_main.py::test_001_logo_and_search   # run a single test
```

Tests require a running Chrome/Chromium browser. They use `DashComposite` from `dash[testing]` with Selenium WebDriver.

## Architecture

### Multi-page Dash app

- `src/app.py` — creates the Dash app instance, navbar, SEO endpoints (robots.txt, sitemap.xml), Matomo analytics
- `src/pages/*.py` — each page registers itself with `@register_page()` and o.wns its own layout and callbacks
- `run.py` — dev entry point; exports `server` (Flask) for gunicorn

### Module imports

- always import modules from the app starting with `src.` (e.g. `src.utils.`, `src.pages.recherche`, etc.), NOT `utils.cache` or `pages.observatoire`.

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

- Data is stored as **Parquet** at rest, possibly in DuckDB, loaded in DuckDB, served from DuckDB for big queries and manipulated with **Polars** for the remaining steps
- Path set via `DATA_FILE_PARQUET_PATH` env var; tests use `tests/test.parquet`
- `src/util/*.py` — helpers shared by other modules, search (`search_org`), link generation, geographic data loading
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

#### Sauvegarde de la base utilisateurs

`users.sqlite` est sauvegardée toutes les heures sur S3 par un timer systemd
(voir `deploy/decpinfo-backup.{service,timer}`). Installation initiale (une fois,
sur le serveur, en root) :

```bash
cp deploy/decpinfo-backup.service deploy/decpinfo-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now decpinfo-backup.timer
systemctl list-timers decpinfo-backup.timer # vérifier le prochain déclenchement
```

Restauration manuelle :

```bash
cd /var/www/decpinfo && source .venv/bin/activate
python -m src.backup list
systemctl stop decpinfo
python -m src.backup restore backups/users-YYYYMMDDTHHMMSSZ.sqlite.gz.enc
systemctl start decpinfo
```
