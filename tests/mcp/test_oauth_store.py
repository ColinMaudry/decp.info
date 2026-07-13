from src.mcp.oauth import store


def test_create_and_get_client(tmp_path):
    db = tmp_path / "u.sqlite"
    store.init_schema(db)
    meta = {
        "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "scope": "mcp",
    }
    store.create_client(db, "abc123", meta)
    row = store.get_client(db, "abc123")
    assert row["client_id"] == "abc123"
    assert row["client_metadata"] == meta
    assert store.get_client(db, "nope") is None


def test_save_get_delete_code(tmp_path):
    db = tmp_path / "u.sqlite"
    store.init_schema(db)
    store.save_code(
        db,
        "thecode",
        client_id="abc",
        user_id=7,
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        code_challenge="chal",
        code_challenge_method="S256",
        scope="mcp",
        resource="https://colibre.fr/_mcp",
        expires_at="2999-01-01T00:00:00+00:00",
    )
    row = store.get_code(db, "thecode")
    assert row["user_id"] == 7
    assert row["code_challenge"] == "chal"
    assert row["resource"] == "https://colibre.fr/_mcp"
    store.delete_code(db, "thecode")
    assert store.get_code(db, "thecode") is None


def test_save_get_revoke_token(tmp_path):
    db = tmp_path / "u.sqlite"
    store.init_schema(db)
    tid = store.save_token(
        db,
        access_token="acc",
        refresh_token="ref",
        client_id="abc",
        user_id=7,
        scope="mcp",
        resource="https://colibre.fr/_mcp",
        access_expires_at="2999-01-01T00:00:00+00:00",
        refresh_expires_at="2999-01-01T00:00:00+00:00",
    )
    assert store.get_token_by_access(db, "acc")["id"] == tid
    assert store.get_token_by_refresh(db, "ref")["user_id"] == 7
    store.increment_usage(db, tid)
    assert store.get_token_by_access(db, "acc")["count_total"] == 1
    store.revoke_token(db, tid)
    assert store.get_token_by_access(db, "acc")["revoked_at"] is not None
