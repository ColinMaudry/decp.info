def test_schema_without_token_returns_401(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/schema")
    assert resp.status_code == 401


def test_schema_returns_columns(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/schema", headers=valid_token_header)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "columns" in data
    assert isinstance(data["columns"], list)
    assert len(data["columns"]) > 0
    first = data["columns"][0]
    assert set(first.keys()) >= {"name", "type"}
    # uid doit être présent dans le schéma DECP de test
    names = [c["name"] for c in data["columns"]]
    assert "uid" in names
