import datetime

import polars as pl

from src.mcp.serialization import to_json_records


def test_dates_become_iso_strings():
    df = pl.DataFrame({"d": [datetime.date(2025, 1, 1)], "n": [10]})
    assert to_json_records(df) == [{"d": "2025-01-01", "n": 10}]


def test_none_is_preserved():
    df = pl.DataFrame({"nom": [None], "x": [3]})
    assert to_json_records(df) == [{"nom": None, "x": 3}]


def test_strings_and_numbers_untouched():
    df = pl.DataFrame({"s": ["abc"], "f": [1.5]})
    assert to_json_records(df) == [{"s": "abc", "f": 1.5}]
