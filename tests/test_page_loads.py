import os


def test_update_timestamp_falls_back_to_db_mtime(tmp_path, monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(u, "get_last_modified", boom)
    fb = tmp_path / "decp.duckdb"
    fb.write_bytes(b"x")
    assert get_data_update_timestamp("http://x", str(fb)) == os.path.getmtime(str(fb))


def test_update_timestamp_none_when_all_fail(monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(u, "get_last_modified", boom)
    assert get_data_update_timestamp("http://x", None) is None


def test_update_timestamp_nominal(monkeypatch):
    import src.utils as u
    from src.utils import get_data_update_timestamp

    monkeypatch.setattr(u, "get_last_modified", lambda p: 123.0)
    assert get_data_update_timestamp("http://x", None) == 123.0


def test_sources_tables_none_path():
    from src.figures import get_sources_tables

    div = get_sources_tables(None)
    assert "indisponible" in str(div.children).lower()


def test_sources_tables_missing_file():
    from src.figures import get_sources_tables

    div = get_sources_tables("/does/not/exist.csv")
    assert "indisponible" in str(div.children).lower()


def test_sources_tables_valid_csv(tmp_path):
    from dash import dash_table

    from src.figures import get_sources_tables

    csv = tmp_path / "s.csv"
    csv.write_text(
        "nom,organisation,nb_marchés,nb_acheteurs,code,url,unique\n"
        "Source A,Org A,5,2,XA,http://a,1\n"
    )
    div = get_sources_tables(str(csv))
    assert isinstance(div.children, dash_table.DataTable)
