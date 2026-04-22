import polars as pl

SCHEMA = pl.Schema(
    {
        "uid": pl.String,
        "objet": pl.String,
        "acheteur_id": pl.String,
        "montant": pl.Float64,
        "dureeMois": pl.Int64,
        "dateNotification": pl.Date,
    }
)


def test_empty_filter_returns_true():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("", SCHEMA)
    assert where == "TRUE"
    assert params == []


def test_icontains_string_is_case_insensitive_like():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{objet} icontains travaux", SCHEMA)
    assert where == '"objet" IS NOT NULL AND "objet" <> \'\' AND "objet" ILIKE ?'
    assert params == ["%travaux%"]


def test_icontains_with_trailing_wildcard_is_starts_with():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql(
        "{acheteur_id} icontains 24350013900189*", SCHEMA
    )
    assert (
        where
        == '"acheteur_id" IS NOT NULL AND "acheteur_id" <> \'\' AND "acheteur_id" ILIKE ?'
    )
    assert params == ["24350013900189%"]


def test_icontains_with_leading_wildcard_is_ends_with():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{uid} icontains *2024", SCHEMA)
    assert where == '"uid" IS NOT NULL AND "uid" <> \'\' AND "uid" ILIKE ?'
    assert params == ["%2024"]


def test_numeric_greater_than():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{montant} i> 40000", SCHEMA)
    assert where == '"montant" IS NOT NULL AND "montant" > ?'
    assert params == [40000.0]


def test_numeric_less_than():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{montant} i< 1000", SCHEMA)
    assert where == '"montant" IS NOT NULL AND "montant" < ?'
    assert params == [1000.0]


def test_numeric_equality_via_icontains():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{dureeMois} icontains 12", SCHEMA)
    assert where == '"dureeMois" IS NOT NULL AND "dureeMois" = ?'
    assert params == [12]


def test_date_column_treated_as_string_ilike():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{dateNotification} icontains 2024*", SCHEMA)
    assert "ILIKE" in where
    assert params == ["2024%"]


def test_multiple_filters_joined_by_and():
    from src.utils.table_sql import filter_query_to_sql

    filter_query = "{objet} icontains voirie && {montant} i> 40000"
    where, params = filter_query_to_sql(filter_query, SCHEMA)
    assert " AND " in where
    assert params == ["%voirie%", 40000.0]


def test_invalid_numeric_value_is_skipped():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{montant} i> notanumber", SCHEMA)
    assert where == "TRUE"
    assert params == []


def test_unknown_column_is_skipped():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql("{inexistant} icontains foo", SCHEMA)
    assert where == "TRUE"
    assert params == []


def test_escapes_identifier_with_quotes_not_concatenation():
    from src.utils.table_sql import filter_query_to_sql

    where, params = filter_query_to_sql(
        "{objet} icontains '; DROP TABLE decp; --", SCHEMA
    )
    assert "DROP TABLE" not in where
    assert any("DROP TABLE" in str(p) for p in params)


def test_sort_by_empty():
    from src.utils.table_sql import sort_by_to_sql

    assert sort_by_to_sql([], SCHEMA) == ""
    assert sort_by_to_sql(None, SCHEMA) == ""


def test_sort_by_single_column_desc():
    from src.utils.table_sql import sort_by_to_sql

    result = sort_by_to_sql([{"column_id": "montant", "direction": "desc"}], SCHEMA)
    assert result == '"montant" DESC NULLS LAST'


def test_sort_by_multiple_columns_preserves_order():
    from src.utils.table_sql import sort_by_to_sql

    result = sort_by_to_sql(
        [
            {"column_id": "dateNotification", "direction": "desc"},
            {"column_id": "montant", "direction": "asc"},
        ],
        SCHEMA,
    )
    assert result == '"dateNotification" DESC NULLS LAST, "montant" ASC NULLS LAST'


def test_sort_by_ignores_unknown_column():
    from src.utils.table_sql import sort_by_to_sql

    result = sort_by_to_sql([{"column_id": "fake", "direction": "asc"}], SCHEMA)
    assert result == ""
