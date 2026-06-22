import polars as pl


def _make_lff(rows):
    return pl.LazyFrame(rows)


def test_compute_considerations_stats_basic():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            # uid u1 : social oui (Clause), env non (Sans objet)
            {
                "uid": "u1",
                "considerationsSociales": "Clause sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
            # uid u2 : social non (Sans objet), env oui (Critère)
            {
                "uid": "u2",
                "considerationsSociales": "Sans objet",
                "considerationsEnvironnementales": "Critère environnemental",
            },
            # uid u3 : social oui (Marché réservé compte), env null
            {
                "uid": "u3",
                "considerationsSociales": "Marché réservé",
                "considerationsEnvironnementales": None,
            },
            # uid u4 : aucune considération
            {
                "uid": "u4",
                "considerationsSociales": "Pas de considération sociale",
                "considerationsEnvironnementales": "Sans objet",
            },
        ]
    )

    stats = compute_considerations_stats(lff)

    # 4 marchés au total. Social : u1, u3 -> 2/4 = 50%. Env : u2 -> 1/4 = 25%.
    assert stats["sociales"] == (2, 50)
    assert stats["environnementales"] == (1, 25)


def test_compute_considerations_stats_dedup_per_uid():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            # uid u1 présent 2 fois (2 titulaires) -> compté une seule fois
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

    # 2 marchés distincts. Social : u1 -> 1/2 = 50%.
    assert stats["sociales"] == (1, 50)
    assert stats["environnementales"] == (0, 0)


def test_compute_considerations_stats_missing_column():
    from src.figures import compute_considerations_stats

    lff = _make_lff(
        [
            {"uid": "u1", "considerationsSociales": "Clause sociale"},
            {"uid": "u2", "considerationsSociales": "Sans objet"},
        ]
    )

    stats = compute_considerations_stats(lff)

    # Colonne env absente -> (0, 0) sans exception. Social : 1/2 = 50%.
    assert stats["sociales"] == (1, 50)
    assert stats["environnementales"] == (0, 0)


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

    assert stats["sociales"] == (0, 0)
    assert stats["environnementales"] == (0, 0)


def test_get_considerations_card_content_returns_two_progress_bars():
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

    # Récupère récursivement tous les dbc.Progress
    def find_progress(component, found):
        children = getattr(component, "children", None)
        if isinstance(component, dbc.Progress):
            found.append(component)
        if isinstance(children, (list, tuple)):
            for c in children:
                find_progress(c, found)
        elif children is not None:
            find_progress(children, found)
        return found

    bars = find_progress(div, [])
    assert len(bars) == 2

    # Sociales (rouge) : u1 -> 50%. Environnementales (vert) : u2 -> 50%.
    social_bar, env_bar = bars[0], bars[1]
    assert social_bar.value == 50
    assert social_bar.label == "50 %"
    assert social_bar.style["backgroundColor"] == "rgb(204, 102, 119)"
    assert env_bar.value == 50
    assert env_bar.label == "50 %"
    assert env_bar.style["backgroundColor"] == "rgb(17, 119, 51)"
