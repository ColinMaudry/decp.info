import logging
import os
from time import sleep

import polars as pl
import polars.selectors as cs
from dotenv import load_dotenv
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


def add_resource_link(lff: pl.LazyFrame) -> pl.LazyFrame:
    lff = lff.with_columns(
        (
            '<a href="' + pl.col("sourceOpenData") + '">' + pl.col("source") + "</a>"
        ).alias("source")
    )
    lff = lff.drop("sourceOpenData")
    return lff


def add_annuaire_link(lff: pl.LazyFrame):
    lff = lff.with_columns(
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
    lff = lff.with_columns(
        (
            '<a href = "https://annuaire-entreprises.data.gouv.fr/etablissement/'
            + pl.col("acheteur_id")
            + '">'
            + pl.col("acheteur_id")
            + "</a>"
        ).alias("acheteur_id")
    )
    return lff


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


def get_decp_data() -> pl.LazyFrame:
    # Chargement du fichier parquet
    # Le fichier est chargé en mémoire, ce qui est plus rapide qu'une base de données pour le moment.
    # On utilise polars pour la rapidité et la facilité de manipulation des données.

    try:
        logger.info(
            f"Lecture du fichier parquet ({os.getenv('DATA_FILE_PARQUET_PATH')})..."
        )
        df: pl.DataFrame = pl.read_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))
    except ComputeError:
        # Le fichier est probablement en cours de mise à jour
        logger.info("Échec, nouvelle tentative dans 10s...")
        sleep(10)
        df: pl.DataFrame = pl.read_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))

    lff: pl.LazyFrame = df.lazy()

    # Remplacement des valeurs numériques par des chaînes de caractères
    # lff = numbers_to_strings(lff)

    # Tri des marchés par date de notification
    lff = lff.sort(by=["datePublicationDonnees"], descending=True, nulls_last=True)

    return lff


lf = get_decp_data()
