import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id       TEXT PRIMARY KEY,
    client_metadata TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_codes (
    code_hash             TEXT PRIMARY KEY,
    client_id             TEXT NOT NULL,
    user_id               INTEGER NOT NULL,
    redirect_uri          TEXT,
    code_challenge        TEXT,
    code_challenge_method TEXT,
    scope                 TEXT,
    resource              TEXT,
    expires_at            TEXT NOT NULL,
    used                  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS oauth_tokens (
    id                 INTEGER PRIMARY KEY,
    access_token_hash  TEXT NOT NULL UNIQUE,
    refresh_token_hash TEXT UNIQUE,
    client_id          TEXT NOT NULL,
    user_id            INTEGER NOT NULL,
    scope              TEXT,
    resource           TEXT NOT NULL,
    issued_at          TEXT NOT NULL,
    access_expires_at  TEXT NOT NULL,
    refresh_expires_at TEXT,
    revoked_at         TEXT,
    count_total        INTEGER NOT NULL DEFAULT 0,
    last_used_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_access ON oauth_tokens(access_token_hash);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_refresh ON oauth_tokens(refresh_token_hash);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def _connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_schema(db_path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def create_client(db_path, client_id: str, metadata: dict) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO oauth_clients (client_id, client_metadata, created_at) "
            "VALUES (?, ?, ?)",
            (client_id, json.dumps(metadata), _utcnow_iso()),
        )
        conn.commit()


def get_client(db_path, client_id: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_clients WHERE client_id = ?", (client_id,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["client_metadata"] = json.loads(d["client_metadata"])
    return d


def save_code(
    db_path,
    code: str,
    *,
    client_id: str,
    user_id: int,
    redirect_uri: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
    scope: str | None,
    resource: str | None,
    expires_at: str,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO oauth_codes (code_hash, client_id, user_id, redirect_uri, "
            "code_challenge, code_challenge_method, scope, resource, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _hash(code),
                client_id,
                user_id,
                redirect_uri,
                code_challenge,
                code_challenge_method,
                scope,
                resource,
                expires_at,
            ),
        )
        conn.commit()


def get_code(db_path, code: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_codes WHERE code_hash = ?", (_hash(code),)
        ).fetchone()
    return dict(row) if row else None


def delete_code(db_path, code: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM oauth_codes WHERE code_hash = ?", (_hash(code),))
        conn.commit()


def save_token(
    db_path,
    *,
    access_token: str,
    refresh_token: str | None,
    client_id: str,
    user_id: int,
    scope: str | None,
    resource: str,
    access_expires_at: str,
    refresh_expires_at: str | None,
) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO oauth_tokens (access_token_hash, refresh_token_hash, "
            "client_id, user_id, scope, resource, issued_at, access_expires_at, "
            "refresh_expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _hash(access_token),
                _hash(refresh_token) if refresh_token else None,
                client_id,
                user_id,
                scope,
                resource,
                _utcnow_iso(),
                access_expires_at,
                refresh_expires_at,
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_token_by_access(db_path, access_token: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE access_token_hash = ?",
            (_hash(access_token),),
        ).fetchone()
    return dict(row) if row else None


def get_token_by_refresh(db_path, refresh_token: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM oauth_tokens WHERE refresh_token_hash = ?",
            (_hash(refresh_token),),
        ).fetchone()
    return dict(row) if row else None


def revoke_token(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE oauth_tokens SET revoked_at = ? WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()


def increment_usage(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE oauth_tokens SET count_total = count_total + 1, last_used_at = ? "
            "WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()
