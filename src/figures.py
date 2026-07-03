from datetime import datetime
from typing import Literal

import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_leaflet.express as dlx
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from dash import dash_table, dcc, html
from dash_extensions.javascript import Namespace
from polars.exceptions import ColumnNotFoundError

from src.db import schema
from src.utils import logger
from src.utils.data import DATA_SCHEMA, DEPARTEMENTS_GEOJSON
from src.utils.table import add_links, format_number, setup_table_columns


def get_yearly_statistics(statistics, today_str) -> html.Div:
    # Build DataFrame from statistics
    years = list(reversed(range(2018, int(today_str.split("/")[-1]) + 1)))
    data = []
    for year in years:
        year_str = str(year)
        stat = statistics[year_str]
        data.append(
            {
                "Année": year_str,
                "Marchés et accord-cadres": format_number(
                    stat["nb_notifications_marches"]
                ),
                "Acheteurs": format_number(stat["nb_acheteurs_uniques"]),
                "Titulaires": format_number(stat["nb_titulaires_uniques"]),
            }
        )

    dff = pl.DataFrame(data)

    # Create Dash DataTable
    table = dash_table.DataTable(
        data=dff.to_dicts(),
        columns=[
            {"name": "Année", "id": "Année"},
            {"name": "Marchés et accord-cadres", "id": "Marchés et accord-cadres"},
            {"name": "Acheteurs", "id": "Acheteurs"},
            {"name": "Titulaires", "id": "Titulaires"},
        ],
        page_size=10,
        sort_action="none",
        filter_action="none",
        style_header={"fontFamily": "Inter", "fontSize": "16px"},
        style_cell={"fontFamily": "Inter", "fontSize": "16px"},
    )

    return html.Div(children=table, className="marches_table")


def get_barchart_sources(lff: pl.LazyFrame, type_date: str):
    labels = {
        "dateNotification": "notification",
        "datePublicationDonnees": "publication des données",
    }

    now_year = datetime.now().year

    lff = lff.select("uid", type_date, "sourceDataset")

    lff = lff.unique("uid")

    # Rassemblement des datasets Atexo pour ne pas surcharger le graphique
    lff = lff.with_columns(
        pl.when(pl.col("sourceDataset").str.starts_with("atexo"))
        .then(pl.lit("plateformes atexo"))
        .otherwise(pl.col("sourceDataset"))
        .alias("sourceDataset")
    )

    # Rassemblement des datasets AWS pour ne pas surcharger le graphique
    lff = lff.with_columns(
        pl.when(pl.col("sourceDataset").str.contains(r"aws|marches\-publics.info"))
        .then(pl.lit("aws"))
        .otherwise(pl.col("sourceDataset"))
        .alias("sourceDataset")
    )

    lff = lff.with_columns(pl.col(type_date).dt.year().alias("annee"))
    lff = lff.filter(
        pl.col(type_date).is_not_null() & pl.col("annee").is_between(2019, now_year)
    )
    lff = lff.with_columns(pl.col(type_date).cast(pl.String).str.head(7))
    lff = (
        lff.group_by([type_date, "sourceDataset"])
        .len()
        .sort(by=[type_date, "len"], descending=True)
    )

    lff = lff.sort(by=["sourceDataset"], descending=False)

    dff: pl.DataFrame = lff.collect(engine="streaming")

    fig = px.bar(
        dff,
        x=type_date,
        y="len",
        color="sourceDataset",
        labels={
            "len": "Nombre de marchés",
            type_date: f"Mois de {labels[type_date]}",
            "sourceDataset": "Source de données",
        },
    )

    graph = dcc.Graph(figure=fig)

    return graph


