import json

import plotly.express as px
import polars as pl


def get_map_count_marches(lf: pl.LazyFrame):
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

    df = lf.collect()

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
        width=1000,
        height=800,
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


def get_barchart_sources(lf: pl.LazyFrame, type_date: str):
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
    df: pl.DataFrame = lf.collect()

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
