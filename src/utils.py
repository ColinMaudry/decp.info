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

            return name, operator_group[1], value

    return [None] * 3


def add_annuaire_link(df: pl.LazyFrame):
    df = df.with_columns(
        pl.when(pl.col("titulaire_typeIdentifiant") == "SIRET")
        .then(
            pl.col("titulaire_id")
            + ' <a href="https://annuaire-entreprises.data.gouv.fr/etablissement/'
            + pl.col("titulaire_id")
            + '">📑</a>'
        )
        .otherwise(pl.col("titulaire_id"))
        .alias("titulaire_id")
    )
    df = df.with_columns(
        (
            pl.col("acheteur_id")
            + ' <a href="https://annuaire-entreprises.data.gouv.fr/etablissement/'
            + pl.col("acheteur_id")
            + '" target="_blank">📑</a>'
        ).alias("acheteur_id")
    )
    return df


def booleans_to_strings(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Convert all boolean columns to string type.
    """
    lf = lf.with_columns(
        pl.col(cs.Boolean)
        .cast(pl.String)
        .str.replace("true", "oui")
        .str.replace("false", "non")
    )
    return lf


def numbers_to_strings(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Convert all numeric columns to string type.
    """
    lf = lf.with_columns(pl.col(pl.Float64, pl.Int16).cast(pl.String).fill_null(""))
    return lf


def format_number(number) -> str:
    number = "{:,}".format(number).replace(",", " ")
    return number


def get_decp_data() -> pl.DataFrame:
    # Chargement du fichier parquet
    # Le fichier est chargé en mémoire, ce qui est plus rapide qu'une base de données pour le moment.
    # On utilise polars pour la rapidité et la facilité de manipulation des données.

    try:
        logger.info(
            f"Lecture du fichier parquet ({os.getenv('DATA_FILE_PARQUET_PATH')})..."
        )
        ddf: pl.DataFrame = pl.read_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))
    except ComputeError:
        # Le fichier est probablement en cours de mise à jour
        logger.info("Échec, nouvelle tentative dans 10s...")
        sleep(10)
        ddf: pl.DataFrame = pl.read_parquet(os.getenv("DATA_FILE_PARQUET_PATH"))
    return ddf


df = get_decp_data()
