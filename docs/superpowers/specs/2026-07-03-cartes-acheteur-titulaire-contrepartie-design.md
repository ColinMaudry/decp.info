# Cartes /acheteur et /titulaire : afficher la contrepartie (clustering)

## Objectif

Sur les fiches `/acheteurs/<id>` et `/titulaires/<id>`, la carte affiche
aujourd'hui uniquement la position de l'organisme consulté (un point unique,
issu de l'API annuaire, via `point_on_map`). On veut y ajouter la position de
la **contrepartie** :

- sur `/acheteurs/<id>` : les titulaires avec qui cet acheteur a contracté ;
- sur `/titulaires/<id>` : les acheteurs qui ont contracté avec ce titulaire.

Design et code inspirés de `/observatoire` (`get_geographic_maps` /
`make_clusters_map` dans `src/figures.py`), notamment le clustering
dash-leaflet. Couleurs identiques : acheteur en orange (`#E69F00`), titulaire
en bleu ciel (`#56B4E9`).

## Comportement attendu

- La carte suit le filtre **Année** de la page (comme le tableau Top
  titulaires/acheteurs et l'histogramme de distance) — elle n'est donc plus
  calculée à partir de l'API annuaire mais des données DECP (marchés).
- Le marqueur de l'organisme consulté et ceux de la contrepartie utilisent
  **la même source de données** (`acheteur_longitude`/`latitude` et
  `titulaire_longitude`/`latitude` des marchés), avec clustering identique à
  `/observatoire`.
- Le cadrage de la carte s'ajuste automatiquement (fitBounds) pour englober
  l'organisme et toutes ses contreparties, avec un léger padding.
- Si aucune coordonnée exploitable n'est disponible (aucun marché
  géolocalisé, ou dataset sans colonnes longitude/latitude), repli sur une
  vue France fixe (centre `[46.6, 2.2]`, zoom 5) plutôt qu'une zone vide.
- Contrairement à `/observatoire`, **pas** de découpage par région/DOM-TOM ni
  de bascule chloroplèthe : une seule carte cluster, le volume de points
  d'un organisme unique restant faible.
- La carte dash-leaflet conserve les contrôles de zoom +/- natifs de Leaflet
  (contrairement à l'actuelle carte Plotly qui n'en a pas) — comportement par
  défaut de `dl.Map`, aucune configuration spécifique nécessaire.

## Architecture

### Nouvelle fonction partagée `build_org_markers` (`src/figures.py`)

Extraite du corps de `get_geographic_maps` (branche `"clusters"`), pour être
réutilisée par `/observatoire` et par la nouvelle carte org :

```python
ORG_COLORS = {
    "acheteur": "#E69F00",  # orange
    "titulaire": "#56B4E9",  # bleu ciel
}

def build_org_markers(lff: pl.LazyFrame, org_type: Literal["acheteur", "titulaire"]) -> list[dict]:
    """Regroupe les marchés par point géographique pour un type d'organisme.

    Retourne [] si les colonnes longitude/latitude de ce type sont absentes
    du LazyFrame (ex: tests/test.parquet), sans lever d'exception.
    """
```

Le groupement (par `{org_type}_longitude`, `{org_type}_latitude`,
`{org_type}_nom`, comptage `nb_marches`) et le format des marqueurs
(`{"lat", "lon", "tooltip", "marker_color"}`) restent identiques à
l'implémentation actuelle. Nouveauté : garde d'absence de colonnes via
`lff.collect_schema().names()` (cf. `get_considerations_card_content` pour le
même pattern) — corrige au passage un crash latent non testé de
`get_geographic_maps` sur des jeux de données sans colonnes géo.

`get_geographic_maps` est mis à jour pour appeler `build_org_markers(lff, org_type)` au lieu de la boucle inline, et pour utiliser `ORG_COLORS` au lieu
de son dict `colors` local.

### Nouvelle fonction `get_org_location_map` (`src/figures.py`)

```python
def get_org_location_map(
    dff: pl.DataFrame,
    home_type: Literal["acheteur", "titulaire"],
    map_id: str,
) -> dl.Map:
    """Carte cluster (dash-leaflet) de l'organisme et de sa contrepartie."""
```

- Calcule les marqueurs pour `home_type` et son type complémentaire via
  `build_org_markers`.
- Construit jusqu'à deux couches `dl.GeoJSON` clusterisées (une par type
  présent), réutilisant le JS clientside existant
  (`dash_clientside.leaflet.pointToLayer` / `clusterToLayer`, inchangé) et le
  même mécanisme `options={"fillColor": ORG_COLORS[org_type]}` que
  `make_clusters_map`.