def get_sources_tables(source_path) -> html.Div:
    try:
        if not source_path:
            raise ValueError("SOURCE_STATS_CSV_PATH non défini")
        dff = pl.read_csv(source_path)
    except Exception as e:
        logger.warning(f"Sources de données indisponibles ({e})")
        return html.Div("Sources de données momentanément indisponibles.")
    dff = dff.with_columns(
        (
            pl.lit('<a href = "')
            + pl.col("url")
            + pl.lit('">')
            + pl.col("nom")
            + pl.lit("</a>")
        ).alias("nom"),
    )
    dff = dff.drop("url", "unique")
    dff = dff.sort(by=["nb_marchés"], descending=True)
    dff = dff.with_columns(
        pl.col("nb_marchés").map_elements(format_number, return_dtype=pl.String),
        pl.col("nb_acheteurs").map_elements(format_number, return_dtype=pl.String),
    )

    columns = {
        "nom": "Nom de la source",
        "organisation": "Responsable de publication",
        "nb_marchés": "Nb de marchés",
        "nb_acheteurs": "Nb d'acheteurs",
        "code": "Code",
    }

    datatable = dash_table.DataTable(
        id="source_table",
        data=dff.to_dicts(),
        columns=[
            {
                "name": columns[i],
                "id": i,
                "presentation": "markdown",
                "type": "text",
                "format": {"nully": "N/A"},
            }
            for i in dff.schema.names()
        ],
        style_cell_conditional=[
            {
                "if": {"column_id": ["nom", "organisation"]},
                "minWidth": "220px",
                "textAlign": "left",
                "overflow": "hidden",
                "lineHeight": "14px",
                "whiteSpace": "normal",
            },
        ],
        sort_action="native",
        markdown_options={"html": True},
        style_header={"fontFamily": "Inter", "fontSize": "16px"},
        style_cell={"fontFamily": "Inter", "fontSize": "16px"},
    )

    return html.Div(children=datatable)


class DataTable(dash_table.DataTable):
    def __init__(
        self,
        dtid: str,
        hidden_columns: list[str] | None = None,
        data: list[dict[str, str | int | float | bool]] | None = None,
        columns: list[dict[str, str]] | None = None,
        page_size: int = 20,
        page_action: Literal["native", "custom", "none"] = "native",
        sort_action: Literal["native", "custom", "none"] = "native",
        filter_action: Literal["native", "custom", "none"] = "native",
        style_cell_conditional: list | None = None,
        style_cell: dict | None = None,
        **kwargs,
    ):
        # Styles de base
        style_cell_conditional_common = [
            {
                "if": {"column_id": "objet"},
                "minWidth": "350px",
                "overflow": "hidden",
                "lineHeight": "18px",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "acheteur_id"},
                "minWidth": "160px",
                "overflow": "hidden",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "acheteur_nom"},
                "minWidth": "250px",
                "overflow": "hidden",
                "lineHeight": "18px",
                "whiteSpace": "normal",
            },
            {
                "if": {"column_id": "titulaire_nom"},
                "minWidth": "250px",
                "overflow": "hidden",
                "lineHeight": "18px",
                "whiteSpace": "normal",
            },
        ]

        style_cell_common = {"fontFamily": "Inter", "fontSize": "16px"}

        for key in DATA_SCHEMA.keys():
            field = DATA_SCHEMA[key]
            if field["type"] in ["number", "integer"]:
                rule = {
                    "if": {"column_id": field["name"]},
                    "textAlign": "right",
                    # "fontFamily": "Fira Code",
                }
                style_cell_conditional_common.append(rule)

        style_cell_conditional = (
            style_cell_conditional or []
        ) + style_cell_conditional_common
        if style_cell:
            style_cell.update(style_cell_common)
        else:
            style_cell = style_cell_common
        style_header = style_cell

        # Initialisation de la classe parente avec les arguments
        super().__init__(
            id=dtid,
            data=data,
            columns=columns,
            cell_selectable=False,
            page_size=page_size,
            filter_action=filter_action,
            page_action=page_action,
            filter_options={
                "case": "insensitive",
                "placeholder_text": "Filtre de colonne...",
            },
            sort_action=sort_action,
            sort_mode="multi",
            row_deletable=False,
            page_current=0,
            style_cell_conditional=style_cell_conditional,
            data_timestamp=0,
            markdown_options={"html": True},
            style_header=style_header,
            style_cell=style_cell,
            tooltip_duration=8000,
            tooltip_delay=350,
            hidden_columns=hidden_columns,
            **kwargs,  # Possibilité de remplacer des arguments
        )


