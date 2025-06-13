import polars as pl
import polars.selectors as cs

operators = [
    ["s<", "<"],
    ["s>", ">"],
    ["icontains", "contains"],
]


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