- Calcule les bounds `[[lat_min, lon_min], [lat_max, lon_max]]` sur l'ensemble
  des points (les deux types confondus) et les passe via la prop `bounds` de
  `dl.Map`, avec `boundsOptions={"padding": [30, 30], "maxZoom": 12}`.
- Si aucun point n'est disponible : `center=[46.6, 2.2]`, `zoom=5` (pas de
  prop `bounds`).
- `style={"width": "100%", "height": "300px"}` (cohérent avec la hauteur
  actuelle de la colonne carte).
- Les ids des couches GeoJSON sont dérivés de `map_id`
  (`f"{map_id}-acheteur"` / `f"{map_id}-titulaire"`).

## Flux de données (pages)

Sur `src/pages/acheteur.py` et `src/pages/titulaire.py`, le rendu de la carte
est aujourd'hui mélangé dans le callback qui interroge l'API annuaire
(`update_acheteur_infos` / `update_titulaire_infos`, déclenché uniquement par
l'URL). On sépare :

- Ce callback existant perd l'`Output` `*_map` et l'appel à `point_on_map` ;
  il continue de fournir nom/commune/département/région/lien annuaire,
  inchangés.
- **Nouveau callback dédié** par page, avec `Input` sur l'URL **et** le
  dropdown Année (comme `get_top_titulaires`/`get_top_acheteurs`) :

```python
@callback(
    Output("acheteur_map", "children"),
    Input("acheteur_url", "pathname"),
    Input("acheteur_year", "value"),
)
def update_acheteur_map(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    geo_columns = [
        c
        for c in [
            "uid",
            "acheteur_longitude",
            "acheteur_latitude",
            "acheteur_nom",
            "titulaire_longitude",
            "titulaire_latitude",
            "titulaire_nom",
        ]
        if c in schema.names()
    ]
    dff = query_marches(where_sql, params, columns=geo_columns)
    return get_org_location_map(dff, "acheteur", "acheteur_map_leaflet")
```

Le filtre `geo_columns` sur `schema.names()` évite une erreur SQL DuckDB
(colonne inexistante) quand le dataset ne contient pas encore les colonnes
longitude/latitude — c'est le cas de `tests/test.parquet` aujourd'hui. Dans
ce cas, `build_org_markers` renvoie `[]` pour les deux types et
`get_org_location_map` bascule sur la vue France par défaut.

Symétrique sur `src/pages/titulaire.py` (`update_titulaire_map`,
`_titulaire_scope`, `"titulaire"` comme `home_type`).

## Nettoyage

`point_on_map` (carte Plotly à point unique basée sur l'annuaire) devient
inutilisée une fois les deux pages migrées : suppression de la fonction dans
`src/figures.py` et de son import dans `acheteur.py`/`titulaire.py`.

## Tests

- Test unitaire de `build_org_markers` : cas nominal (plusieurs points,
  comptage), cas colonnes absentes (`[]` sans exception), cas coordonnées
  nulles filtrées.
- Test unitaire de `get_org_location_map` : bounds calculés sur des points
  connus ; repli sur la vue France par défaut quand aucun marqueur.
- Pas de nouveau test Selenium dédié (aucun test existant ne navigue
  actuellement vers `/acheteurs/<id>` ou `/titulaires/<id>` dans le
  navigateur) ; vérification manuelle via le serveur de dev recommandée
  après implémentation.

## Hors périmètre (YAGNI)

- Pas de découpage par région/DOM-TOM ni de bascule chloroplèthe sur ces
  pages (réservé à `/observatoire`).
- Pas de changement du texte département/région/lien annuaire (reste basé
  sur l'annuaire des entreprises).
- Pas de nouveau filtre autre que celui déjà présent (Année).
