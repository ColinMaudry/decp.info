import json
import logging
import os
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from time import localtime

import polars as pl
import polars.selectors as cs
from dash import no_update
from httpx import HTTPError, get, post
from unidecode import unidecode

from src.db import conn as duckdb_conn  # noqa: F401  (exposed for convenience)
from src.db import get_cursor, query_marches, schema  # noqa: F401

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("decp.info")
DEVELOPMENT = os.getenv("DEVELOPMENT", "False").lower() == "true"
if DEVELOPMENT:
    logger.setLevel(logging.DEBUG)

logging.getLogger("httpx").setLevel("WARNING")


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


def filter_table_data(
    lff: pl.LazyFrame, filter_query: str, filter_source: str
) -> pl.LazyFrame:
    _schema = lff.collect_schema()
    track_search(filter_query, filter_source)
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


def track_search(query, category):
    if len(query) >= 4 and not DEVELOPMENT and os.getenv("MATOMO_DOMAIN"):
        url = "https://decp.info"
        params = {
            "idsite": os.getenv("MATOMO_ID_SITE"),
            "url": url,
            "rec": "1",
            "action_name": "search" if category == "home_page_search" else "filter",
            "search_cat": category,
            "rand": uuid.uuid4().hex,
            "apiv": "1",
            "h": localtime().tm_hour,
            "m": localtime().tm_min,
            "s": localtime().tm_sec,
            "search": query,
            "token_auth": os.getenv("MATOMO_TOKEN"),
        }
        post(
            url=f"https://{os.getenv('MATOMO_DOMAIN')}/matomo.php",
            params=params,
        ).raise_for_status()


def search_org(dff: pl.DataFrame, query: str, org_type: str) -> pl.DataFrame:
    """
    Search in either 'acheteur' or 'titulaire' DataFrame.

    :param dff: Polars DataFrame with acheteur or titulaire columns
    :param query: User search string
    :param org_type: 'acheteur' or 'titulaire'
    :return: Filtered DataFrame with 'matches' column
    """
    if not query.strip():
        return dff.select(pl.lit(False).alias("matches"))

    # Enregistrement des recherche dans Matomo
    track_search(query, "home_page_search")

    # Normalize query
    normalized_query = unidecode(query.strip()).upper()
    tokens = [" " + t.strip() for t in normalized_query.split() if t.strip()]

    # Define columns based on entity type
    cols = [
        f"{org_type}_id",
        f"{org_type}_nom",
        f"{org_type}_departement_nom",
        f"{org_type}_departement_code",
        f"{org_type}_commune_nom",
    ]

    # Concatenate all fields into one string per row
    org_str = pl.concat_str(pl.lit(" "), pl.col(cols), separator=" ").str.replace(
        "-", " "
    )

    # For each token, create a boolean column: True if token is found
    token_matches = []
    for token in tokens:
        token_match = org_str.str.contains(token).alias(f"token_{token}")
        token_matches.append(token_match)

    # Count how many tokens match per row
    match_score = pl.sum_horizontal(token_matches).alias("match_score")

    # For each token, create a boolean column: True if token is found
    token_matches = []
    for token in tokens:
        token_match = org_str.str.contains(token).alias(f"token_{token}")
        token_matches.append(token_match)

    # Sélection des colonnes
    if org_type == "acheteur":
        dff = dff.select(cols + ["Marchés"])
    if org_type == "titulaire":
        dff = dff.select(cols + ["Marchés", "titulaire_typeIdentifiant"])

    # Apply and filter
    dff = (
        dff.with_columns(token_matches + [match_score])
        .filter(pl.col("match_score") == len(tokens))
        .drop([f"token_{token}" for token in tokens])
    )

    # Format result
    dff = add_links(dff)
    dff = dff.with_columns(
        pl.concat_str(
            pl.col(f"{org_type}_departement_nom"),
            pl.lit(" ("),
            pl.col(f"{org_type}_departement_code"),
            pl.lit(")"),
        ).alias("Département")
    )

    dff = dff.select(f"{org_type}_id", f"{org_type}_nom", "Département", "Marchés")
    dff = dff.group_by(f"{org_type}_id", f"{org_type}_nom", "Département").sum()
    dff = dff.sort("Marchés", descending=True)

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


def get_button_properties(height):
    if height > 65000:
        download_disabled = True
        download_text = "Téléchargement désactivé au-delà de 65 000 lignes"
        download_title = " Ajoutez des filtres pour réduire le nombre de lignes, Excel ne supporte pas d'avoir plus de 65 000 URLs dans une même feuille de calcul."
    elif height == 0:
        download_disabled = True
        download_text = "Pas de données à télécharger"
        download_title = ""
    else:
        download_disabled = False
        download_text = "Télécharger au format Excel"
        download_title = "Télécharger les données telles qu'affichées au format Excel"
    return download_disabled, download_text, download_title


def get_enum_values_as_dict(column_name):
    try:
        options = {}
        for value in DATA_SCHEMA[column_name]["enum"]:
            options[value] = value
        return options
    except KeyError:
        return {"not_found": "not found"}


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


def make_org_jsonld(org_id, org_type, org_name=None, type_org_id="SIRET") -> dict:
    org_types = {"acheteur": "GovernmentOrganization", "titulaire": "Organization"}
    address = None
    if type_org_id.lower() == "siret" and len(org_id) == 14:
        annuaire_data = get_annuaire_data(org_id)
        annuaire_address = annuaire_data["matching_etablissements"][0]
        code_postal = annuaire_address["code_postal"]
        commune = annuaire_address["libelle_commune"]

        address = (
            {
                "@type": "PostalAddress",
                "streetAddress": annuaire_address.get("adresse", "")
                .replace(code_postal, "")
                .replace(commune, "")
                .strip(),
                "addressLocality": commune,
                "postalCode": code_postal,
                "addressCountry": "FR",
            },
        )

    jsonld = {
        "@type": org_types[org_type],
        "name": org_name,
        "url": f"https://decp.info/{org_type}s/{org_id}",
        "sameAs": f"https://annuaire-entreprises.data.gouv.fr/etablissement/{org_id}",
        "identifier": {
            "@type": "PropertyValue",
            "propertyID": type_org_id.lower(),
            "value": org_id,
        },
    }

    if address:
        jsonld["address"] = address

    return jsonld


# df_acheteurs / df_titulaires sont conservés en mémoire pour alimenter
# la recherche sur la page d'accueil (autocomplétion, filtrage par sous-chaîne
# à chaque frappe). Les colonnes reproduisent la sortie historique de
# get_org_data(df, org_type).
def _build_org_frame(org_type: str) -> pl.DataFrame:
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


DF_ACHETEURS = _build_org_frame("acheteur")
DF_TITULAIRES = _build_org_frame("titulaire")

COLUMNS = schema.names()

DEPARTEMENTS = get_departements()
DEPARTEMENTS_GEOJSON = get_departements_geojson()
DOMAIN_NAME = (
    "test.decp.info" if os.getenv("DEVELOPMENT").lower() == "true" else "decp.info"
)
META_CONTENT = {
    "image_url": f"https://{DOMAIN_NAME}/assets/decp.info.png",
    "title": "decp.info - exploration des marchés publics français",
    "description": (
        "Explorez et analysez les données des marchés publics français avec cet outil libre et gratuit. "
        "Pour une commande publique accessible à toutes et tous."
    ),
}
DATA_SCHEMA = get_data_schema()
