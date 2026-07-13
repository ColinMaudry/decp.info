from datetime import datetime, timedelta, timezone

from src.mcp import usage


def test_record_and_count_since(tmp_path):
    db = tmp_path / "u.sqlite"
    usage.init_schema(db)
    usage.record(db, user_id=7, token_id=1, kind="oauth")
    usage.record(db, user_id=7, token_id=1, kind="oauth")
    usage.record(db, user_id=9, token_id=2, kind="static")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert usage.count_since(db, 7, past) == 2
    assert usage.count_since(db, 9, past) == 1


def test_record_never_raises(tmp_path):
    # base non initialisée → record ne doit pas lever
    usage.record(tmp_path / "missing.sqlite", user_id=1, token_id=1, kind="oauth")


def test_purge_older_than(tmp_path):
    db = tmp_path / "u.sqlite"
    usage.init_schema(db)
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(
        timespec="seconds"
    )
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO mcp_usage (user_id, token_id, kind, created_at) VALUES (7, 1, 'oauth', ?)",
        (old,),
    )
    conn.commit()
    conn.close()
    usage.purge_older_than(db, days=90)
    past = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    assert usage.count_since(db, 7, past) == 0
