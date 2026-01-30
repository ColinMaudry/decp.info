import json
from typing import Literal

import plotly.express as px
import plotly.graph_objects as go
import polars as pl
from dash import dash_table, dcc, html

from src.utils import data_schema, format_number


def get_map_count_marches(df: pl.DataFrame):
    lf = df.lazy()
    lf = lf.with_columns(
        pl.col("lieuExecution_code").str.head(2).str.zfill(2).alias("Département")
    )
    lf = (
        lf.select(["uid", "Département"])
        .drop_nulls()
        .unique(subset="uid")
        .group_by("Département")
        .len("uid")
    )
    # Suppression des infos pour les DOM/TOM pour l'instant
    lf = lf.remove(pl.col("Département").is_in(["97", "98"]))

    with open("./data/departements-1000m.geojson") as f:
        departements = json.load(f)

    # Ajout de feature.id
    for f in departements["features"]:
        f["id"] = f["properties"]["code"]

    df = lf.collect(engine="streaming")

    fig = px.choropleth(
        df,
        geojson=departements,
        locations="Département",
        color="uid",
        color_continuous_scale="Reds",
        title="Nombres de marchés attribués par département (lieu d'exécution)",
        range_color=(df["uid"].min(), df["uid"].max()),
        labels={"uid": "Marchés attribués"},
        scope="europe",
        width=900,
        height=700,
    )

    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        mapbox={
            "style": "carto-positron",
            "center": {"lon": 10, "lat": 10},
            "zoom": 1,
            "domain": {"x": [0, 1], "y": [0, 1]},
        }
    )
    return fig


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

    df = pl.DataFrame(data)

    # Create Dash DataTable
    table = dash_table.DataTable(
        data=df.to_dicts(),
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


def get_barchart_sources(df_source: pl.DataFrame, type_date: str):
    lf = df_source.lazy()
    labels = {
        "dateNotification": "notification",
        "datePublicationDonnees": "publication des données",
    }

    lf = lf.select("uid", type_date, "sourceDataset")

    lf = lf.unique("uid")

    # Rassemblement des datasets Atexo pour ne pas surcharger le graphique
    lf = lf.with_columns(
        pl.when(pl.col("sourceDataset").str.starts_with("atexo"))
        .then(pl.lit("plateformes atexo"))
        .otherwise(pl.col("sourceDataset"))
        .alias("sourceDataset")
    )

    # Rassemblement des datasets AWS pour ne pas surcharger le graphique
    lf = lf.with_columns(
        pl.when(pl.col("sourceDataset").str.contains(r"aws|marches\-publics.info"))
        .then(pl.lit("aws"))
        .otherwise(pl.col("sourceDataset"))
        .alias("sourceDataset")
    )

    lf = lf.with_columns(pl.col(type_date).dt.year().alias("annee"))
    lf = lf.filter(
        pl.col(type_date).is_not_null() & pl.col("annee").is_between(2019, 2025)
    )
    lf = lf.with_columns(pl.col(type_date).cast(pl.String).str.head(7))
    lf = (
        lf.group_by([type_date, "sourceDataset"])
        .len()
        .sort(by=[type_date, "len"], descending=True)
    )

    # lf = lf.with_columns(
    #     pl.when(pl.col("sourceDataset").is_null()).then(
    #         pl.lit("Source inconnue")).alias("sourceDataset")
    #     )

    lf = lf.sort(by=["sourceDataset"], descending=False)
    df: pl.DataFrame = lf.collect(engine="streaming")

    fig = px.bar(
        df,
        x=type_date,
        y="len",
        color="sourceDataset",
        title=f"Nombre de marchés attribués par date de {labels[type_date]} et source de données",
        labels={
            "len": "Nombre de marchés",
            type_date: f"Mois de {labels[type_date]}",
            "sourceDataset": "Source de données",
        },
    )

    return fig


def get_sources_tables(source_path) -> html.Div:
    df = pl.read_csv(source_path)
    df = df.with_columns(
        (
            pl.lit('<a href = "')
            + pl.col("url")
            + pl.lit('">')
            + pl.col("nom")
            + pl.lit("</a>")
        ).alias("nom")
    )
    df = df.drop("url", "unique")
    df = df.sort(by=["nb_marchés"], descending=True)

    columns = {
        "nom": "Nom de la source",
        "organisation": "Responsable de publication",
        "nb_marchés": "Nb de marchés",
        "nb_acheteurs": "Nb d'acheteurs",
        "code": "Code",
    }

    datatable = dash_table.DataTable(
        id="source_table",
        data=df.to_dicts(),
        columns=[
            {
                "name": columns[i],
                "id": i,
                "presentation": "markdown",
                "type": "text",
                "format": {"nully": "N/A"},
            }
            for i in df.schema.names()
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
        **kwargs,
    ):
        # Styles de base
        style_cell_conditional = [
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

        for key in data_schema.keys():
            field = data_schema[key]
            if field["type"] in ["number", "integer"]:
                rule = {
                    "if": {"column_id": field["name"]},
                    "textAlign": "right",
                    # "fontFamily": "Fira Code",
                }
                style_cell_conditional.append(rule)

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
                "placeholder_text": "",
            },
            sort_action=sort_action,
            sort_mode="multi",
            sort_by=[],
            row_deletable=False,
            page_current=0,
            style_cell_conditional=style_cell_conditional,
            data_timestamp=0,
            markdown_options={"html": True},
            style_header={"fontFamily": "Inter", "fontSize": "16px"},
            style_cell={"fontFamily": "Inter", "fontSize": "16px"},
            tooltip_duration=8000,
            tooltip_delay=350,
            hidden_columns=hidden_columns,
            **kwargs,  # Possibilité de remplacer des arguments
        )


def get_duplicate_matrix() -> html.Div:
    """
    Fonction développée avec l'aide de la LLM Euria d'Infomaniak.
    :return:
    """
    result_df = pl.read_parquet(
        "https://www.data.gouv.fr/api/1/datasets/r/a545bf6c-8b24-46ed-b49f-a32bf02eaffa"
    ).sort("sourceDataset")
    result_df = result_df.select(
        ["sourceDataset", "unique"] + sorted(result_df.columns[2:])
    )

    description = dcc.Markdown("""
    Ce graphique illustre les doublons de marchés publics entre sources, c'est-à-dire la proportion de marchés publiés par plus d'une source. Il s'appuie sur les identifiants `uid` qui sont pour chaque marché la concaténation du SIRET de l'acheteur et de l'identifiant interne du marché.

    **Comment lire ce graphique ?**

    On part des codes de sources de données en ordonnée. Ces jeux de données sont documentés dans [À propos](/a-propos#sources).

    La première colonne (**unique**) représente le pourcentage de marchés fournis par cette source qui sont uniquement disponibles dans cette source. Plus le rouge est foncé, plus important est le pourcentage. Donc, à l'inverse, plus le rouge est clair dans la première colonne, plus la source en ordonnée a des marchés en commun avec d'autres sources, et donc plus on trouvera sur la même ligne d'autres cases plus ou moins foncées qui indiqueront avec quelles autres sources cette source partage des marchés.

    Passez votre souris sur une case pour avoir les pourcentages exacts. À noter que ces statistiques sont produites avant le dédoublonnement qui a lieu avant la publication en Open Data et sur ce site.""")

    # Extract data
    z_data = result_df.select(pl.all().exclude("sourceDataset")).fill_null(0).to_numpy()
    x_labels = result_df.columns[1:]  # columns after "sourceDataset"
    y_labels = result_df["sourceDataset"].to_list()

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
                "<b>%{z:.0%}</b> des marchés de <b>%{y}</b> sont également présents dans <b>%{x}</b>"
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

    return html.Div(
        children=[
            html.H3("Doublons de marchés entre les sources"),
            description,
            dcc.Graph(figure=fig),
        ]
    )
