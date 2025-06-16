import json

import plotly.express as px
import polars as pl
from dash import dcc, html, register_page

from src.utils import df

title = "Statistiques"

register_page(
    __name__, path="/statistiques", title=f"decp.info - {title}", name=title, order=3
)

df = df.with_columns(
    pl.col("lieuExecution_code").str.head(2).str.zfill(2).alias("Département")
)
df = (
    df.unique(subset="uid")
    .select(["uid", "Département"])
    .unique(subset="uid")
    .group_by("Département")
    .len("uid")
)

with open("./data/departements-1000m.geojson") as f:
    departements = json.load(f)

# Ajout de feature.id
for f in departements["features"]:
    f["id"] = f["properties"]["code"]

fig = px.choropleth(
    df,
    geojson=departements,
    locations="Département",
    color="uid",
    color_continuous_scale="Viridis",
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

layout = [
    html.Div(
        className="container",
        children=[
            html.H2(title),
            dcc.Markdown("""
            Si nous disposons de beaucoup de données pour certains départements, pour d'autres les sources de DECP doivent encore être identifiées et ajoutées.

            Par exemple, les données des plateformes Atexo [ne sont pas encore présentes](https://github.com/ColinMaudry/decp-processing/issues/57).
            """),
            dcc.Loading(
                overlay_style={"visibility": "visible", "filter": "blur(2px)"},
                id="loading-1",
                type="default",
                children=[
                    html.Div(children=[dcc.Graph(figure=fig)]),
                ],
            ),
        ],
    )
]