def get_duplicate_matrix() -> dcc.Graph:
    """
    Fonction développée avec l'aide de la LLM Euria d'Infomaniak.
    :return:
    """
    lff = pl.scan_parquet(
        "https://www.data.gouv.fr/api/1/datasets/r/a545bf6c-8b24-46ed-b49f-a32bf02eaffa"
    ).sort("sourceDataset")
    lff = lff.select(
        ["sourceDataset", "unique"] + sorted(lff.collect_schema().names()[2:])
    )

    dff = lff.collect()

    # Extract data
    z_data = dff.select(pl.all().exclude("sourceDataset")).fill_null(0).to_numpy()
    x_labels = dff.columns[1:]  # columns after "sourceDataset"
    y_labels = dff["sourceDataset"].to_list()

    # Create heatmap
    fig = go.Figure(
        data=go.Heatmap(
            z=z_data,
            x=x_labels,
            y=y_labels,
            colorscale=[
                [0.0, "white"],  # 0% → white
                [0.10, "lightsalmon"],  # 10% → light warm tone
                [1.0, "darkred"],  # 100% → deep red
            ],
            zmin=0,
            zmax=1,
            hoverongaps=False,
            showscale=True,
            hovertemplate=(
                "<b>%{z:.0%}</b> des marchés présents dans <b>%{y}</b> sont également présents dans <b>%{x}</b>"
            ),
        )
    )

    # Update layout: make it wider and taller
    fig.update_layout(
        title="",
        xaxis_title="Sources de données",
        yaxis_title="Sources de données",
        yaxis=dict(autorange="reversed"),
        xaxis=dict(tickangle=45, tickfont=dict(size=10)),  # Smaller x-tick labels
        coloraxis_colorbar=dict(title="Percentage", tickfont=dict(size=10)),
        width=1000,  # Wider
        height=1000,  # Taller
        font=dict(size=11),  # Overall font size
        margin=dict(l=100, r=50, t=80, b=100),  # Add margin for labels
    )

    return dcc.Graph(figure=fig)


ORG_COLORS = {
    "acheteur": "#E69F00",  # orange
    "titulaire": "#56B4E9",  # bleu ciel
}


def build_org_markers(
    lff: pl.LazyFrame, org_type: Literal["acheteur", "titulaire"]
) -> list[dict]:
    """Regroupe les marchés par point géographique pour un type d'organisme.

    Renvoie [] (sans exception) si les colonnes longitude/latitude de ce
    type sont absentes du LazyFrame (ex: tests/test.parquet).
    """
    lon_col = f"{org_type}_longitude"
    lat_col = f"{org_type}_latitude"
    nom_col = f"{org_type}_nom"

    available = set(lff.collect_schema().names())
    if lon_col not in available or lat_col not in available:
        return []

    lff_org = (
        lff.select("uid", lon_col, lat_col, nom_col)
        .group_by(lon_col, lat_col, nom_col)
        .len("nb_marches")
        .filter(pl.col(lat_col).is_not_null() & pl.col(lon_col).is_not_null())
    )

    return [
        {
            "lat": row[lat_col],
            "lon": row[lon_col],
            "tooltip": f"{row[nom_col]} ({row['nb_marches']} marchés)",
            "marker_color": ORG_COLORS[org_type],
        }
        for row in lff_org.collect().to_dicts()
    ]


