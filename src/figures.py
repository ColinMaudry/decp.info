from typing import Literal
from urllib.error import HTTPError, URLError

import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_leaflet.express as dlx
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from dash import dash_table, dcc, html
from dash_extensions.javascript import Namespace

from src.utils import data_schema, departements_geojson, df, format_number


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
        pl.col(type_date).is_not_null() & pl.col("annee").is_between(2019, 2025)
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
        dff = pl.read_csv(source_path)
    except (URLError, HTTPError):
        return html.Div("Erreur de connexion")
    dff = dff.with_columns(
        (
            pl.lit('<a href = "')
            + pl.col("url")
            + pl.lit('">')
            + pl.col("nom")
            + pl.lit("</a>")
        ).alias("nom")
    )
    dff = dff.drop("url", "unique")
    dff = dff.sort(by=["nb_marchés"], descending=True)

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
                "minWidth": "350px",
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


def point_on_map(lat, lon):
    lat = float(lat)
    lon = float(lon)

    # Create a scatter mapbox or choropleth map
    fig = px.scatter_map(
        lat=[lat], lon=[lon], height=300, width=400, color=[1], size=[1]
    )

    fig.update_coloraxes(showscale=False)

    # Set map style (you can use 'open-street-map', 'carto-positron', etc.)
    fig.update_layout(
        mapbox_style="light",  # Light, clean background
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
    )

    # Optionally, center the map on France
    fig.update_geos(
        center=dict(lat=46.603354, lon=1.888334),  # Center of France
        lataxis_range=[41, 51.5],  # Latitude range for France
        lonaxis_range=[-5, 10],  # Longitude range for France
    )

    # But scatter_mapbox doesn't use geos, so better to control via zoom/center manually
    # Let's reset and use proper centering in scatter_mapbox instead:

    fig.update_layout(map_center={"lat": 46.6, "lon": 1.89}, map_zoom=4)

    graph = dcc.Graph(id="map", figure=fig)
    graph = html.Div(style={"width": "400px"})
    return graph


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

        for key in data_schema.keys():
            field = data_schema[key]
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


def get_geographic_maps(dff: pl.DataFrame) -> list | None:
    """
    Génère les cartes géographiques pour la métropole et les DOM-TOM.
    """

    regions: dict = {
        "Métropole": {
            "coordinates": [46.6, 2.2],
            "zoom_leaflet": 5,
            "zoom_chloropleth": 1,
            "name": "Métropole",
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

    def make_map_data(region_code: str) -> tuple[list, str or None]:
        lff: pl.LazyFrame = dff.lazy()
        if region_code == "Métropole":
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

        if (code == "Métropole" and nb_marches > 30000) or (
            code != "Métropole" and nb_marches > 10000
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
                lff_org = (
                    lff.select(
                        "uid",
                        f"{org_type}_longitude",
                        f"{org_type}_latitude",
                        f"{org_type}_nom",
                    )
                    .group_by(
                        f"{org_type}_longitude",
                        f"{org_type}_latitude",
                        f"{org_type}_nom",
                    )
                    .len("nb_marches")
                    .filter(
                        pl.col(f"{org_type}_latitude").is_not_null()
                        & pl.col(f"{org_type}_longitude").is_not_null()
                    )
                )

                markers = []

                # Couleurs accessibles (Okabe-Ito)
                colors = {
                    "acheteur": "#E69F00",  # orange
                    "titulaire": "#56B4E9",  # bleu ciel
                }

                for row in lff_org.collect().to_dicts():
                    markers.append(
                        {
                            "lat": row[f"{org_type}_latitude"],
                            "lon": row[f"{org_type}_longitude"],
                            "tooltip": f"{row[f'{org_type}_nom']} ({row['nb_marches']} marchés)",
                            "marker_color": colors[org_type],
                        }
                    )
                dfs.append(markers)

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

        lg, xl = (12, 8) if code == "Métropole" else (6, 4)

        col = make_card(regions[code]["name"], fig=map_graph, lg=lg, xl=xl)
        cols.append(col)

    return cols


def make_chloropleth_map(region: dict) -> dcc.Graph:
    df_map = region["data"][0]

    fig = px.choropleth(
        df_map,
        geojson=departements_geojson,
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
    color_acheteur = region_acheteurs[0]["marker_color"]
    color_titulaire = region_titulaires[0]["marker_color"]

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
            "height": "400px" if name == "Métropole" else "300px",
        },
        id=f"map-{region_id}",
    )
    return leaflet_map


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
    dff = dff.with_columns(pl.col("titulaire_distance").log(10))
    fig = px.histogram(
        dff,
        x="titulaire_distance",
        nbins=50,
        labels={"titulaire_distance": "Distance (km)"},
    )
    fig.update_xaxes(
        tickvals=[0, 1, 2, 3, 4],
        ticktext=["1", "10", "100", "1 000", "10 000"],
        title_text="Distance (km)",
    )
    fig.update_yaxes(title_text="Nombre de marchés")
    return dcc.Graph(figure=fig)


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
    title = data_schema[names_col]["title"]
    lff = lff.rename({names_col: title})
    lff = lff.select("uid", title)

    if per_uid:
        lff = lff.group_by("uid").first()

    lff = lff.group_by(title).len("Nombre")
    lff = lff.with_columns(pl.col(title).replace(None, pl.lit(nulls)))
    dff = lff.collect(engine="streaming")
    nb_names = dff[title].n_unique()
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
            "name": data_schema[col]["title"],
            "description": data_schema[col]["description"],
        }
        for col in df.columns
    ]
    for column in table_columns:
        new_column = {
            "id": column["id"],
            "name": column["name"],
            "description": data_schema[column["id"]]["description"],
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
