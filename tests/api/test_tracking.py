from src.api import tokens_db, tracking


def test_counter_worker_increments_count(temp_db):
    _, token_id = tokens_db.create_token(temp_db, "x")

    tracking.start_worker(str(temp_db))
    try:
        tracking.enqueue_counter_update(token_id)
        tracking.enqueue_counter_update(token_id)
        # Laisser le worker drainer la queue
        tracking.flush(timeout=2.0)
    finally:
        tracking.stop_worker()

    rows = tokens_db.list_tokens(temp_db)
    assert rows[0]["count_total"] == 2
    assert rows[0]["last_used_at"] is not None


def test_after_request_hook_increments_counter_async(api_client, valid_token_header):
    client, db_path = api_client
    # Récupérer le token_id du token créé par la fixture
    from src.api import tokens_db, tracking

    rows = tokens_db.list_tokens(db_path)
    assert len(rows) == 1  # vérification du token créé par la fixture

    # Faire une requête (qui doit déclencher l'incrément)
    client.get("/api/v1/health")  # pas authentifiée → ne compte pas
    client.get("/api/v1/schema", headers=valid_token_header)

    tracking.flush(timeout=2.0)

    rows = tokens_db.list_tokens(db_path)
    assert rows[0]["count_total"] == 1


def test_matomo_disabled_skips_call(monkeypatch, api_client, valid_token_header):
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "false")
    client, _ = api_client

    from src.api import tracking

    called = []
    monkeypatch.setattr(
        tracking,
        "_post_matomo",
        lambda **kw: called.append(kw),
    )
    client.get("/api/v1/health")
    tracking.flush(timeout=2.0)
    assert called == []


def test_matomo_enabled_posts_event(monkeypatch, api_client, valid_token_header):
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")

    from src.api import tracking

    captured = []
    monkeypatch.setattr(
        tracking,
        "_post_matomo",
        lambda **kw: captured.append(kw),
    )

    client, _ = api_client
    client.get("/api/v1/schema", headers=valid_token_header)
    tracking.flush(timeout=2.0)

    assert len(captured) == 1
    call = captured[0]
    assert call["params"]["idsite"] == "42"
    assert call["params"]["rec"] == "1"
    assert "token-" in call["params"]["uid"]
    assert call["params"]["dimension2"] == "200"
