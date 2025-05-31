import polars as pl

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
            + f' <a href="https://annuaire-entreprises.data.gouv.fr/etablissement/'
            + pl.col("titulaire_id")
            + '" target="_blank">📑</a>'
        )
        .otherwise(pl.col("titulaire_id"))
        .alias("titulaire_id")
    )
    df = df.with_columns(
        (
            pl.col("acheteur_id")
            + f' <a href="https://annuaire-entreprises.data.gouv.fr/etablissement/'
            + pl.col("acheteur_id")
            + '" target="_blank">📑</a>'
        ).alias("acheteur_id")
    )
    return df
