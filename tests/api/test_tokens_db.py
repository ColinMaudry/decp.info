import sqlite3

from src.api import tokens_db


def test_init_schema_creates_table(temp_db):
    with sqlite3.connect(str(temp_db)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_tokens'"
        ).fetchall()
    assert rows == [("api_tokens",)]


def test_create_token_returns_plaintext_and_stores_hash(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "test-label")
    assert token.startswith("decpinfo_")
    assert len(token) == len("decpinfo_") + 64  # 32 octets hex = 64 chars
    assert token_id >= 1

    with sqlite3.connect(str(temp_db)) as conn:
        row = conn.execute(
            "SELECT token_hash, label, count_total FROM api_tokens WHERE id = ?",
            (token_id,),
        ).fetchone()
    assert row[1] == "test-label"
    assert row[2] == 0
    assert row[0] != token  # stocké en clair impossible
    assert len(row[0]) == 64  # sha256 hex


def test_get_token_by_plaintext_returns_row(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row is not None
    assert row["id"] == token_id
    assert row["label"] == "x"
    assert row["revoked_at"] is None


def test_get_token_unknown_returns_none(temp_db):
    assert tokens_db.get_token_by_plaintext(temp_db, "decpinfo_zzz") is None


def test_revoke_token_sets_revoked_at(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    tokens_db.revoke_token(temp_db, token_id)
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row["revoked_at"] is not None


def test_increment_usage_updates_counter_and_timestamp(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    tokens_db.increment_usage(temp_db, token_id)
    tokens_db.increment_usage(temp_db, token_id)
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row["count_total"] == 2
    assert row["last_used_at"] is not None


def test_list_tokens_returns_all(temp_db):
    tokens_db.create_token(temp_db, "a")
    tokens_db.create_token(temp_db, "b")
    rows = tokens_db.list_tokens(temp_db)
    assert [r["label"] for r in rows] == ["a", "b"]
