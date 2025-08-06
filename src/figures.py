import json

import plotly.express as px
import polars as pl


def get_map_count_marches(lf):
    lf = lf.with_columns(
        pl.col("lieuExecution_code").str.head(2).str.zfill(2).alias("Département")
    )
    lf = (
        lf.unique(subset="uid")
        .select(["uid", "Département"])
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

    lf = lf.select("uid", type_date, "source")
    lf = lf.unique("uid")
    lf = lf.with_columns(pl.col(type_date).dt.year().alias("annee"))
    lf = lf.filter(
        pl.col(type_date).is_not_null() & pl.col("annee").is_between(2018, 2025)
    )
    lf = lf.sort(by=[type_date, "source"], descending=False)
    lf = lf.with_columns(pl.col(type_date).cast(pl.String).str.head(7))

    lf = lf.group_by([type_date, "source"]).len()
    lf = lf.with_columns(
        pl.when(pl.col("source").is_null()).then(
            pl.lit("Source inconnue").alias("source")
        )
    )
    lf = lf.sort(by=[type_date, "source"], descending=False)
    df: pl.DataFrame = lf.collect()

    fig = px.bar(
        df,
        x=type_date,
        y="len",
        color="source",
        title=f"Nombre de marchés attribués par date de {labels[type_date]} et source de données",
        labels={
            "len": "Nombre de marchés",
            type_date: f"Mois de {labels[type_date]}",
            "source": "Source de données",
        },
    )
    return fig
