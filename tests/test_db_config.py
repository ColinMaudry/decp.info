"""Bornage des ressources DuckDB (chantier 1).

Les défauts DuckDB (`threads` = tous les cœurs, `memory_limit` = 80 % de la RAM)
s'appliquent **par processus** et ignorent les limites cgroup. Avec plusieurs
workers gunicorn, chaque processus croit disposer de la machine entière.
"""

import duckdb

from src.db import configure_connection


def _reglage(conn: duckdb.DuckDBPyConnection, nom: str):
    return conn.execute(f"SELECT current_setting('{nom}')").fetchone()[0]


def test_configure_connection_applique_le_nombre_de_threads(monkeypatch):
    monkeypatch.setenv("DUCKDB_THREADS", "3")

    conn = duckdb.connect()
    configure_connection(conn)

    assert _reglage(conn, "threads") == 3


def test_configure_connection_applique_la_limite_memoire(monkeypatch):
    defaut = _reglage(duckdb.connect(), "memory_limit")
    monkeypatch.setenv("DUCKDB_MEMORY_LIMIT", "512MB")

    conn = duckdb.connect()
    configure_connection(conn)

    assert _reglage(conn, "memory_limit") != defaut


def test_configure_connection_sans_variables_preserve_les_defauts(monkeypatch):
    """Sans configuration explicite, on ne change pas le comportement existant."""
    monkeypatch.delenv("DUCKDB_THREADS", raising=False)
    monkeypatch.delenv("DUCKDB_MEMORY_LIMIT", raising=False)
    defaut = _reglage(duckdb.connect(), "threads")

    conn = duckdb.connect()
    configure_connection(conn)

    assert _reglage(conn, "threads") == defaut


def test_configure_connection_avertit_si_non_borne(monkeypatch, caplog):
    """L'absence de bornage doit être visible dans les logs de démarrage."""
    monkeypatch.delenv("DUCKDB_THREADS", raising=False)
    monkeypatch.delenv("DUCKDB_MEMORY_LIMIT", raising=False)

    with caplog.at_level("WARNING"):
        configure_connection(duckdb.connect())

    assert any("DUCKDB_THREADS" in message for message in caplog.messages)
