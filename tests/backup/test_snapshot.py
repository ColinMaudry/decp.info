import sqlite3
from pathlib import Path

from src.backup.snapshot import make_snapshot, verify_integrity, write_snapshot


def _make_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")
    conn.commit()
    conn.close()


def test_snapshot_roundtrip_preserves_rows(tmp_path):
    src = tmp_path / "users.sqlite"
    _make_db(src)
    gzipped = make_snapshot(src)
    restored = tmp_path / "restored.sqlite"
    write_snapshot(gzipped, restored)
    conn = sqlite3.connect(str(restored))
    rows = conn.execute("SELECT id, val FROM t ORDER BY id").fetchall()
    conn.close()
    assert rows == [(1, "a"), (2, "b")]


def test_verify_integrity_ok(tmp_path):
    src = tmp_path / "users.sqlite"
    _make_db(src)
    assert verify_integrity(src) is True


def test_verify_integrity_detects_corruption(tmp_path):
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"this is not a sqlite database")
    assert verify_integrity(bad) is False