def get_geographic_maps(dff: pl.DataFrame) -> list[dbc.Col] | list:
    """
    Génère les cartes géographiques pour l'hexagone et les DOM-TOM.
    """

    regions: dict = {
        "Hexagone": {
            "coordinates": [46.6, 2.2],
            "zoom_leaflet": 5,
            "zoom_chloropleth": 1,
            "name": "Hexagone",
        },
        "971": {
            "coordinates": [16.23, -61.55],
            "zoom_leaflet": 9,
            "zoom_chloropleth": 1,
            "name": "Guadeloupe",
        },
        "972": {
            "coordinates": [14.64, -61.02],
            "zoom_leaflet": 10,
            "zoom_chloropleth": 1,
            "name": "Martinique",
        },
        "973": {
            "coordinates": [3.93, -53.12],
            "zoom_leaflet": 7,
            "zoom_chloropleth": 1,
            "name": "Guyane",
        },
        "974": {
            "coordinates": [-21.11, 55.53],
            "zoom_leaflet": 9,
            "zoom_chloropleth": 1,
            "name": "La Réunion",
        },
        "976": {
            "coordinates": [-12.82, 45.16],
            "zoom_leaflet": 10,
            "zoom_chloropleth": 1,
            "name": "Mayotte",
        },
    }

    def make_map_data(region_code: str) -> tuple[list, str | None]:
        lff: pl.LazyFrame = dff.lazy()
        if region_code == "Hexagone":
            lff = lff.filter(
                (pl.col("acheteur_departement_code").str.len_chars() == 2)
                & (pl.col("titulaire_departement_code").str.len_chars() == 2)
            )
        else:
            lff = lff.filter(
                (pl.col("acheteur_departement_code") == code)
                | (pl.col("titulaire_departement_code") == code)
            )

        nb_marches = lff.select("uid").collect()["uid"].n_unique()

        if nb_marches == 0:
            return [], None

        dfs = []

        if (code == "Hexagone" and nb_marches > 30000) or (
            code != "Hexagone" and nb_marches > 10000
        ):
            _map_type: str = "chloropleth"

            lff = lff.rename({"acheteur_departement_code": "Département"})
            lff = (
                lff.select(["uid", "Département"])
                .drop_nulls()
                .group_by("uid")
                .agg(pl.col("Département").first())
                .group_by("Département")
                .len("uid")
            )
            dfs.append(lff.collect())
        else:
            _map_type: str = "clusters"
            for org_type in ["acheteur", "titulaire"]:
                dfs.append(build_org_markers(lff, org_type))

        return dfs, _map_type

    cols = []

    for code in regions.keys():
        regions[code]["data"], map_type = make_map_data(code)

        if map_type == "chloropleth":
            map_graph = make_chloropleth_map(regions[code])
        elif map_type == "clusters":
            map_graph = make_clusters_map(regions[code])
        elif map_type is None:
            continue
        else:
            raise ValueError(f"Map type '{map_type}' not recognised")

        lg, xl = (12, 8) if code == "Hexagone" else (6, 4)

        col = make_card(regions[code]["name"], fig=map_graph, lg=lg, xl=xl)
        cols.append(col)

    return cols


def make_chloropleth_map(region: dict) -> dcc.Graph:
    df_map = region["data"][0]

    fig = px.choropleth(
        df_map,
        geojson=DEPARTEMENTS_GEOJSON,
        locations="Département",
        color="uid",
        color_continuous_scale="Reds",
        range_color=(df_map["uid"].min(), df_map["uid"].max()),
        labels={"uid": "Marchés attribués"},
        scope="europe",
    )

    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        mapbox={
            "style": "carto-positron",
            "center": {"lon": 10, "lat": 10},
            "zoom": 8,
            "domain": {"x": [0, 1], "y": [0, 1]},
        }
    )

    graph = dcc.Graph(figure=fig, config={"displayModeBar": False})
    return graph


