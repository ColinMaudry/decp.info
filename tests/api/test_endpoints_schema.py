def test_schema_accessible_without_token(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/schema")
    assert resp.status_code == 200


def test_schema_returns_fields(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/schema")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "fields" in data
    assert isinstance(data["fields"], list)
    assert len(data["fields"]) > 0
    first = data["fields"][0]
    assert set(first.keys()) >= {"name", "type", "title", "description"}
    names = [f["name"] for f in data["fields"]]
    assert "uid" in names
