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
    # Renseignées : dénominateur = non-null ; numérateur = non-null ET != "Sans objet".
    # Social : 4 non-null, 3 != "Sans objet" (u1/u3/u4) -> (4, 75%).
    # Env : 3 non-null, 1 != "Sans objet" (u2) -> (3, 33%).
    assert stats["sociales_renseignees"] == (4, 75)
    assert stats["environnementales_renseignees"] == (3, 33)


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
    # Social : 2 non-null, 1 positif -> (2, 50%). Env : 2 non-null, 0 positif -> (2, 0%).
    assert stats["sociales_renseignees"] == (2, 50)
    assert stats["environnementales_renseignees"] == (2, 0)


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
    # Social : 2 non-null, 1 positif -> (2, 50%). Env absente -> (0, 0).
    assert stats["sociales_renseignees"] == (2, 50)
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

    assert stats["sociales"] == (0, 0)
    assert stats["environnementales"] == (0, 0)
    assert stats["sociales_renseignees"] == (0, 0)
    assert stats["environnementales_renseignees"] == (0, 0)


def test_get_considerations_card_content_returns_four_progress_bars():
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

    all_bars = find_progress(div, [])
    inner_bars = [b for b in all_bars if getattr(b, "bar", False)]
    # 4 barres internes : 2 positives + 2 renseignées
    assert len(inner_bars) == 4

    social_pos, social_ren, env_pos, env_ren = inner_bars
    # Sociales positives : u1 -> 1/2 = 50%
    assert social_pos.value == 50
    assert social_pos.color == "#CC6677"
    assert social_pos.style["color"] == "white"
    # Sociales renseignées : 2 non-null, 1 positif (u1) -> 50%
    assert social_ren.value == 50
    assert social_ren.color == "#E5B2BB"
    # Environnementales positives : u2 -> 1/2 = 50%
    assert env_pos.value == 50
    assert env_pos.color == "#117733"
    assert env_pos.style["color"] == "white"
    # Environnementales renseignées : 2 non-null (u1 "Sans objet", u2), 1 positif (u2) -> 50%
    assert env_ren.value == 50
    assert env_ren.color == "#88BB99"
