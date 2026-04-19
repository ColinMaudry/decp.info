import os
import uuid

import polars as pl
from dash import no_update
from polars import selectors as cs

from src.cache import cache
from src.db import query_marches, schema
from src.utils import logger
from src.utils.data import DATA_SCHEMA
from src.utils.frontend import get_button_properties
from src.utils.tracking import track_search  # noqa: F401


def split_filter_part(filter_part):
    operators = [
        ["s<", "<"],
        ["s>", ">"],
        ["i<", "<"],
        ["i>", ">"],
        ["icontains", "contains"],
        # [" ", "contains"]
    ]
    logger.debug("filter part " + filter_part)
    for operator_group in operators:
        if operator_group[0] in filter_part:
            name_part, value_part = filter_part.split(operator_group[0], 1)
            name_part = name_part.strip()
            value = value_part.strip()
            name = name_part[name_part.find("{") + 1 : name_part.rfind("}")]
            logger.debug("=> " + " ".join([name, operator_group[1], value]))

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
    for col in ["uid", "acheteur_nom", "titulaire_nom", "acheteur_id", "titulaire_id"]:
        if col in dff.columns:
            if col.startswith("titulaire_"):
                detail_link = (
                    '<a href = "/titulaires/'
                    + pl.col("titulaire_id")
                    + '">'
                    + pl.col(col)
                    + "</a>"
                )
                if col == "titulaire_nom":
                    detail_link = (
                        detail_link
                        + ' <a href="/observatoire?titulaire_id='
                        + pl.col("titulaire_id")
                        + '" title="Voir dans l\'observatoire">📊</a>'
                    )
                dff = dff.with_columns(
                    pl.when(
                        pl.Expr.or_(
                            pl.col("titulaire_typeIdentifiant").is_null(),
                            pl.col("titulaire_typeIdentifiant") == "SIRET",
                        )
                    )
                    .then(detail_link)
                    .otherwise(pl.col(col))
                    .alias(col)
                )
            if col.startswith("acheteur_"):
                detail_link = (
                    '<a href = "/acheteurs/'
                    + pl.col("acheteur_id")
                    + '">'
                    + pl.col(col)
                    + "</a>"
                )
                if col == "acheteur_nom":
                    detail_link = (
                        detail_link
                        + ' <a href="/observatoire?acheteur_id='
                        + pl.col("acheteur_id")
                        + '" title="Voir dans l\'observatoire">📊</a>'
                    )
                dff = dff.with_columns(detail_link.alias(col))
            if col == "uid":
                dff = dff.with_columns(
                    (
                        '<a href = "/marches/'
                        + pl.col("uid")
                        + '">'
                        + pl.col("uid")
                        + "</a>"
                    ).alias("uid")
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


def normalize_sort_by(sort_by) -> tuple:
    if not sort_by:
        return ()
    return tuple((entry["column_id"], entry["direction"]) for entry in sort_by)


def format_number(number) -> str:
    number = "{:,}".format(number).replace(",", " ")
    return number


def unformat_montant(number: str) -> float:
    number = number.replace(" €", "")
    number = number.replace(" €", "").replace(" ", "")
    number = number.replace(",", ".")
    number = number.strip()
    return float(number)


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
    if "titulaire_distance" in dff.columns:
        dff = dff.with_columns(
            pl.col("titulaire_distance")
            .pipe(format_distance)
            .alias("titulaire_distance")
        )

    return dff


def filter_table_data(
    lff: pl.LazyFrame, filter_query: str, filter_source: str
) -> pl.LazyFrame:
    _schema = lff.collect_schema()
    filtering_expressions = filter_query.split(" && ")
    for filter_part in filtering_expressions:
        col_name, operator, filter_value = split_filter_part(filter_part)
        col_type = str(_schema[col_name])
        # logger.debug("filter_value:", filter_value)
        # logger.debug("filter_value_type:", type(filter_value))
        # logger.debug("operator:", operator)
        # logger.debug("col_type:", col_type)

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
                    filter_value = filter_value.strip('"')
                    if filter_value.endswith("*"):
                        lff = lff.filter(
                            pl.col(col_name).str.starts_with(filter_value[:-1])
                        )
                    elif filter_value.startswith("*"):
                        lff = lff.filter(
                            pl.col(col_name).str.ends_with(filter_value[1:])
                        )
                    else:
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
    logger.debug(sort_by)
    return lff


def setup_table_columns(
    dff, hideable: bool = True, exclude: list = None, new_columns: list = None
) -> tuple:
    # Liste finale de colonnes
    markdown_exceptions = ["montant", "titulaire_distance", "distance", "dureeMois"]
    columns = []
    tooltip = {}
    for column_id in dff.columns:
        if exclude and column_id in exclude:
            continue
        column_object = DATA_SCHEMA.get(column_id)
        if column_object:
            column_name = column_object.get("title")
        else:
            # Si le champ est un champ créé par erreur lors d'une jointure, on le skip
            if column_id.endswith("_left") or column_id.endswith("_right"):
                logger.warning(f"Champ innatendu : {column_id}")
                continue
            column_name = column_id
            column_object = {"title": column_name, "description": ""}

        presentation = "input" if column_id in markdown_exceptions else "markdown"

        column = {
            "name": column_name,
            "id": column_id,
            "presentation": presentation,
            "type": "text",
            "format": {"nully": "N/A"},
            "hideable": hideable,
        }
        columns.append(column)
        if column_object:
            tooltip[column_id] = {
                "value": f"""**{column_object.get("title")}** ({column_id})

    """
                + column_object.get("description", ""),
                "type": "markdown",
            }
    return columns, tooltip


def get_default_hidden_columns(page):
    if page == "acheteur":
        displayed_columns = [
            "uid",
            "objet",
            "dateNotification",
            "titulaire_id",
            "titulaire_typeIdentifiant",
            "titulaire_nom",
            "titulaire_distance",
            "montant",
            "codeCPV",
            "dureeRestanteMois",
        ]
    elif page == "titulaire":
        displayed_columns = [
            "uid",
            "objet",
            "dateNotification",
            "acheteur_id",
            "acheteur_nom",
            "titulaire_distance",
            "montant",
            "codeCPV",
            "dureeRestanteMois",
        ]
    elif page == "tableau":
        displayed_columns = os.getenv("DISPLAYED_COLUMNS")
    else:
        displayed_columns = os.getenv("DISPLAYED_COLUMNS")
        logger.warning(f"Invalid page: {page}")

    hidden_columns = []

    for col in schema.names():
        if col in displayed_columns:
            continue
        else:
            hidden_columns.append(col)
    return hidden_columns


@cache.memoize()
def _load_filter_sort_postprocess(filter_query, sort_by_key):
    logger.debug(
        f"Cache miss — recomputing for filter={filter_query!r} sort={sort_by_key!r}"
    )

    lff: pl.LazyFrame = query_marches().lazy()

    if filter_query:
        lff = filter_table_data(lff, filter_query, "tableau")

    if sort_by_key:
        sort_by = [
            {"column_id": col, "direction": direction} for col, direction in sort_by_key
        ]
        lff = sort_table_data(lff, sort_by)

    lff = lff.cast(pl.String)
    lff = lff.fill_null("")

    dff: pl.DataFrame = lff.collect()

    dff = add_links(dff)
    if "sourceFile" in dff.columns:
        dff = add_resource_link(dff)
    if dff.height > 0:
        dff = format_values(dff)

    return dff


def prepare_table_data(
    data, data_timestamp, filter_query, page_current, page_size, sort_by, source_table
):
    """
    Fonction de préparation des données pour les datatables, afin de permettre une gestion fine des logiques,
    notamment pour les filtres et les tris.
    :param data
    :param data_timestamp:
    :param filter_query:
    :param page_current:
    :param page_size:
    :param sort_by:
    :param source_table:
    :return:
    """

    if os.getenv("DEVELOPMENT").lower() == "true":
        logger.debug(" + + + + + + + + + + + + + + + + + + ")

    trigger_cleanup = no_update

    # Récupération des données
    if isinstance(data, list):
        lff: pl.LazyFrame = pl.LazyFrame(data, strict=False, infer_schema_length=5000)
    elif isinstance(data, pl.LazyFrame):
        lff = data
    else:
        lff: pl.LazyFrame = query_marches().lazy()

    # Application des filtres
    if filter_query:
        lff = filter_table_data(lff, filter_query, source_table)
        trigger_cleanup = no_update if source_table == "tableau" else str(uuid.uuid4())

    # Application des tris
    if sort_by and len(sort_by) > 0:
        lff = sort_table_data(lff, sort_by)

    # Matérialisation des filtres
    dff: pl.DataFrame = lff.collect()
    height = dff.height

    if height > 0:
        nb_rows = f"{format_number(height)} lignes ({format_number(dff.select('uid').unique().height)} marchés)"
    else:
        nb_rows = "0 lignes (0 marchés)"

    # Pagination des données
    start_row = page_current * page_size
    # end_row = (page_current + 1) * page_size
    dff = dff.slice(start_row, page_size)

    # Tout devient string
    dff = dff.cast(pl.String)

    # Remplace les strings null par "", mais pas les numeric null
    dff = dff.fill_null("")

    # Ajout des liens vers les pages de détails
    dff = add_links(dff)

    # Ajout des liens vers les fichiers Open Data
    if "sourceFile" in dff.columns:
        dff = add_resource_link(dff)

    # Formatage des montants
    if height > 0:
        dff = format_values(dff)

    # Récupération des colonnes et tooltip
    table_columns, tooltip = setup_table_columns(dff)

    dicts = dff.to_dicts()

    # Propriétés du bouton de téléchargement
    download_disabled, download_text, download_title = get_button_properties(height)

    return (
        dicts,
        table_columns,
        tooltip,
        data_timestamp + 1,
        nb_rows,
        download_disabled,
        download_text,
        download_title,
        trigger_cleanup,
    )


def invert_columns(columns):
    """
    Renvoie les colonnes du schéma non spécifiées en paramètre. Utile pour passer d'une colonnes masquées à une liste de colonnes affichées, et vice versa.

    :param columns:
    :return:
    """
    inverted_columns = []
    for column in schema.names():
        if column not in columns:
            inverted_columns.append(column)
    return inverted_columns


COLUMNS = schema.names()
