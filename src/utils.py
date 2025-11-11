import json
import logging
import os
from time import sleep

import polars as pl
import polars.selectors as cs
from httpx import get
from polars import Schema
from polars.exceptions import ComputeError

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
        ).alias("sourceDataset")
    )
    dff = dff.drop(["sourceFile"])
    return dff


def add_links(dff: pl.DataFrame):
    dff = dff.with_columns(
        pl.when(pl.col("titulaire_typeIdentifiant") == "SIRET")
        .then(
            '<a href = "/titulaires/'
            + pl.col("titulaire_id")
            + '">'
            + pl.col("titulaire_id")
            + "</a>"
        )
        .otherwise(pl.col("titulaire_id"))
        .alias("titulaire_id")
    )

    for column, path in [("acheteur_id", "acheteurs"), ("uid", "marches")]:
        dff = dff.with_columns(
            (
                f'<a href = "/{path}/'
                + pl.col(column)
                + '" target="_blank">'
                + pl.col(column)
                + "</a>"
            ).alias(column)
        )
    return dff


def add_links_in_dict(data: list[dict], org_type: str) -> list:
    new_data = []
    for marche in data:
        org_id = marche[org_type + "_id"]
        marche[org_type + "_nom"] = (
            f'<a href="/{org_type}s/{org_id}">{marche[org_type + "_nom"]}</a>'
        )
        if marche.get("uid"):
            marche["id"] = f'<a href="/marches/{marche["uid"]}">{marche["id"]}</a>'
            marche["uid"] = f'<a href="/marches/{marche["uid"]}">{marche["uid"]}</a>'
        new_data.append(marche)
    return new_data


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


def dates_to_strings(lff: pl.LazyFrame, column: str) -> pl.LazyFrame:
    """
    Convert a date column to string type.
    """
    lff = lff.with_columns(pl.col(column).cast(pl.String).fill_null(""))
    return lff


def format_number(number) -> str:
    number = "{:,}".format(number).replace(",", " ")
    return number


def format_values(dff: pl.DataFrame) -> pl.DataFrame:
    def format_montant(expr, scale=None):
        # https://stackoverflow.com/a/78636786
        expr = expr.cast(pl.String)
        expr = expr.str.splitn(".", 2)

        num = expr.struct[0]
        frac = expr.struct[1]

        # Ajout des espaces
        num = (
            num.str.reverse()
            .str.replace_all(r"\d{3}", "$0 ")
            .str.reverse()
            .str.replace(r"^ ", "")
        )

        frac: pl.Expr = (
            pl.when(frac.is_not_null() & ~frac.is_in(["0"]))
            .then("," + frac.str.head(2))
            .otherwise(pl.lit(""))
        )

        montant: pl.Expr = (
            pl.when((num + frac) == pl.lit(""))
            .then(pl.lit(""))
            .otherwise(num + frac + pl.lit(" €"))
        )

        return montant

    def format_distance(expr):
        expr = expr.cast(pl.String)
        return pl.concat_str(expr, pl.lit(" km"))

    if "montant" in dff.columns:
        dff = dff.with_columns(pl.col("montant").pipe(format_montant).alias("montant"))
    if "distance" in dff.columns:
        dff = dff.with_columns(
            pl.col("distance").pipe(format_distance).alias("distance")
        )

    return dff


def get_annuaire_data(siret: str) -> dict:
    url = f"https://recherche-entreprises.api.gouv.fr/search?q={siret}"
    response = get(url)
    return response.json()["results"][0]


def get_decp_data() -> pl.DataFrame:
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

    return lff.collect()


