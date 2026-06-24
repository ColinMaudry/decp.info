import gzip
import sqlite3
import tempfile
from pathlib import Path


def make_snapshot(db_path: Path) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(tmp_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return gzip.compress(tmp_path.read_bytes())
    finally:
        tmp_path.unlink(missing_ok=True)


def write_snapshot(gzipped: bytes, dest: Path) -> None:
    dest.write_bytes(gzip.decompress(gzipped))


def verify_integrity(db_path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.DatabaseError:
        return False
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return row is not None and row[0] == "ok"
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()