def make_clusters_map(region: dict) -> dl.Map:
    # JavaScript functions for styling
    ns = Namespace("dash_clientside", "leaflet")
    point_to_layer = ns("pointToLayer")
    cluster_to_layer = ns("clusterToLayer")

    name = region["name"]

    # Données de la région
    region_acheteurs = region["data"][0]
    region_titulaires = region["data"][1]

    # Couleurs
    color_acheteur = ORG_COLORS["acheteur"]
    color_titulaire = ORG_COLORS["titulaire"]

    acheteurs_geojson_data = dlx.dicts_to_geojson(region_acheteurs)
    titulaires_geojson_data = dlx.dicts_to_geojson(region_titulaires)

    center, zoom = region["coordinates"], region["zoom_leaflet"]
    region_id = name.lower().replace(" ", "-")
    leaflet_map = dl.Map(
        [
            dl.TileLayer(),
            dl.GeoJSON(
                data=titulaires_geojson_data,
                cluster=True,
                zoomToBoundsOnClick=True,
                pointToLayer=point_to_layer,
                clusterToLayer=cluster_to_layer,
                id=f"geojson-{region_id}-titulaires",
                options={"fillColor": color_titulaire},
            ),
            dl.GeoJSON(
                data=acheteurs_geojson_data,
                cluster=True,
                zoomToBoundsOnClick=True,
                pointToLayer=point_to_layer,
                clusterToLayer=cluster_to_layer,
                id=f"geojson-{region_id}-acheteurs",
                options={"fillColor": color_acheteur},
            ),
        ],
        center=center,
        zoom=zoom,
        style={
            "width": "100%",
            "height": "400px" if name == "Hexagone" else "300px",
        },
        id=f"map-{region_id}",
    )
    return leaflet_map


def get_org_location_map(
    dff: pl.DataFrame,
    home_type: Literal["acheteur", "titulaire"],
    map_id: str,
) -> dl.Map:
    """Carte cluster (dash-leaflet) d'un organisme et de sa contrepartie.

    Affiche les marchés de `home_type` (fiche /acheteur ou /titulaire
    consultée) ainsi que ceux de son type complémentaire, clusterisés et
    colorés comme sur /observatoire. Cadrage automatique (fitBounds) sur
    l'ensemble des points ; repli sur une vue France fixe si aucun point
    n'est disponible.
    """
    lff = dff.lazy()
    markers_by_type = {
        "acheteur": build_org_markers(lff, "acheteur"),
        "titulaire": build_org_markers(lff, "titulaire"),
    }

    ns = Namespace("dash_clientside", "leaflet")
    point_to_layer = ns("pointToLayer")
    cluster_to_layer = ns("clusterToLayer")

    layers: list = [dl.TileLayer()]
    all_points: list[tuple[float, float]] = []
    # Ordre fixe (titulaire puis acheteur) pour que l'organisme consulté
    # soit toujours peint au-dessus de sa contrepartie, comme sur /observatoire.
    for org_type in ("titulaire", "acheteur"):
        markers = markers_by_type[org_type]
        if not markers:
            continue
        all_points.extend((m["lat"], m["lon"]) for m in markers)
        layers.append(
            dl.GeoJSON(
                data=dlx.dicts_to_geojson(markers),
                cluster=True,
                zoomToBoundsOnClick=True,
                pointToLayer=point_to_layer,
                clusterToLayer=cluster_to_layer,
                id=f"{map_id}-{org_type}",
                options={"fillColor": ORG_COLORS[org_type]},
            )
        )

    map_kwargs: dict = {}
    if all_points:
        lats = [lat for lat, _ in all_points]
        lons = [lon for _, lon in all_points]
        map_kwargs["bounds"] = [[min(lats), min(lons)], [max(lats), max(lons)]]
        map_kwargs["boundsOptions"] = {"padding": [30, 30], "maxZoom": 12}
    else:
        map_kwargs["center"] = [46.6, 2.2]
        map_kwargs["zoom"] = 5

    return dl.Map(
        layers,
        style={"width": "100%", "height": "300px"},
        id=map_id,
        **map_kwargs,
    )