def get_org_data(dff: pl.DataFrame, org_type: str) -> pl.DataFrame:
    lff = dff.lazy()
    lff = lff.select(
        cs.starts_with(org_type).exclude(
            f"{org_type}_latitude", f"{org_type}_longitude"
        )
    )
    lff = lff.unique(f"{org_type}_id")
    return lff.collect()


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
    debug = os.getenv("DEVELOPMENT", "False").lower() == "true"
    schema = lff.collect_schema()
    filtering_expressions = filter_query.split(" && ")
    for filter_part in filtering_expressions:
        col_name, operator, filter_value = split_filter_part(filter_part)
        col_type = str(schema[col_name])
        if debug:
            print("filter_value:", filter_value)
            print("filter_value_type:", type(filter_value))
            print("operator:", operator)
            print("col_type:", col_type)

        lff = lff.filter(pl.col(col_name).is_not_null())

        if col_type == "Date":
            # Convertir la colonne date en chaînes de caractères
            lff = dates_to_strings(lff, col_name)
            col_type = "String"
        if col_type == "String":
            lff = lff.filter(pl.col(col_name) != pl.lit(""))

        elif col_type.startswith("Int") or col_type.startswith("Float"):
            try:
                filter_value = int(filter_value)
            except ValueError:
                logger.error(f"Invalid numeric filter value: {filter_value}")
                continue

        if operator in ("contains", "<", "<=", ">", ">="):
            if operator == "<":
                lff = lff.filter(pl.col(col_name) < filter_value)
            elif operator == ">":
                lff = lff.filter(pl.col(col_name) > filter_value)
            elif operator == ">=":
                lff = lff.filter(pl.col(col_name) >= filter_value)
            elif operator == "<=":
                lff = lff.filter(pl.col(col_name) <= filter_value)
            elif operator == "contains":
                if col_type in ["String", "Date"]:
                    lff = lff.filter(
                        pl.col(col_name).str.contains("(?i)" + filter_value)
                    )
                elif col_type.startswith("Int") or col_type.startswith("Float"):
                    lff = lff.filter(pl.col(col_name) == filter_value)
                else:
                    logger.error(f"Invalid column type: {col_type}")
        else:
            logger.error(f"Invalid operator: {operator}")

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


def setup_table_columns(dff, hideable: bool = True, exclude: list = None) -> tuple:
    # Liste finale de colonnes
    columns = []
    tooltip = {}
    for column_id in dff.columns:
        if exclude and column_id in exclude:
            continue
        column_object = data_schema.get(column_id)
        if column_object:
            column_name = column_object.get("title", column_id)
        else:
            column_name = column_id

        column = {
            "name": column_name,
            "id": column_id,
            "presentation": "markdown",
            "type": "text",
            "format": {"nully": "N/A"},
            "hideable": hideable,
        }
        columns.append(column)

        if column_object:
            tooltip[column_id] = {
                "value": f"""**{column_object.get("title")}** ({column_id})

    """
                + column_object["description"],
                "type": "markdown",
            }
    return columns, tooltip


def get_default_hidden_columns(schema: Schema):
    displayed_columns = os.getenv("DISPLAYED_COLUMNS")
    hidden_columns = []
    if displayed_columns:
        displayed_columns = displayed_columns.replace(" ", "").split(",")
        for col in schema.names():
            if col in displayed_columns:
                continue
            else:
                hidden_columns.append(col)
        return hidden_columns
    raise ValueError("DISPLAYED_COLUMNS n'est pas configuré")


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

    new_schema = {}

    for col in original_schema["fields"]:
        new_schema[col["name"]] = col

    new_schema["sourceDataset"] = {
        "description": "Code de la source des données, avec un lien vers le fichier Open Data dont proviennent les données de ce marché public.",
        "title": "Source des données",
        "short_name": "Source",
    }
    return new_schema


df: pl.DataFrame = get_decp_data()
df_acheteurs = get_org_data(df, "acheteur")
df_titulaires = get_org_data(df, "titulaire")
departements = get_departements()
domain_name = (
    "test.decp.info" if os.getenv("DEVELOPMENT").lower() == "true" else "decp.info"
)
meta_content = {
    "image_url": f"https://{domain_name}/assets/decp.info.png",
    "title": "decp.info - exploration des marchés publics français",
    "description": (
        "Explorez et analysez les données des marchés publics français avec cet outil libre et gratuit. "
        "Pour une commande publique accessible à toutes et tous."
    ),
}
data_schema = get_data_schema()
