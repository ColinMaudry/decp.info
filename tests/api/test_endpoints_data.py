def test_data_without_token_returns_401(api_client):
    client, _ = api_client
    resp = client.get("/api/v1/data")
    assert resp.status_code == 401


def test_data_default_pagination(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) >= {"data", "meta", "links"}
    assert isinstance(body["data"], list)
    assert len(body["data"]) <= 50  # default page_size
    assert body["meta"]["page"] == 1
    assert body["meta"]["page_size"] == 50
    assert "total" in body["meta"]


def test_data_count_false_omits_total(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?count=false", headers=valid_token_header)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "total" not in body["meta"]


def test_data_page_size_max_enforced(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?page_size=5000", headers=valid_token_header)
    assert resp.status_code == 400


def test_data_page_size_below_min_rejected(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?page_size=0", headers=valid_token_header)
    assert resp.status_code == 400


def test_data_pagination_links(api_client, valid_token_header):
    client, _ = api_client
    resp = client.get("/api/v1/data?page=1&page_size=1", headers=valid_token_header)
    body = resp.get_json()
    assert body["links"]["prev"] is None
    if body["meta"]["total"] > 1:
        assert body["links"]["next"] is not None
        assert "page=2" in body["links"]["next"]