def get_distance_histogram(lff: pl.LazyFrame) -> dcc.Graph:
    if "titulaire_distance" not in lff.collect_schema().names():
        dff = pl.DataFrame({"titulaire_distance": pl.Series([], dtype=pl.Float64)})
    else:
        dff = (
            lff.select("titulaire_distance")
            .drop_nulls()
            .filter(pl.col("titulaire_distance") > 0)
            .collect(engine="streaming")
        )
    log_distances = dff["titulaire_distance"].log(10).to_numpy()

    fig = go.Figure()
    if len(log_distances) > 0:
        counts, bin_edges = np.histogram(log_distances, bins=25)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_widths = bin_edges[1:] - bin_edges[:-1]
        bin_edges_km = 10.0**bin_edges

        def fmt_km(km):
            if km < 10:
                return f"{km:.1f}"
            elif km < 1000:
                return f"{round(km)}"
            else:
                return f"{round(km):,}".replace(",", " ")

        hover_texts = []
        for i in range(len(counts)):
            nb = f"{counts[i]:,}".replace(",", " ")
            hover_texts.append(
                f"Distance : {fmt_km(bin_edges_km[i])} – {fmt_km(bin_edges_km[i + 1])} km"
                f"<br>Nombre de marchés : {nb}"
            )

        fig.add_trace(
            go.Bar(
                x=bin_centers,
                y=counts,
                width=bin_widths,
                hovertext=hover_texts,
                hoverinfo="text",
            )
        )
        fig.update_layout(bargap=0)

    fig.update_layout(margin=dict(r=10, t=10), height=450)
    fig.update_xaxes(
        tickvals=[0, 1, 2, 3, 4],
        ticktext=["1", "10", "100", "1 000", "10 000"],
        title_text="Distance (km)",
    )
    fig.update_yaxes(title_text="Nombre de marchés")
    return dcc.Graph(figure=fig)


def get_dashboard_summary_table(dff, dff_per_uid, nb_marches):
    nb_acheteurs = dff.select("acheteur_id").n_unique()
    nb_titulaires = dff.select("titulaire_id", "titulaire_typeIdentifiant").n_unique()
    total_montant = int(dff_per_uid.select(pl.col("montant").sum()).item())
    median_distance = dff.select(pl.median("titulaire_distance")).item()

    summary_table = [
        html.P(["Nombre de marchés : ", html.Strong(str(format_number(nb_marches)))]),
        html.P(
            [
                "Nombre d'acheteurs uniques : ",
                html.Strong(str(format_number(nb_acheteurs))),
            ]
        ),
        html.P(
            [
                "Nombre de titulaires uniques : ",
                html.Strong(str(format_number(nb_titulaires))),
            ]
        ),
        html.P(
            [
                "Montant total (",
                html.Span(
                    "?",
                    id={"type": "modal-trigger", "index": "montant"},
                    style={"cursor": "pointer", "textDecoration": "underline dotted"},
                ),
                ") : ",
                html.Strong(format_number(total_montant) + " €"),
            ]
        ),
        html.P(
            [
                "Distance acheteur-titulaire médiane : ",
                html.Strong(format_number(median_distance) + " km"),
            ]
        ),
    ]

    return summary_table


CONSIDERATIONS_REGEX = r"(?i)Clause|Critère|Marché réservé"
CONSIDERATIONS_COLUMNS = {
    "sociales": "considerationsSociales",
    "environnementales": "considerationsEnvironnementales",
}


