import urllib.parse

from src.utils.table import build_view_query


def test_empty_inputs_give_empty_string():
    assert build_view_query(None, None, None) == ""
    assert build_view_query("", [], []) == ""


def test_filter_only():
    q = build_view_query("{objet} icontains route", None, None)
    params = urllib.parse.parse_qs(q)
    assert params["filtres"] == ["{objet} icontains route"]
    assert "tris" not in params
    assert "colonnes" not in params


def test_sort_is_json_encoded():
    sort_by = [{"column_id": "montant", "direction": "desc"}]
    q = build_view_query(None, sort_by, None)
    params = urllib.parse.parse_qs(q)
    import json

    assert json.loads(params["tris"][0]) == sort_by


def test_hidden_columns_become_visible_csv():
    # build_view_query reçoit les colonnes MASQUÉES et stocke les VISIBLES
    q = build_view_query(None, None, ["objet"])
    params = urllib.parse.parse_qs(q)
    visible = params["colonnes"][0].split(",")
    assert "objet" not in visible
    assert len(visible) > 0
