import json
import logging
import os
from time import sleep

import polars as pl
import polars.selectors as cs
from dotenv import load_dotenv
from httpx import get
from polars.exceptions import ComputeError

load_dotenv()

operators = [
    ["s<", "<"],
    ["s>", ">"],
    ["i<", "<"],
    ["i>", ">"],
    ["icontains", "contains"],
]

logger = logging.getLogger("decp.info")
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


def split_filter_part(filter_part):
    print("filter part", filter_part)
    for operator_group in operators:
        if operator_group[0] in filter_part:
            name_part, value_part = filter_part.split(operator_group[0], 1)
            name_part = name_part.strip()
            value = value_part.strip()
            name = name_part[name_part.find("{") + 1 : name_part.rfind("}")]
            print("=>", name, operator_group[1], value)

            return name, operator_group[1], value

    return [None] * 3


def add_resource_link(dff: pl.DataFrame) -> pl.DataFrame:
    dff = dff.with_columns(
        (
            '<a href="' + pl.col("sourceFile") + '">' + pl.col("sourceDataset") + "</a>"
        ).alias("source")
    )
    dff = dff.drop(["sourceFile", "sourceDataset"])
    return dff


def add_org_links(dff: pl.DataFrame):
    dff = dff.with_columns(
        pl.when(pl.col("titulaire_typeIdentifiant") == "SIRET")
        .then(
            '<a href = "https://annuaire-entreprises.data.gouv.fr/etablissement/'
            + pl.col("titulaire_id")
            + '">'
            + pl.col("titulaire_id")
            + "</a>"
        )
        .otherwise(pl.col("titulaire_id"))
        .alias("titulaire_id")
    )
    dff = dff.with_columns(
        (
            '<a href = "/acheteur/'
            + pl.col("acheteur_id")
            + '" target="_blank">'
            + pl.col("acheteur_id")
            + "</a>"
        ).alias("acheteur_id")
    )
    return dff


def booleans_to_strings(lff: pl.LazyFrame) -> pl.LazyFrame:
    """
    Convert all boolean columns to string type.
    """
    lff = lff.with_columns(
        pl.col(cs.Boolean)
        .cast(pl.String)
        .str.replace("true", "oui")
        .str.replace("false", "non")
    )
    return lff


def numbers_to_strings(lff: pl.LazyFrame) -> pl.LazyFrame:
    """
    Convert all numeric columns to string type.
    """
    lff = lff.with_columns(pl.col(pl.Float64, pl.Int16).cast(pl.String).fill_null(""))
    return lff


def format_number(number) -> str:
    number = "{:,}".format(number).replace(",", " ")
    return number


def get_annuaire_data(siret: str) -> dict:
    url = f"https://recherche-entreprises.api.gouv.fr/search?q={siret}"
    response = get(url)
    return response.json()["results"][0]


def get_decp_data() -> pl.LazyFrame:
    # Chargement du fichier parquet
    # Le fichier est chargé en mémoire, ce qui est plus rapide qu'une base de données pour le moment.
    # On utilise polars pour la rapidité et la facilité de manipulation des données.

    try:
        logger.info(
            f"Lecture du fichier parquet ({os.getenv('DATA_FILE_PARQUET_PATH')})..."
        )
        lff: pl.LazyFrame = pl.scan_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))
    except ComputeError:
        # Le fichier est probablement en cours de mise à jour
        logger.info("Échec, nouvelle tentative dans 10s...")
        sleep(10)
        lff: pl.LazyFrame = pl.scan_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))

    # Tri des marchés par date de notification
    lff = lff.sort(by=["dateNotification", "uid"], descending=True, nulls_last=True)

    # Uniquement les données actuelles, pas les anciennes versions de marchés
    lff = lff.filter(pl.col("donneesActuelles")).drop("donneesActuelles")

    # Convertir les colonnes booléennes en chaînes de caractères
    lff = booleans_to_strings(lff)

    # Bizarrement je ne peux pas faire lff = lff.fill_null("") ici
    # ça génère une erreur dans la page acheteur (acheteur_data.table) :
    # AttributeError: partially initialized module 'pandas' has no attribute 'NaT' (most likely due to a circular import)

    return lff


def get_departements() -> dict:
    with open("data/departements.json", "rb") as f:
        data = json.load(f)
        return data


def get_departement_region(code_postal):
    if code_postal > "97000":
        code_departement = code_postal[:3]
    else:
        code_departement = code_postal[:2]
    nom_departement = departements[code_departement]["departement"]
    nom_region = departements[code_departement]["region"]
    return code_departement, nom_departement, nom_region


def filter_table_data(lff: pl.LazyFrame, filter_query: str) -> pl.LazyFrame:
    schema = lff.collect_schema()
    filtering_expressions = filter_query.split(" && ")
    for filter_part in filtering_expressions:
        col_name, operator, filter_value = split_filter_part(filter_part)
        col_type = str(schema[col_name])
        print("filter_value:", filter_value)
        print("filter_value_type:", type(filter_value))
        print("col_type:", col_type)

        if operator in ("<", "<=", ">", ">="):
            filter_value = int(filter_value)
            if operator == "<":
                lff = lff.filter(pl.col(col_name) < filter_value)
            elif operator == ">":
                lff = lff.filter(pl.col(col_name) > filter_value)
            elif operator == ">=":
                lff = lff.filter(pl.col(col_name) >= filter_value)
            elif operator == "<=":
                lff = lff.filter(pl.col(col_name) <= filter_value)

        elif col_type.startswith("Int") or col_type.startswith("Float"):
            try:
                filter_value = int(filter_value)
            except ValueError:
                logger.error(f"Invalid numeric filter value: {filter_value}")
                continue
            lff = lff.filter(pl.col(col_name) == filter_value)

        elif operator == "contains" and col_type == "String":
            lff = lff.filter(pl.col(col_name).str.contains("(?i)" + filter_value))

        # elif operator == 'datestartswith':
        # lff = lff.filter(pl.col(col_name).str.startswith(filter_value)")

    return lff


def sort_table_data(lff: pl.LazyFrame, sort_by: list) -> pl.LazyFrame:
    lff = lff.sort(
        [col["column_id"] for col in sort_by],
        descending=[col["direction"] == "desc" for col in sort_by],
        nulls_last=True,
    )
    print(sort_by)
    return lff


lf = get_decp_data()
departements = get_departements()
