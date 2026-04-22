import json
import logging
import os
from collections import OrderedDict

import polars as pl
from httpx import HTTPError, get

from src.db import get_cursor, query_marches, schema
from src.utils import logger

logging.getLogger("httpx").setLevel("WARNING")


def get_annuaire_data(siret: str) -> dict:
    url = f"https://recherche-entreprises.api.gouv.fr/search?q={siret}"
    try:
        response = get(url).raise_for_status()
        response = response.json()["results"][0]
    except (HTTPError, IndexError):
        response = None
        logger.warning("Could not fetch data from recherche-entreprises.api.")
    return response


def get_statistics() -> dict:
    return (
        get(
            "https://www.data.gouv.fr/api/1/datasets/r/0ccf4a75-f3aa-4b46-8b6a-18aeb63e36df",
            follow_redirects=True,
        )
        .raise_for_status()
        .json()
    )


def get_departements() -> dict:
    with open("data/departements.json", "rb") as f:
        data = json.load(f)
        return data


def get_departements_geojson() -> dict:
    with open("./data/departements-1000m.geojson") as f:
        geojson = json.load(f)

    # Ajout de feature.id
    for f in geojson["features"]:
        f["id"] = f["properties"]["code"]

    return geojson


def get_departement_region(code_postal):
    if code_postal > "97000":
        code_departement = code_postal[:3]
    else:
        code_departement = code_postal[:2]
    nom_departement = DEPARTEMENTS[code_departement]["departement"]
    nom_region = DEPARTEMENTS[code_departement]["region"]
    return code_departement, nom_departement, nom_region


def get_data_schema() -> dict:
    # Récupération du schéma des données tabulaires
    path = os.getenv("DATA_SCHEMA_PATH")
    if path.startswith("http"):
        original_schema: dict = get(
            os.getenv("DATA_SCHEMA_PATH"), follow_redirects=True
        ).json()
    elif os.path.exists(path):
        with open(path) as f:
            original_schema: dict = json.load(f)
    else:
        raise Exception(f"Chemin vers le schéma invalide: {path}")

    new_schema = OrderedDict()

    for col in original_schema["fields"]:
        new_schema[col["name"]] = col

    return new_schema


def prepare_dashboard_data(**filter_params) -> pl.DataFrame:
    """Exécute la requête DuckDB filtrée pour le tableau de bord.

    Retourne une pl.DataFrame matérialisée uniquement pour le sous-ensemble
    correspondant aux filtres. Les appelants qui ont besoin d'une LazyFrame
    appellent `.lazy()` sur le résultat.
    """
    from src.utils.table_sql import dashboard_filters_to_sql

    where_sql, params = dashboard_filters_to_sql(**filter_params)
    return query_marches(where_sql=where_sql, params=params)


def build_org_frame(org_type: str) -> pl.DataFrame:
    org_cols = [
        c
        for c in schema.names()
        if c.startswith(f"{org_type}_")
        and c not in (f"{org_type}_latitude", f"{org_type}_longitude")
    ]
    select_list = ", ".join(org_cols)
    group_list = ", ".join(org_cols)
    sql = f'SELECT {select_list}, COUNT(*) AS "Marchés" FROM decp GROUP BY {group_list}'
    return get_cursor().execute(sql).pl()


DF_ACHETEURS = build_org_frame("acheteur")
DF_TITULAIRES = build_org_frame("titulaire")
DEPARTEMENTS = get_departements()
DEPARTEMENTS_GEOJSON = get_departements_geojson()
DATA_SCHEMA = get_data_schema()
