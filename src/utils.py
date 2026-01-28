import json
import logging
import os
import uuid
from time import localtime, sleep

import polars as pl
import polars.selectors as cs
from httpx import get, post
from polars.exceptions import ComputeError
from unidecode import unidecode

logger = logging.getLogger("decp.info")
logging.getLogger("httpx").setLevel("WARNING")

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


def split_filter_part(filter_part):
    operators = [
        ["s<", "<"],
        ["s>", ">"],
        ["i<", "<"],
        ["i>", ">"],
        ["icontains", "contains"],
        # [" ", "contains"]
    ]
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


def add_links(dff: pl.DataFrame, target: str = "_blank"):
    for col in ["uid", "acheteur_nom", "titulaire_nom", "acheteur_id", "titulaire_id"]:
        if col in dff.columns:
            if col.startswith("titulaire_"):
                dff = dff.with_columns(
                    pl.when(
                        pl.Expr.or_(
                            pl.col("titulaire_typeIdentifiant").is_null(),
                            pl.col("titulaire_typeIdentifiant") == "SIRET",
                        )
                    )
                    .then(
                        '<a href = "/titulaires/'
                        + pl.col("titulaire_id")
                        + f'" target="{target}">'
                        + pl.col(col)
                        + "</a>"
                    )
                    .otherwise(pl.col(col))
                    .alias(col)
                )
            if col.startswith("acheteur_"):
                dff = dff.with_columns(
                    (
                        '<a href = "/acheteurs/'
                        + pl.col("acheteur_id")
                        + f'" target="{target}">'
                        + pl.col(col)
                        + "</a>"
                    ).alias(col)
                )
            if col == "uid":
                dff = dff.with_columns(
                    (
                        '<a href = "/marches/'
                        + pl.col("uid")
                        + f'" target="{target}">'
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
        "uid",
        cs.starts_with(org_type).exclude(
            f"{org_type}_latitude", f"{org_type}_longitude"
        ),
    )
    lff = lff.group_by(cs.starts_with(org_type)).len("Marchés")
    return lff.collect()


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
    track_search(filter_query)
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
    print(sort_by)
    return lff


def setup_table_columns(
    dff, hideable: bool = True, exclude: list = None, new_columns: list = None
) -> tuple:
    new_columns = new_columns or []

    # Liste finale de colonnes
    columns = []
    tooltip = {}
    for column_id in dff.columns:
        if exclude and column_id in exclude:
            continue
        column_object = data_schema.get(column_id)
        if column_object:
            column_name = column_object.get("title")
        else:
            if column_id not in new_columns:
                # Si le champ n'est pas dans le schéma et pas annoncé, on le skip
                print("Champ innatendu : ")
                print(dff[column_id].head())
            column_name = column_id
            column_object = {"title": column_name, "description": ""}

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
    else:
        displayed_columns = os.getenv("DISPLAYED_COLUMNS")
        if displayed_columns is None:
            raise ValueError("DISPLAYED_COLUMNS n'est pas configuré")
        else:
            displayed_columns = displayed_columns.replace(" ", "").split(",")

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

    new_schema = {}

    for col in original_schema["fields"]:
        new_schema[col["name"]] = col

    new_schema["sourceDataset"] = {
        "description": "Code de la source des données, avec un lien vers le fichier Open Data dont proviennent les données de ce marché public.",
        "title": "Source des données",
        "short_name": "Source",
    }
    return new_schema


def track_search(query):
    if (
        len(query) >= 4
        and os.getenv("DEVELOPMENT").lower != "true"
        and os.getenv("MATOMO_DOMAIN")
    ):
        if os.getenv("DEVELOPMENT").lower() == "true":
            url = "https://test.decp.info"
        else:
            url = "https://decp.info"
        params = {
            "idsite": os.getenv("MATOMO_ID_SITE"),
            "url": url,
            "rec": "1",
            "action_name": "front_page_search",
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
    track_search(query)

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
        .sort("Marchés", descending=True)
        .drop([f"token_{token}" for token in tokens])
    )

    # Format result
    dff = add_links(dff, target="")
    dff = dff.with_columns(
        pl.concat_str(
            pl.col(f"{org_type}_departement_nom"),
            pl.lit(" ("),
            pl.col(f"{org_type}_departement_code"),
            pl.lit(")"),
        ).alias("Département")
    )

    dff = dff.select(f"{org_type}_id", f"{org_type}_nom", "Département", "Marchés")

    return dff


def prepare_table_data(
    data, data_timestamp, filter_query, page_current, page_size, sort_by
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
    :return:
    """

    if os.getenv("DEVELOPMENT").lower() == "true":
        print(" + + + + + + + + + + + + + + + + + + ")

    # Récupération des données
    if isinstance(data, list):
        lff: pl.LazyFrame = pl.LazyFrame(data, strict=False, infer_schema_length=5000)
    else:
        lff: pl.LazyFrame = df.lazy()  # start from the original data

    # if search_params:
    #     if "filtres" in search_params:
    #         filter_query = search_params["filtres"][0]
    #
    #     if "tris" in search_params:
    #         try:
    #             sort_by = json.loads(search_params["tris"][0])
    #         except json.JSONDecodeError:
    #             pass
    #
    #     if "colonnes" in search_params:
    #         try:
    #             hidden_columns = json.loads(search_params["colonnes"][0])
    #             print(hidden_columns)
    #             lff = lff.drop(hidden_columns)
    #         except json.JSONDecodeError:
    #             pass

    # Application des filtres
    if filter_query:
        lff = filter_table_data(lff, filter_query)

    # Application des tris
    if len(sort_by) > 0:
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

    # Ajout des liens vers l'annuaire des entreprises
    dff = add_links(dff)

    # Ajout des liens vers les fichiers Open Data
    if "sourceFile" in dff.columns:
        dff = add_resource_link(dff)

    # Formatage des montants
    if height > 0:
        dff = format_values(dff)

    # Récupération des colonnes et tooltip
    columns, tooltip = setup_table_columns(dff)

    dicts = dff.to_dicts()

    # Propriétés du bouton de téléchargement
    download_disabled, download_text, download_title = get_button_properties(height)

    return (
        dicts,
        columns,
        tooltip,
        data_timestamp + 1,
        nb_rows,
        download_disabled,
        download_text,
        download_title,
    )


def get_button_properties(height):
    if height > 65000:
        download_disabled = True
        download_text = "Téléchargement désactivé au-delà de 65 000 lignes"
        download_title = "Excel ne supporte pas d'avoir plus de 65 000 URLs dans une même feuille de calcul. Contactez-moi pour me présenter votre besoin en téléchargement afin que je puisse adapter la solution."
    elif height == 0:
        download_disabled = True
        download_text = "Pas de données à télécharger"
        download_title = ""
    else:
        download_disabled = False
        download_text = "Télécharger au format Excel"
        download_title = ""
    return download_disabled, download_text, download_title


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


df: pl.DataFrame = get_decp_data()
schema = df.collect_schema()

df_acheteurs = get_org_data(df, "acheteur")
df_titulaires = get_org_data(df, "titulaire")
df_acheteurs_departement: pl.DataFrame = (
    df_acheteurs.select(["acheteur_id", "acheteur_nom", "acheteur_departement_code"])
    .unique()
    .sort("acheteur_nom")
)
df_titulaires_departement: pl.DataFrame = (
    df_titulaires.select(
        ["titulaire_id", "titulaire_nom", "titulaire_departement_code"]
    )
    .unique()
    .sort("titulaire_nom")
)
df_acheteurs_marches: pl.DataFrame = (
    df.select("uid", "objet", "acheteur_id").unique().sort("acheteur_id")
)
df_titulaires_marches: pl.DataFrame = (
    df.select("uid", "objet", "titulaire_id").unique().sort("titulaire_id")
)

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