def compute_considerations_stats(lff: pl.LazyFrame) -> dict[str, tuple[int, int, int]]:
    """Statistiques considérations pour l'observatoire.

    Clés renvoyées :
      - "champs_renseignes"        : (count_ren_sociales, pct / total)
      - "{key}_renseignees"        : (count_ren, pct positifs parmi renseignés)
    Colonne absente -> (0, 0).
    """
    names = lff.collect_schema().names()
    present = {key: col for key, col in CONSIDERATIONS_COLUMNS.items() if col in names}

    stats: dict[str, tuple[int, int, int]] = {"champs_renseignes": (0, 0)}
    for key in CONSIDERATIONS_COLUMNS:
        stats[f"{key}_renseignees"] = (0, 0)

    if not present:
        return stats

    agg = (
        lff.select(["uid"] + list(present.values()))
        .group_by("uid")
        .agg([pl.col(col).first() for col in present.values()])
        .collect(engine="streaming")
    )

    total = agg.height
    if total == 0:
        return stats

    for key, col in present.items():
        count_ren = agg.filter(pl.col(col).is_not_null()).height
        count_pos_ren = agg.filter(
            pl.col(col).is_not_null() & (pl.col(col) != "Sans objet")
        ).height
        pct_pos_ren = round(100 * count_pos_ren / count_ren) if count_ren > 0 else 0
        stats[f"{key}_renseignees"] = (count_ren, count_pos_ren, pct_pos_ren)
        if key == "sociales":
            stats["champs_renseignes"] = (count_ren, round(100 * count_ren / total))

    return stats


# (clé stats, libellé, couleur)
CONSIDERATIONS_RENSEIGNEES = [
    ("sociales_renseignees", "Considérations sociales", "#CC6677"),
    ("environnementales_renseignees", "Considérations environnementales", "#117733"),
]


def _progress_bar(pct: int, color: str) -> dbc.Progress:
    return dbc.Progress(
        dbc.Progress(
            value=pct, label=f"{pct} %", bar=True, color=color, style={"color": "white"}
        ),
    )


def get_considerations_card_content(lff: pl.LazyFrame) -> html.Div:
    """Trois barres : champs renseignés + part positive pour sociales et environnementales."""
    stats = compute_considerations_stats(lff)

    count_ren, pct_ren = stats["champs_renseignes"]
    blocks = [
        html.Div(
            className="mb-3",
            children=[
                html.Div(
                    className="d-flex justify-content-between",
                    children=[
                        html.Span("Champs considérations renseignés"),
                        html.Span(
                            f"{format_number(count_ren)} marchés",
                            className="text-muted",
                        ),
                    ],
                ),
                _progress_bar(pct_ren, "#6c757d"),
            ],
        )
    ]

    for key, label, color in CONSIDERATIONS_RENSEIGNEES:
        total_count, count, pct = stats[key]
        blocks.append(
            html.Div(
                className="mb-3",
                children=[
                    html.Div(
                        className="d-flex justify-content-between",
                        children=[
                            html.Span(label),
                            html.Span(
                                f"dans {format_number(count)} marchés",
                                className="text-muted",
                            ),
                        ],
                    ),
                    _progress_bar(pct, color),
                ],
            )
        )

    return html.Div(children=blocks)


def make_card(
    title: str, subtitle=None, fig=None, paragraphs=None, lg=6, xl=4
) -> dbc.Col:
    children = []
    if title:
        children.append(html.H5(title, className="card-title"))
    if subtitle:
        children.append(html.H6(subtitle, className="card-subtitle mb-2 text-muted"))
    if fig is not None:
        children.append(fig)
    if paragraphs:
        for p in paragraphs:
            p.className = "card-text"
            children.append(p)

    card = dbc.Col(
        html.Div(html.Div(className="card-body", children=children), className="card"),
        lg=lg,
        xl=xl,
        # width=width,
        # className="mb-4",
    )
    return card


