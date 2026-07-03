import polars as pl


def _make_lff(rows):
    return pl.LazyFrame(rows)


def test_compute_considerations_stats_basic():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            # u1 : social oui (Clause), env non (Sans objet)
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            # u2 : social non (Sans objet), env oui (Critère)
            {
                "uid": "u2",
                "considerationsSociales": "Sans objet",
                "considerationsEnvironnementales": "Critère environnemental",
            },
            # u3 : social oui (Marché réservé), env null
            {
                "uid": "u3",
                "considerationsSociales": "Marché réservé",
                "considerationsEnvironnementales": None,
            },
            # u4 : social autre valeur (pas "Sans objet"), env null
            {
                "uid": "u4",
                "considerationsSociales": "Pas de considération sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
        ]
    )

    stats = compute_considerations_stats(lff)

    # champs_renseignes : basé sur sociales. 4 non-null / 4 total -> (4, 100%).
    assert stats["champs_renseignes"] == (4, 100)
    # Sociales renseignées : dén=4 non-null, num=3 != "Sans objet" (u1/u3/u4) -> (4, 3, 75%).
    assert stats["sociales_renseignees"] == (4, 3, 75)
    # Env renseignées : dén=3 non-null (u1/u2/u4), num=1 != "Sans objet" (u2) -> (3, 1, 33%).
    assert stats["environnementales_renseignees"] == (3, 1, 33)


def test_compute_considerations_stats_dedup_per_uid():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            # u1 présent 2 fois (2 titulaires) -> compté une seule fois
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            {
                "uid": "u2",
                "considerationsSociales": "Sans objet",
                "considerationsEnvironnementales": "Sans objet",
            },
        ]
    )

    stats = compute_considerations_stats(lff)

    # 2 uid distincts. Social 2 non-null, 1 != "Sans objet" (u1) -> (2, 1, 50%).
    assert stats["champs_renseignes"] == (2, 100)
    assert stats["sociales_renseignees"] == (2, 1, 50)
    # Env 2 non-null, 0 != "Sans objet" -> (2, 0, 0%).
    assert stats["environnementales_renseignees"] == (2, 0, 0)


def test_compute_considerations_stats_missing_column():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            {"uid": "u1", "considerationsSociales": "Clause sociale"},
            {"uid": "u2", "considerationsSociales": "Sans objet"},
        ]
    )

    stats = compute_considerations_stats(lff)

    # Colonne env absente -> (0, 0). Social : 2 non-null, 1 != "Sans objet" -> (2, 1, 50%).
    assert stats["champs_renseignes"] == (2, 100)
    assert stats["sociales_renseignees"] == (2, 1, 50)
    assert stats["environnementales_renseignees"] == (0, 0)


def test_compute_considerations_stats_empty():
    from src.figures import compute_considerations_stats

    lff = pl.LazyFrame(
        {
            "uid": pl.Series([], dtype=pl.String),
            "considerationsSociales": pl.Series([], dtype=pl.String),
            "considerationsEnvironnementales": pl.Series([], dtype=pl.String),
        }
    )

    stats = compute_considerations_stats(lff)

    assert stats["champs_renseignes"] == (0, 0)
    assert stats["sociales_renseignees"] == (0, 0)
    assert stats["environnementales_renseignees"] == (0, 0)


def test_get_considerations_card_content_returns_three_progress_bars():
    import dash_bootstrap_components as dbc
    from dash import html

    from src.figures import get_considerations_card_content

    lff = pl.LazyFrame(
        [
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            {
                "uid": "u2",
                "considerationsSociales": "Sans objet",
                "considerationsEnvironnementales": "Critère environnemental",
            },
        ]
    )

    div = get_considerations_card_content(lff)

    assert isinstance(div, html.Div)

    def find_progress(component, found):
        if isinstance(component, dbc.Progress):
            found.append(component)
        children = getattr(component, "children", None)
        if isinstance(children, (list, tuple)):
            for c in children:
                find_progress(c, found)
        elif children is not None and not isinstance(children, str):
            find_progress(children, found)
        return found

    inner_bars = [b for b in find_progress(div, []) if getattr(b, "bar", False)]
    assert len(inner_bars) == 3

    bar_ren, bar_social, bar_env = inner_bars
    # Bar 1 : champs renseignés (2/2 = 100%, gris)
    assert bar_ren.value == 100
    assert bar_ren.color == "#6c757d"
    # Bar 2 : sociales parmi renseignés (u1 != "Sans objet" -> 1/2 = 50%, rose)
    assert bar_social.value == 50
    assert bar_social.color == "#CC6677"
    # Bar 3 : env parmi renseignés (u2 != "Sans objet" -> 1/2 = 50%, vert)
    assert bar_env.value == 50
    assert bar_env.color == "#117733"


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
