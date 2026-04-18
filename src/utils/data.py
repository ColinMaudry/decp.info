import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timedelta

import polars as pl
from httpx import HTTPError, get

from src.db import get_cursor, schema
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


def prepare_dashboard_data(
    lff: pl.LazyFrame,
    dashboard_year=None,
    dashboard_acheteur_id=None,
    dashboard_acheteur_categorie=None,
    dashboard_acheteur_departement_code=None,
    dashboard_titulaire_id=None,
    dashboard_titulaire_categorie=None,
    dashboard_titulaire_departement_code=None,
    dashboard_marche_type=None,
    dashboard_marche_objet=None,
    dashboard_marche_code_cpv=None,
    dashboard_marche_considerations_sociales=None,
    dashboard_marche_considerations_environnementales=None,
    dashboard_marche_techniques=None,
    dashboard_marche_innovant=None,
    dashboard_marche_sous_traitance_declaree=None,
    dashboard_montant_min=None,
    dashboard_montant_max=None,
) -> pl.LazyFrame:
    if dashboard_year:
        lff = lff.filter(pl.col("dateNotification").dt.year() == int(dashboard_year))
    else:
        lff = lff.filter(
            pl.col("dateNotification") > (datetime.now() - timedelta(days=365))
        )

    if dashboard_acheteur_id:
        lff = lff.filter(pl.col("acheteur_id").str.contains(dashboard_acheteur_id))
    else:
        if dashboard_acheteur_categorie:
            lff = lff.filter(
                pl.col("acheteur_categorie") == dashboard_acheteur_categorie
            )
        if dashboard_acheteur_departement_code:
            lff = lff.filter(
                pl.col("acheteur_departement_code").is_in(
                    dashboard_acheteur_departement_code
                )
            )

    if dashboard_titulaire_id:
        lff = lff.filter(pl.col("titulaire_id").str.contains(dashboard_titulaire_id))
    else:
        if dashboard_titulaire_categorie:
            lff = lff.filter(
                pl.col("titulaire_categorie") == dashboard_titulaire_categorie
            )
        if dashboard_titulaire_departement_code:
            lff = lff.filter(
                pl.col("titulaire_departement_code").is_in(
                    dashboard_titulaire_departement_code
                )
            )

    if dashboard_marche_type:
        lff = lff.filter(pl.col("type") == dashboard_marche_type)

    if dashboard_marche_objet:
        lff = lff.filter(pl.col("objet").str.contains(f"(?i){dashboard_marche_objet}"))

    if dashboard_marche_code_cpv:
        lff = lff.filter(pl.col("codeCPV").str.starts_with(dashboard_marche_code_cpv))

    if dashboard_marche_innovant and dashboard_marche_innovant != "all":
        lff = lff.filter(pl.col("marcheInnovant") == dashboard_marche_innovant)

    if (
        dashboard_marche_sous_traitance_declaree
        and dashboard_marche_sous_traitance_declaree != "all"
    ):
        lff = lff.filter(
            pl.col("sousTraitanceDeclaree") == dashboard_marche_sous_traitance_declaree
        )

    if dashboard_marche_techniques:
        lff = lff.filter(
            pl.col("techniques")
            .str.split(", ")
            .list.set_intersection(dashboard_marche_techniques)
            .list.len()
            > 0
        )

    if dashboard_marche_considerations_sociales:
        lff = lff.filter(
            pl.col("considerationsSociales")
            .str.split(", ")
            .list.set_intersection(dashboard_marche_considerations_sociales)
            .list.len()
            > 0
        )

    if dashboard_marche_considerations_environnementales:
        lff = lff.filter(
            pl.col("considerationsEnvironnementales")
            .str.split(", ")
            .list.set_intersection(dashboard_marche_considerations_environnementales)
            .list.len()
            > 0
        )

    if dashboard_montant_min is not None:
        lff = lff.filter(pl.col("montant") >= dashboard_montant_min)

    if dashboard_montant_max is not None:
        lff = lff.filter(pl.col("montant") <= dashboard_montant_max)

    return lff


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
