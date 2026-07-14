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
    assert token.startswith("colibre_")
    assert len(token) == len("colibre_") + 64  # 32 octets hex = 64 chars
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
    assert tokens_db.get_token_by_plaintext(temp_db, "colibre_zzz") is None


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


def test_create_token_defaults_to_api_kind(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x")
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row["kind"] == "api"


def test_create_token_with_mcp_kind(temp_db):
    token, _ = tokens_db.create_token(temp_db, "x", user_id=7, kind="mcp")
    row = tokens_db.get_token_by_plaintext(temp_db, token)
    assert row["kind"] == "mcp"
    assert row["user_id"] == 7


def test_list_user_tokens_filters_by_user_and_kind(temp_db):
    tokens_db.create_token(temp_db, "mcp-u1", user_id=1, kind="mcp")
    tokens_db.create_token(temp_db, "api-u1", user_id=1, kind="api")
    tokens_db.create_token(temp_db, "mcp-u2", user_id=2, kind="mcp")
    rows = tokens_db.list_user_tokens(temp_db, 1, "mcp")
    assert [r["label"] for r in rows] == ["mcp-u1"]


def test_revoke_user_token_revokes_own(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    assert tokens_db.revoke_user_token(temp_db, token_id, 1) is True
    assert tokens_db.get_token_by_plaintext(temp_db, token)["revoked_at"] is not None


def test_revoke_user_token_refuses_other_owner(temp_db):
    token, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    assert tokens_db.revoke_user_token(temp_db, token_id, 999) is False
    assert tokens_db.get_token_by_plaintext(temp_db, token)["revoked_at"] is None


def test_revoke_user_token_already_revoked_returns_false(temp_db):
    _, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    assert tokens_db.revoke_user_token(temp_db, token_id, 1) is True
    assert tokens_db.revoke_user_token(temp_db, token_id, 1) is False


def test_create_token_stores_recoverable_encrypted_token(temp_db, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "s3cr3t-test-key")
    token, token_id = tokens_db.create_token(temp_db, "x", user_id=7, kind="mcp")
    with sqlite3.connect(str(temp_db)) as conn:
        enc = conn.execute(
            "SELECT token_enc FROM api_tokens WHERE id = ?", (token_id,)
        ).fetchone()[0]
    assert enc is not None
    assert token not in enc  # chiffré, jamais en clair dans la base
    assert tokens_db.get_token_plaintext_for_user(temp_db, token_id, 7) == token


def test_get_token_plaintext_scoped_to_owner(temp_db, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "s3cr3t-test-key")
    _, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    assert tokens_db.get_token_plaintext_for_user(temp_db, token_id, 999) is None


def test_get_token_plaintext_none_when_no_key(temp_db, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    _, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    assert tokens_db.get_token_plaintext_for_user(temp_db, token_id, 1) is None


def test_get_token_plaintext_none_after_key_rotation(temp_db, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "key-A")
    _, token_id = tokens_db.create_token(temp_db, "x", user_id=1, kind="mcp")
    monkeypatch.setenv("SECRET_KEY", "key-B")  # rotation → indéchiffrable
    assert tokens_db.get_token_plaintext_for_user(temp_db, token_id, 1) is None
