import polars as pl

from src.db import aggregate_marches


def test_aggregate_groupby_count_returns_named_columns():
    df = aggregate_marches(
        select_sql='"acheteur_departement_code", COUNT("uid") AS "uid__count"',
        group_by='"acheteur_departement_code"',
    )
    assert isinstance(df, pl.DataFrame)
    assert df.columns == ["acheteur_departement_code", "uid__count"]
    assert df["uid__count"].sum() > 0


def test_aggregate_global_without_groupby_returns_one_row():
    df = aggregate_marches(select_sql='COUNT("uid") AS "uid__count"')
    assert df.height == 1
    assert df["uid__count"][0] > 0