def make_donut(
    lff: pl.LazyFrame,
    names_col,
    per_uid: bool,
    nulls="?",
    potentially_many_names: bool = False,
):
    title = DATA_SCHEMA[names_col]["title"]
    lff = lff.rename({names_col: title})
    lff = lff.select("uid", title)

    if per_uid:
        lff = lff.group_by("uid").first()

    lff = lff.group_by(title).len("Nombre")
    lff = lff.with_columns(pl.col(title).replace(None, pl.lit(nulls)))
    dff = lff.collect(engine="streaming")
    nb_names = dff[title].n_unique()

    sum_values = dff["Nombre"].sum()
    dff = dff.with_columns(
        pl.when((pl.col("Nombre") / sum_values) < 0.01)
        .then(pl.lit("Autres"))
        .otherwise(pl.col(title))
        .alias(title)
    )

    dff = dff.with_columns(
        pl.col("Nombre")
        .map_elements(format_number, return_dtype=pl.String)
        .alias("Nombre_fmt")
    )
    fig = px.pie(
        dff,
        values="Nombre",
        names=title,
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Safe,
        custom_data=["Nombre_fmt"],
    )
    fig = fig.update_traces(
        texttemplate="<b>%{label}</b><br><b>%{percent}</b>",
        hovertemplate="<b>%{label}</b><br>%{customdata[0]}<extra></extra>",
    )
    fig = fig.update_layout(showlegend=False, font=dict(size=14))
    graph = dcc.Graph(figure=fig)
    if potentially_many_names:
        return graph, nb_names
    return graph


def make_column_picker(page: str):
    table_data = []
    table_columns = [
        {
            "id": col,
            "name": DATA_SCHEMA[col]["title"],
            "description": DATA_SCHEMA[col]["description"],
        }
        for col in schema.names()
    ]
    for column in table_columns:
        new_column = {
            "id": column["id"],
            "name": column["name"],
            "description": DATA_SCHEMA[column["id"]]["description"],
        }
        table_data.append(new_column)

    table = (
        DataTable(
            row_selectable="multi",
            data=table_data,
            filter_action="native",
            sort_action="none",
            style_cell={
                "textAlign": "left",
            },
            columns=[
                {
                    "name": "Nom",
                    "id": "name",
                },
                {
                    "name": "Description",
                    "id": "description",
                },
            ],
            style_cell_conditional=[
                {
                    "if": {"column_id": "description"},
                    "minWidth": "450px",
                    "overflow": "hidden",
                    "lineHeight": "18px",
                    "whiteSpace": "normal",
                }
            ],
            page_action="none",
            dtid=f"{page}_column_list",
        ),
    )

    return table


def get_top_org_table(data, org_type: str, extra_columns: list, filters: bool = True):
    if isinstance(data, pl.LazyFrame):
        lff = data
    else:
        lff = pl.LazyFrame(data, strict=False, infer_schema_length=5000)

    if org_type == "titulaire":
        extra_columns.append("titulaire_typeIdentifiant")
    columns = ["uid", f"{org_type}_id", f"{org_type}_nom"] + extra_columns

    lff = lff.select(columns)
    lff = lff.group_by([f"{org_type}_id", f"{org_type}_nom"] + extra_columns).agg(
        pl.len().alias("Attributions")
    )
    lff = lff.sort(by="Attributions", descending=True, nulls_last=True)
    lff = lff.cast(pl.String)
    lff = lff.fill_null("")

    try:
        dff: pl.DataFrame = lff.collect(engine="streaming")
    except ColumnNotFoundError:
        logger.warning(f"get_top_org_table: column not found. {lff.collect_schema()}")
        return html.Div()

    if dff.height == 0:
        return html.Div()

    columns, tooltip = setup_table_columns(
        dff, hideable=False, exclude=[f"{org_type}_id"]
    )
    dff = add_links(dff)
    data = dff.to_dicts()
    # data = add_links_in_dict(data, f"{org_type}")

    return DataTable(
        dtid=f"top10_{org_type}",
        data=data,
        page_action="native",
        page_size=10,
        columns=columns,
        tooltip_header=tooltip,
        filter_action="native" if filters else "none",
    )
