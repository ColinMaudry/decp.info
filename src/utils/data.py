import json
import logging
import os
from collections import OrderedDict

import httpx
import polars as pl
from httpx import HTTPError, get

from src.db import get_cursor, query_marches, schema
from src.utils import logger

logging.getLogger("httpx").setLevel("WARNING")


def get_annuaire_data(siret: str) -> dict | None:
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


def get_departement_region(code_postal: str | None):
    if code_postal:
        if code_postal > "97000":
            code_departement = code_postal[:3]
        else:
            code_departement = code_postal[:2]
        nom_departement = DEPARTEMENTS[code_departement]["departement"]
        nom_region = DEPARTEMENTS[code_departement]["region"]
        return code_departement, nom_departement, nom_region
    return "", "", ""


def _validate_schema(raw) -> dict | None:
    if (
        isinstance(raw, dict)
        and isinstance(raw.get("fields"), list)
        and raw["fields"]
        and all(isinstance(c, dict) and "name" in c for c in raw["fields"])
    ):
        return raw
    return None


def _fetch_remote_schema(url: str | None) -> dict | None:
    if not url:
        return None
    try:
        raw = get(url, follow_redirects=True).raise_for_status().json()
    except (
        httpx.HTTPError,
        httpx.TransportError,
        httpx.TimeoutException,
        json.JSONDecodeError,
    ) as e:
        logger.error(f"Schéma distant indisponible ({url}) : {e}")
        return None
    return _validate_schema(raw)


def _load_schema_file(path: str) -> dict | None:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Schéma local illisible ({path}) : {e}")
        return None
    return _validate_schema(raw)


def _persist_schema_cache(raw: dict, path: str) -> None:
    if not path:
        return
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(raw, f)
        os.replace(tmp, path)
    except (OSError, ValueError) as e:
        logger.warning(f"Écriture du cache schéma échouée ({path}) : {e}")


def get_data_schema() -> dict:
    cache_path = os.getenv("DATA_SCHEMA_CACHE", "./schema.cache.json")
    raw = _fetch_remote_schema(os.getenv("DATA_SCHEMA_PATH"))
    if raw is not None:
        _persist_schema_cache(raw, cache_path)
    else:
        raw = _load_schema_file(cache_path)
    if raw is None:
        raise RuntimeError("Aucun schéma disponible (ni distant ni cache).")
    schema = OrderedDict((c["name"], c) for c in raw["fields"])
    for col in schema.keys():
        new_obj = schema[col]
        if "enum" in new_obj:
            enums = ", ".join(new_obj["enum"])
            new_obj["description"] = (
                f"{new_obj['description']} Valeurs possibles : {enums}"
            )
    return schema


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
        and c
        not in (
            f"{org_type}_latitude",
            f"{org_type}_longitude",
            f"{org_type}_distance",
        )
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
# Colonne virtuelle (dérivée de uid) : lien loupe vers la fiche du marché.
# Absente du schéma DuckDB, créée à l'affichage dans postprocess_page().
DATA_SCHEMA["marche"] = {
    "name": "marche",
    "type": "string",
    "title": "Marché",
    "description": "Lien vers la fiche détaillée du marché.",
}
