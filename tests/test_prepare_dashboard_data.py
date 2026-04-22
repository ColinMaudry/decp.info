import polars as pl


def test_returns_dataframe_with_year_filter():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(dashboard_year="2025")
    assert isinstance(dff, pl.DataFrame)
    assert dff.height == 1


def test_year_mismatch_returns_empty():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(dashboard_year="2024")
    assert isinstance(dff, pl.DataFrame)
    assert dff.height == 0


def test_acheteur_id_partial_match():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(
        dashboard_year="2025",
        dashboard_acheteur_id="12",
    )
    assert dff.height == 1


def test_departement_in_clause():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(
        dashboard_year="2025",
        dashboard_acheteur_departement_code=["75", "92"],
    )
    assert dff.height == 1


def test_montant_min_above_value_excludes_row():
    from src.utils.data import prepare_dashboard_data

    dff = prepare_dashboard_data(
        dashboard_year="2025",
        dashboard_montant_min=1000,
    )
    assert dff.height == 0
