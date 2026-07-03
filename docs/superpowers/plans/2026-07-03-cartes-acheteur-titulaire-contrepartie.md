# Cartes /acheteur et /titulaire : afficher la contrepartie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sur `/acheteurs/<id>` et `/titulaires/<id>`, remplacer la carte Plotly à point unique (basée sur l'annuaire) par une carte dash-leaflet clusterisée qui affiche l'organisme consulté **et** sa contrepartie (titulaires pour un acheteur, acheteurs pour un titulaire).

**Architecture:** Extraction d'une fonction partagée `build_org_markers` (déjà dupliquée en boucle dans `get_geographic_maps` d'`/observatoire`) puis nouvelle fonction `get_org_location_map` qui assemble deux couches `dl.GeoJSON` clusterisées (une par type d'organisme) avec cadrage automatique (`bounds`). Un nouveau callback par page, déclenché par l'URL et le filtre Année, appelle cette fonction ; l'ancien callback annuaire perd la responsabilité de la carte.

**Tech Stack:** Python, Polars, DuckDB, Dash, `dash-leaflet` (`dl`), `dash-leaflet.express` (`dlx`), `dash-extensions` (`Namespace`).

## Global Constraints

- Couleurs des marqueurs : acheteur `#E69F00` (orange), titulaire `#56B4E9` (bleu ciel) — identiques à `/observatoire`.
- La carte suit le filtre **Année** de la page (`acheteur_year`/`titulaire_year`), comme les tableaux Top titulaires/acheteurs.
- Cadrage automatique (`fitBounds`) sur l'organisme + toutes ses contreparties, avec padding léger (`boundsOptions={"padding": [30, 30], "maxZoom": 12}`).
- Repli sur une vue France fixe (`center=[46.6, 2.2]`, `zoom=5`) si aucune coordonnée exploitable n'est disponible (dataset sans colonnes longitude/latitude, ou organisme sans marché géolocalisé) — jamais d'exception.
- Pas de découpage par région/DOM-TOM ni de bascule chloroplèthe sur `/acheteur`/`/titulaire` (réservé à `/observatoire`).
- Les contrôles de zoom +/- natifs de `dl.Map` (Leaflet) doivent rester actifs — ne jamais passer `zoomControl=False`.
- Imports internes toujours via `src.` (ex. `from src.figures import ...`), jamais `figures.py` en import relatif nu.
- Lancer les tests avec `uv run pytest` (l'activation du venv via l'outil Bash n'est pas fiable dans cet environnement).

---

## File Structure

- **Modify `src/figures.py`** : ajoute `ORG_COLORS`, `build_org_markers`, `get_org_location_map` ; met à jour `get_geographic_maps` et `make_clusters_map` pour réutiliser `build_org_markers`/`ORG_COLORS` ; supprime `point_on_map` (devient mort après migration des deux pages).
- **Modify `src/pages/acheteur.py`** : nouveau callback `update_acheteur_map` ; `update_acheteur_infos` perd la construction de la carte.
- **Modify `src/pages/titulaire.py`** : nouveau callback `update_titulaire_map` ; `update_titulaire_infos` perd la construction de la carte.
- **Test `tests/test_figures.py`** : tests unitaires de `build_org_markers` et `get_org_location_map`.

---

### Task 1: Extraire `build_org_markers` et l'utiliser dans `get_geographic_maps`

**Files:**

- Modify: `src/figures.py:410-551` (fonction `get_geographic_maps`), `src/figures.py:582-633` (fonction `make_clusters_map`)
- Test: `tests/test_figures.py` (ajout en fin de fichier)

**Interfaces:**

- Produces: `ORG_COLORS: dict[str, str]` (clés `"acheteur"`/`"titulaire"`) ; `build_org_markers(lff: pl.LazyFrame, org_type: Literal["acheteur", "titulaire"]) -> list[dict]` où chaque `dict` a les clés `"lat"`, `"lon"`, `"tooltip"`, `"marker_color"`. Renvoie `[]` (sans exception) si les colonnes `{org_type}_longitude`/`{org_type}_latitude` sont absentes du `LazyFrame`.

- [ ] **Step 1: Écrire les tests (qui vont échouer, `build_org_markers` n'existe pas encore)**

Ajouter à la fin de `tests/test_figures.py` :

```python
def test_build_org_markers_groups_and_counts():
    from src.figures import build_org_markers

    lff = pl.LazyFrame(
        [
            {
                "uid": "u1",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR A",
            },
            {
                "uid": "u2",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR A",
            },
            {
                "uid": "u3",
                "acheteur_longitude": -1.68,
                "acheteur_latitude": 48.11,
                "acheteur_nom": "ACHETEUR B",
            },
        ]
    )

    markers = build_org_markers(lff, "acheteur")

    assert len(markers) == 2
    marker_a = next(m for m in markers if m["tooltip"].startswith("ACHETEUR A"))
    assert marker_a["tooltip"] == "ACHETEUR A (2 marchés)"
    assert marker_a["lat"] == 48.85
    assert marker_a["lon"] == 2.35
    assert marker_a["marker_color"] == "#E69F00"


def test_build_org_markers_filters_null_coordinates():
    from src.figures import build_org_markers

    lff = pl.LazyFrame(
        [
            {
                "uid": "u1",
                "acheteur_longitude": None,
                "acheteur_latitude": None,
                "acheteur_nom": "ACHETEUR A",
            },
            {
                "uid": "u2",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR B",
            },
        ]
    )

    markers = build_org_markers(lff, "acheteur")

    assert len(markers) == 1
    assert markers[0]["tooltip"] == "ACHETEUR B (1 marchés)"


def test_build_org_markers_missing_columns_returns_empty():
    from src.figures import build_org_markers

    lff = pl.LazyFrame([{"uid": "u1", "acheteur_nom": "ACHETEUR A"}])

    assert build_org_markers(lff, "acheteur") == []
    assert build_org_markers(lff, "titulaire") == []
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_figures.py -k build_org_markers -v`
Expected: FAIL avec `ImportError: cannot import name 'build_org_markers'`

- [ ] **Step 3: Ajouter `ORG_COLORS` et `build_org_markers`, refactoriser `get_geographic_maps` et `make_clusters_map`**

Dans `src/figures.py`, insérer juste avant `def get_geographic_maps(dff: pl.DataFrame) -> list[dbc.Col] | list:` (ligne 410) :

```python
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
```

Dans le corps de `get_geographic_maps` (fonction interne `make_map_data`), remplacer le bloc actuel :

```python
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
```

par :

```python
        else:
            _map_type: str = "clusters"
            for org_type in ["acheteur", "titulaire"]:
                dfs.append(build_org_markers(lff, org_type))
```

Dans `make_clusters_map`, remplacer :

```python
    # Couleurs
    color_acheteur = region_acheteurs[0]["marker_color"]
    color_titulaire = region_titulaires[0]["marker_color"]
```

par (évite un `IndexError` maintenant que `build_org_markers` peut renvoyer une liste vide) :

```python
    # Couleurs
    color_acheteur = ORG_COLORS["acheteur"]
    color_titulaire = ORG_COLORS["titulaire"]
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_figures.py -v`
Expected: PASS (tous les tests, y compris les 3 nouveaux)

- [ ] **Step 5: Lancer la suite complète pour vérifier l'absence de régression**

Run: `uv run pytest`
Expected: tous les tests passent (identique à avant la modification)

- [ ] **Step 6: Commit**

```bash
git add src/figures.py tests/test_figures.py
git commit -m "$(cat <<'EOF'
refactor(figures): extraire build_org_markers pour réutilisation

EOF
)"
```

---

### Task 2: Ajouter `get_org_location_map`

**Files:**

- Modify: `src/figures.py` (nouvelle fonction, à la suite de `make_clusters_map`, ligne 633)
- Test: `tests/test_figures.py`

**Interfaces:**

- Consumes: `ORG_COLORS`, `build_org_markers` (Task 1)
- Produces: `get_org_location_map(dff: pl.DataFrame, home_type: Literal["acheteur", "titulaire"], map_id: str) -> dl.Map`

- [ ] **Step 1: Écrire les tests (qui vont échouer, la fonction n'existe pas encore)**

Ajouter à la fin de `tests/test_figures.py` :

```python
def test_get_org_location_map_bounds_cover_home_and_counterpart():
    import dash_leaflet as dl

    from src.figures import get_org_location_map

    dff = pl.DataFrame(
        [
            {
                "uid": "u1",
                "acheteur_longitude": 2.35,
                "acheteur_latitude": 48.85,
                "acheteur_nom": "ACHETEUR A",
                "titulaire_longitude": -1.68,
                "titulaire_latitude": 48.11,
                "titulaire_nom": "TITULAIRE A",
            }
        ]
    )

    leaflet_map = get_org_location_map(dff, "acheteur", "test-map")

    assert isinstance(leaflet_map, dl.Map)
    assert leaflet_map.bounds == [[48.11, -1.68], [48.85, 2.35]]

    geojson_layers = [c for c in leaflet_map.children if isinstance(c, dl.GeoJSON)]
    assert {layer.id for layer in geojson_layers} == {
        "test-map-acheteur",
        "test-map-titulaire",
    }


def test_get_org_location_map_defaults_to_france_view_without_coordinates():
    from src.figures import get_org_location_map

    dff = pl.DataFrame(
        [{"uid": "u1", "acheteur_nom": "ACHETEUR A", "titulaire_nom": "TITULAIRE A"}]
    )

    leaflet_map = get_org_location_map(dff, "acheteur", "test-map")

    assert leaflet_map.center == [46.6, 2.2]
    assert leaflet_map.zoom == 5
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `uv run pytest tests/test_figures.py -k get_org_location_map -v`
Expected: FAIL avec `ImportError: cannot import name 'get_org_location_map'`

- [ ] **Step 3: Implémenter `get_org_location_map`**

Dans `src/figures.py`, ajouter à la suite de `make_clusters_map` (après la ligne `return leaflet_map` qui la termine) :

```python
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
    counterpart_type: Literal["acheteur", "titulaire"] = (
        "titulaire" if home_type == "acheteur" else "acheteur"
    )

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
```

Note : `home_type` et `counterpart_type` ne sont pas utilisés pour changer le contenu affiché (les deux types sont toujours construits et affichés) — `home_type` sert uniquement à documenter l'intention de l'appelant et pourrait être utilisé plus tard pour un style différencié. Garder le paramètre tel quel (il est requis par l'appelant pour construire les colonnes de la requête, cf. Task 3/4).

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `uv run pytest tests/test_figures.py -v`
Expected: PASS (tous les tests, y compris les 2 nouveaux)

- [ ] **Step 5: Commit**

```bash
git add src/figures.py tests/test_figures.py
git commit -m "$(cat <<'EOF'
feat(figures): ajouter get_org_location_map (carte cluster organisme + contrepartie)

EOF
)"
```

---

### Task 3: Brancher la carte sur `/acheteurs/<id>`

**Files:**

- Modify: `src/pages/acheteur.py`

**Interfaces:**

- Consumes: `get_org_location_map` (Task 2), `_acheteur_scope(pathname, ach_year) -> tuple[str, list]` (déjà existant, `src/pages/acheteur.py:50`), `schema.names()`, `query_marches` (déjà importés)

- [ ] **Step 1: Mettre à jour l'import de `src.figures`**

Dans `src/pages/acheteur.py`, remplacer :

```python
from src.figures import (
    DataTable,
    get_distance_histogram,
    get_top_org_table,
    make_card,
    make_column_picker,
    point_on_map,
)
```

par :

```python
from src.figures import (
    DataTable,
    get_distance_histogram,
    get_org_location_map,
    get_top_org_table,
    make_card,
    make_column_picker,
)
```

- [ ] **Step 2: Retirer la construction de la carte de `update_acheteur_infos`**

Remplacer le callback existant (celui avec les `Output` `acheteur_siret`, `acheteur_nom`, `acheteur_commune`, `acheteur_map`, `acheteur_departement`, `acheteur_region`, `acheteur_lien_annuaire`) :

```python
@callback(
    Output(component_id="acheteur_siret", component_property="children"),
    Output(component_id="acheteur_nom", component_property="children"),
    Output(component_id="acheteur_commune", component_property="children"),
    Output(component_id="acheteur_map", component_property="children"),
    Output(component_id="acheteur_departement", component_property="children"),
    Output(component_id="acheteur_region", component_property="children"),
    Output(component_id="acheteur_lien_annuaire", component_property="href"),
    Input(component_id="acheteur_url", component_property="pathname"),
)
def update_acheteur_infos(url):
    acheteur_siret = url.split("/")[-1]
    # if len(acheteur_siret) != 14:
    #     acheteur_siret = (
    #         f"Le SIRET renseigné doit faire 14 caractères ({acheteur_siret})"
    #     )
    data = get_annuaire_data(acheteur_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        # Extraction du code département à partir du code postal
        code_postal = data_etablissement.get("code_postal", "")
        departement_code = code_postal[:2] if code_postal else None

        # Création de la carte avec le code département pour un centrage approprié
        acheteur_map = point_on_map(
            data_etablissement["latitude"],
            data_etablissement["longitude"],
            departement_code,
        )
        code_departement, nom_departement, nom_region = get_departement_region(
            data_etablissement["code_postal"]
        )
        departement = f"{nom_departement} ({code_departement})"
        lien_annuaire = (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{acheteur_siret}"
        )
        raison_sociale = data["nom_raison_sociale"]
        libelle_commune = data_etablissement["libelle_commune"]

    else:
        acheteur_map = html.Div()
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = ""
        libelle_commune = ""

    return (
        acheteur_siret,
        raison_sociale,
        libelle_commune,
        acheteur_map,
        departement,
        nom_region,
        lien_annuaire,
    )
```

par :

```python
@callback(
    Output(component_id="acheteur_siret", component_property="children"),
    Output(component_id="acheteur_nom", component_property="children"),
    Output(component_id="acheteur_commune", component_property="children"),
    Output(component_id="acheteur_departement", component_property="children"),
    Output(component_id="acheteur_region", component_property="children"),
    Output(component_id="acheteur_lien_annuaire", component_property="href"),
    Input(component_id="acheteur_url", component_property="pathname"),
)
def update_acheteur_infos(url):
    acheteur_siret = url.split("/")[-1]
    data = get_annuaire_data(acheteur_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        code_departement, nom_departement, nom_region = get_departement_region(
            data_etablissement["code_postal"]
        )
        departement = f"{nom_departement} ({code_departement})"
        lien_annuaire = (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{acheteur_siret}"
        )
        raison_sociale = data["nom_raison_sociale"]
        libelle_commune = data_etablissement["libelle_commune"]

    else:
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = ""
        libelle_commune = ""

    return (
        acheteur_siret,
        raison_sociale,
        libelle_commune,
        departement,
        nom_region,
        lien_annuaire,
    )


@callback(
    Output(component_id="acheteur_map", component_property="children"),
    Input(component_id="acheteur_url", component_property="pathname"),
    Input(component_id="acheteur_year", component_property="value"),
)
def update_acheteur_map(pathname, ach_year):
    where_sql, params = _acheteur_scope(pathname, ach_year)
    geo_columns = [
        col
        for col in [
            "uid",
            "acheteur_longitude",
            "acheteur_latitude",
            "acheteur_nom",
            "titulaire_longitude",
            "titulaire_latitude",
            "titulaire_nom",
        ]
        if col in schema.names()
    ]
    dff = query_marches(where_sql, params, columns=geo_columns)
    return get_org_location_map(dff, "acheteur", "acheteur_map_leaflet")
```

- [ ] **Step 3: Vérifier qu'il n'y a plus de référence à `point_on_map` dans le fichier**

Run: `grep -n "point_on_map" src/pages/acheteur.py`
Expected: aucune sortie

- [ ] **Step 4: Lancer la suite de tests complète**

Run: `uv run pytest`
Expected: tous les tests passent

- [ ] **Step 5: Vérification manuelle dans le navigateur**

Run: `python run.py` (dans un terminal séparé, avec le `.venv` activé et un `.env` pointant vers un jeu de données de production contenant des colonnes longitude/latitude)

Naviguer vers `/acheteurs/<un-siret-existant>` :

- La carte doit afficher des marqueurs orange (acheteur) et bleus (titulaires), clusterisés.
- Les boutons de zoom +/- doivent être visibles sur la carte.
- Changer le filtre Année doit mettre à jour la carte.

Arrêter le serveur (`Ctrl+C`) une fois la vérification faite.

- [ ] **Step 6: Commit**

```bash
git add src/pages/acheteur.py
git commit -m "$(cat <<'EOF'
feat(acheteur): afficher les titulaires sur la carte de la fiche acheteur

EOF
)"
```

---

### Task 4: Brancher la carte sur `/titulaires/<id>` et supprimer `point_on_map`

**Files:**

- Modify: `src/pages/titulaire.py`
- Modify: `src/figures.py:184-254` (suppression de `point_on_map`)

**Interfaces:**

- Consumes: `get_org_location_map` (Task 2), `_titulaire_scope(pathname, titulaire_year) -> tuple[str, list]` (déjà existant, `src/pages/titulaire.py:49`)

- [ ] **Step 1: Mettre à jour l'import de `src.figures`**

Dans `src/pages/titulaire.py`, remplacer :

```python
from src.figures import (
    DataTable,
    get_distance_histogram,
    get_top_org_table,
    make_column_picker,
    point_on_map,
)
```

par :

```python
from src.figures import (
    DataTable,
    get_distance_histogram,
    get_org_location_map,
    get_top_org_table,
    make_column_picker,
)
```

- [ ] **Step 2: Retirer la construction de la carte de `update_titulaire_infos`**

Remplacer le callback existant (celui avec les `Output` `titulaire_siret`, `titulaire_nom`, `titulaire_commune`, `titulaire_map`, `titulaire_departement`, `titulaire_region`, `titulaire_lien_annuaire`, `titulaire_activite_libelle`) :

```python
@callback(
    Output(component_id="titulaire_siret", component_property="children"),
    Output(component_id="titulaire_nom", component_property="children"),
    Output(component_id="titulaire_commune", component_property="children"),
    Output(component_id="titulaire_map", component_property="children"),
    Output(component_id="titulaire_departement", component_property="children"),
    Output(component_id="titulaire_region", component_property="children"),
    Output(component_id="titulaire_lien_annuaire", component_property="href"),
    Output(component_id="titulaire_activite_libelle", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
)
def update_titulaire_infos(url):
    titulaire_siret = url.split("/")[-1]
    if "titulaire_activite_libelle" in DF_TITULAIRES.columns:
        activite_libelle_row = DF_TITULAIRES.filter(
            pl.col("titulaire_id") == titulaire_siret
        ).select("titulaire_activite_libelle")
        activite_libelle = (
            activite_libelle_row.item(0, 0) if activite_libelle_row.height > 0 else ""
        )
    else:
        activite_libelle = ""
    data = get_annuaire_data(titulaire_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        # Extraction du code département à partir du code postal
        code_postal = data_etablissement.get("code_postal", "")
        departement_code = code_postal[:2] if code_postal else None

        # Création de la carte avec le code département pour un centrage approprié
        titulaire_map = point_on_map(
            data_etablissement["latitude"],
            data_etablissement["longitude"],
            departement_code,
        )
        code_departement, nom_departement, nom_region = get_departement_region(
            data_etablissement["code_postal"]
        )
        departement = f"{nom_departement} ({code_departement})"
        lien_annuaire = (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{titulaire_siret}"
        )
        raison_sociale = data["nom_raison_sociale"]
        libelle_commune = data_etablissement["libelle_commune"]

    else:
        titulaire_map = html.Div()
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = html.Span(
            f"N° SIREN inconnu de l'INSEE ({titulaire_siret[:9]})"
        )
        libelle_commune = ""

    return (
        titulaire_siret,
        raison_sociale,
        libelle_commune,
        titulaire_map,
        departement,
        nom_region,
        lien_annuaire,
        activite_libelle,
    )
```

par :

```python
@callback(
    Output(component_id="titulaire_siret", component_property="children"),
    Output(component_id="titulaire_nom", component_property="children"),
    Output(component_id="titulaire_commune", component_property="children"),
    Output(component_id="titulaire_departement", component_property="children"),
    Output(component_id="titulaire_region", component_property="children"),
    Output(component_id="titulaire_lien_annuaire", component_property="href"),
    Output(component_id="titulaire_activite_libelle", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
)
def update_titulaire_infos(url):
    titulaire_siret = url.split("/")[-1]
    if "titulaire_activite_libelle" in DF_TITULAIRES.columns:
        activite_libelle_row = DF_TITULAIRES.filter(
            pl.col("titulaire_id") == titulaire_siret
        ).select("titulaire_activite_libelle")
        activite_libelle = (
            activite_libelle_row.item(0, 0) if activite_libelle_row.height > 0 else ""
        )
    else:
        activite_libelle = ""
    data = get_annuaire_data(titulaire_siret)
    data_etablissement = data.get("matching_etablissements") if data else None
    if data_etablissement:
        data_etablissement = data_etablissement[0]

        code_departement, nom_departement, nom_region = get_departement_region(
            data_etablissement["code_postal"]
        )
        departement = f"{nom_departement} ({code_departement})"
        lien_annuaire = (
            f"https://annuaire-entreprises.data.gouv.fr/etablissement/{titulaire_siret}"
        )
        raison_sociale = data["nom_raison_sociale"]
        libelle_commune = data_etablissement["libelle_commune"]

    else:
        code_departement, nom_departement, nom_region = "", "", ""
        departement = ""
        lien_annuaire = ""
        raison_sociale = html.Span(
            f"N° SIREN inconnu de l'INSEE ({titulaire_siret[:9]})"
        )
        libelle_commune = ""

    return (
        titulaire_siret,
        raison_sociale,
        libelle_commune,
        departement,
        nom_region,
        lien_annuaire,
        activite_libelle,
    )


@callback(
    Output(component_id="titulaire_map", component_property="children"),
    Input(component_id="titulaire_url", component_property="pathname"),
    Input(component_id="titulaire_year", component_property="value"),
)
def update_titulaire_map(pathname, titulaire_year):
    where_sql, params = _titulaire_scope(pathname, titulaire_year)
    geo_columns = [
        col
        for col in [
            "uid",
            "acheteur_longitude",
            "acheteur_latitude",
            "acheteur_nom",
            "titulaire_longitude",
            "titulaire_latitude",
            "titulaire_nom",
        ]
        if col in schema.names()
    ]
    dff = query_marches(where_sql, params, columns=geo_columns)
    return get_org_location_map(dff, "titulaire", "titulaire_map_leaflet")
```

- [ ] **Step 3: Supprimer `point_on_map` (devenue inutilisée) de `src/figures.py`**

Vérifier d'abord qu'il n'y a plus aucun appelant :

Run: `grep -rn "point_on_map" src/`
Expected: aucune sortie

Puis supprimer la fonction complète dans `src/figures.py` (actuellement lignes 184-254, entre `def point_on_map(lat, lon, departement_code=None):` et le `return html.Div(...)` qui la clôt, juste avant `class DataTable(dash_table.DataTable):`) :

```python
def point_on_map(lat, lon, departement_code=None):
    """Fonction améliorée utilisant les codes départementaux pour la détection de région.

    Args:
        lat: Coordonnée de latitude
        lon: Coordonnée de longitude
        departement_code: Code du département (ex: '75', '971', etc.)

    Returns:
        html.Div contenant la carte, ou div vide si invalide
    """
    # Validation des coordonnées
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return html.Div()  # Div vide pour les coordonnées invalides

    # Vérification que les coordonnées sont valides
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return html.Div()

    # Si aucun code département n'est fourni, retourner une div vide
    if not departement_code:
        return html.Div()

    # Détermination de la région en utilisant le code département
    # Logique identique à get_geographic_maps
    if departement_code in ["971", "972", "973", "974", "976"]:
        region_key = departement_code  # Département d'outre-mer
    elif len(departement_code) == 2:  # Département métropolitain
        region_key = "Hexagone"
    else:
        return html.Div()  # Format de code département invalide

    # Paramètres de carte par région (réutilisés de get_geographic_maps)
    regions = {
        "Hexagone": {"center": [46.6, 2.2], "zoom": 5},
        "971": {"center": [16.23, -61.55], "zoom": 9},  # Guadeloupe
        "972": {"center": [14.64, -61.02], "zoom": 10},  # Martinique
        "973": {"center": [3.93, -53.12], "zoom": 7},  # Guyane
        "974": {"center": [-21.11, 55.53], "zoom": 9},  # La Réunion
        "976": {"center": [-12.82, 45.16], "zoom": 10},  # Mayotte
    }

    settings = regions.get(region_key, regions["Hexagone"])

    # Création de la carte
    fig = px.scatter_map(
        lat=[lat],
        lon=[lon],
        height=300,
        # width=400,
        color=[1],
        zoom=settings["zoom"],
    )

    fig.update_traces(marker=dict(size=10))

    # Configuration de la carte (interactive - zoomable)
    fig.update_layout(
        map_style="light",  # Fond de carte clair
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        mapbox_center={"lat": settings["center"][0], "lon": settings["center"][1]},
        mapbox_zoom=settings["zoom"],
        coloraxis_showscale=False,
    )

    return html.Div(
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
    )
```

Supprimer l'intégralité de ce bloc (la ligne vide qui le sépare de `class DataTable` peut rester telle quelle).

- [ ] **Step 4: Lancer la suite de tests complète**

Run: `uv run pytest`
Expected: tous les tests passent

- [ ] **Step 5: Vérification manuelle dans le navigateur**

Run: `python run.py` (avec un jeu de données de production contenant des colonnes longitude/latitude)

Naviguer vers `/titulaires/<un-siret-existant>` :

- La carte doit afficher un marqueur bleu (titulaire) et des marqueurs orange (acheteurs), clusterisés.
- Les boutons de zoom +/- doivent être visibles.
- Changer le filtre Année doit mettre à jour la carte.

Arrêter le serveur (`Ctrl+C`) une fois la vérification faite.

- [ ] **Step 6: Commit**

```bash
git add src/pages/titulaire.py src/figures.py
git commit -m "$(cat <<'EOF'
feat(titulaire): afficher les acheteurs sur la carte de la fiche titulaire

Supprime point_on_map, devenue inutilisée après migration des deux pages
vers get_org_location_map.
EOF
)"
```
