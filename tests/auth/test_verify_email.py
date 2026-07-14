from src.auth import db, tokens


def test_verify_email_valid_token_logs_in_and_redirects_to_mes_infos(
    client, users_db_path
):
    db.init_schema()
    uid = db.create_user("a@b.c", "hash")
    token = tokens.create_verification_token(uid)

    resp = client.get(f"/auth/verify-email?token={token}")
    assert resp.status_code == 302
    assert "/compte/abonnement/mes-infos" in resp.headers["Location"]
    assert db.get_user_by_id(uid)["email_verified"] == 1
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == str(uid)


def test_verify_email_tous_abonnes_redirects_to_abonnement(
    client, users_db_path, monkeypatch
):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    db.init_schema()
    uid = db.create_user("t@b.c", "hash")
    token = tokens.create_verification_token(uid)

    resp = client.get(f"/auth/verify-email?token={token}")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc.endswith("/compte/abonnement")
    assert "mes-infos" not in loc


def test_verify_email_invalid_token(client):
    resp = client.get("/auth/verify-email?token=invalide")
    assert "error=invalid_token" in resp.headers["Location"]


def test_verify_email_missing_token(client):
    resp = client.get("/auth/verify-email")
    assert "error=invalid_token" in resp.headers["Location"]


def test_verify_email_single_use(client, users_db_path):
    db.init_schema()
    uid = db.create_user("a@b.c", "h")
    token = tokens.create_verification_token(uid)
    client.get(f"/auth/verify-email?token={token}")
    resp = client.get(f"/auth/verify-email?token={token}")
    assert "error=invalid_token" in resp.headers["Location"]
