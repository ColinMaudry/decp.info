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
