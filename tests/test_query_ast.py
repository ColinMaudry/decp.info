import polars as pl

from src.utils.query_ast import And, Condition, Not, Or, ast_to_sql

SCHEMA = pl.Schema(
    {
        "acheteur_nom": pl.String,
        "objet": pl.String,
        "montant": pl.Float64,
        "dureeMois": pl.Int64,
        "dateNotification": pl.Date,
    }
)


def _run(node):
    """Compile et retourne (sql, params)."""
    return ast_to_sql(node, SCHEMA)


def test_none_is_true():
    assert _run(None) == ("TRUE", [])


def test_empty_and_is_true():
    assert _run(And([])) == ("TRUE", [])


def test_text_contains_uses_ilike_and_params():
    sql, params = _run(Condition("objet", "contains", "voirie"))
    assert "ILIKE ?" in sql
    assert params == ["%voirie%"]


def test_text_contains_multiword_is_and():
    sql, params = _run(Condition("objet", "contains", "metropole rennes"))
    assert sql.count("ILIKE ?") == 2
    assert params == ["%metropole%", "%rennes%"]


def test_text_contains_wildcard_and_phrase():
    _, params = _run(Condition("objet", "contains", "distri* metropole+rennes"))
    assert params == ["distri%", "%metropole rennes%"]


def test_text_notcontains_negates():
    sql, params = _run(Condition("objet", "notContains", "construction"))
    assert "NOT (" in sql
    assert params == ["%construction%"]


def test_numeric_gt():
    sql, params = _run(Condition("montant", "gt", 40000))
    assert '"montant" > ?' in sql
    assert params == [40000.0]


def test_numeric_eq_int_column():
    sql, params = _run(Condition("dureeMois", "eq", "12"))
    assert '"dureeMois" = ?' in sql
    assert params == [12]


def test_numeric_range():
    sql, params = _run(Condition("montant", "range", 100, 200))
    assert params == [100.0, 200.0]
    assert "BETWEEN" in sql or ("> ?" in sql and "< ?" in sql)


def test_numeric_invalid_value_is_true():
    # valeur non numérique -> condition neutralisée (TRUE), pas d'exception
    assert _run(Condition("montant", "gt", "abc")) == ("TRUE", [])


def test_date_gt_casts_varchar():
    sql, params = _run(Condition("dateNotification", "gt", "2022"))
    assert "VARCHAR" in sql
    assert params == ["2022"]


def test_blank_and_notblank():
    sql_b, _ = _run(Condition("objet", "blank"))
    assert "IS NULL" in sql_b
    sql_nb, _ = _run(Condition("objet", "notBlank"))
    assert "IS NOT NULL" in sql_nb


def test_unknown_column_is_true():
    assert _run(Condition("colonne_inexistante", "contains", "x")) == ("TRUE", [])


def test_and_or_not_grouping():
    node = And(
        [
            Or(
                [
                    Condition("objet", "contains", "beton"),
                    Condition("objet", "contains", "ciment"),
                ]
            ),
            Not(Condition("objet", "contains", "demolition")),
        ]
    )
    sql, params = _run(node)
    assert " OR " in sql and " AND " in sql and "NOT (" in sql
    assert params == ["%beton%", "%ciment%", "%demolition%"]
