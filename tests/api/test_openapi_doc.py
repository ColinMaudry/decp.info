def test_openapi_documents_new_keywords(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    raw = resp.get_data(as_text=True)
    for keyword in [
        "count_results",
        "differs",
        "groupby",
        "__sum",
        "__avg",
        "__min",
        "__max",
    ]:
        assert keyword in raw, f"{keyword} absent de la doc OpenAPI"
