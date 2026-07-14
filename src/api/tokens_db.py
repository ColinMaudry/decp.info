import base64
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

TOKEN_PREFIX = "colibre_"

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_tokens (
    id           INTEGER PRIMARY KEY,
    token_hash   TEXT NOT NULL UNIQUE,
    token_enc    TEXT,
    label        TEXT NOT NULL,
    user_id      INTEGER,
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    count_total  INTEGER NOT NULL DEFAULT 0,
    revoked_at   TEXT,
    kind         TEXT NOT NULL DEFAULT 'api'
);
CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fernet_key() -> bytes | None:
    """Clé Fernet dérivée de SECRET_KEY (séparation de domaine).

    Renvoie None si SECRET_KEY est absent : le jeton n'est alors pas chiffré
    ni ré-affichable (dégradation propre, sans échec).
    """
    secret = os.getenv("SECRET_KEY")
    if not secret:
        return None
    digest = hashlib.sha256(f"mcp-token-enc:{secret}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


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


def create_token(
    db_path, label: str, user_id: int | None = None, kind: str = "api"
) -> tuple[str, int]:
    token = TOKEN_PREFIX + secrets.token_hex(32)
    key = _fernet_key()
    token_enc = Fernet(key).encrypt(token.encode()).decode() if key else None
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO api_tokens (token_hash, token_enc, label, user_id, kind, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (_hash(token), token_enc, label, user_id, kind, _utcnow_iso()),
        )
        conn.commit()
        return token, cur.lastrowid


def get_token_by_plaintext(db_path, token: str) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM api_tokens WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()
    return dict(row) if row else None


def get_token_plaintext_for_user(db_path, token_id: int, user_id: int) -> str | None:
    """Déchiffre et renvoie le jeton en clair, uniquement pour son propriétaire.

    Renvoie None si : SECRET_KEY absent, jeton inexistant/appartenant à un autre
    utilisateur, jamais chiffré (token_enc NULL), ou indéchiffrable (clé changée).
    """
    key = _fernet_key()
    if key is None:
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT token_enc FROM api_tokens WHERE id = ? AND user_id = ?",
            (token_id, user_id),
        ).fetchone()
    if row is None or row["token_enc"] is None:
        return None
    try:
        return Fernet(key).decrypt(row["token_enc"].encode()).decode()
    except InvalidToken:
        return None


def revoke_token(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE api_tokens SET revoked_at = ? WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()


def increment_usage(db_path, token_id: int) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE api_tokens "
            "SET count_total = count_total + 1, last_used_at = ? "
            "WHERE id = ?",
            (_utcnow_iso(), token_id),
        )
        conn.commit()


def list_tokens(db_path) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM api_tokens ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def list_user_tokens(db_path, user_id: int, kind: str = "mcp") -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM api_tokens WHERE user_id = ? AND kind = ? "
            "ORDER BY created_at DESC, id DESC",
            (user_id, kind),
        ).fetchall()
    return [dict(r) for r in rows]


def revoke_user_token(db_path, token_id: int, user_id: int) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE api_tokens SET revoked_at = ? "
            "WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (_utcnow_iso(), token_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
