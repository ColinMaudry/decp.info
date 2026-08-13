from src.auth import db, tokens
from src.subscriptions import db as sub_db


def test_verify_email_valid_token_logs_in_and_redirects_to_abonnement(
    client, users_db_path
):
    db.init_schema()
    sub_db.init_schema()
    uid = db.create_user("a@b.c", "hash")
    token = tokens.create_verification_token(uid)

    resp = client.get(f"/auth/verify-email?token={token}")
    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert location.startswith("/compte/abonnement")
    assert "mes-infos" not in location
    assert "essai=demarre" in location
    assert db.get_user_by_id(uid)["email_verified"] == 1
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == str(uid)


def test_verify_email_valid_token_starts_trial(client, users_db_path):
    db.init_schema()
    sub_db.init_schema()
    uid = db.create_user("essai@b.c", "hash")
    token = tokens.create_verification_token(uid)

    assert sub_db.trial_ends_at(uid) is None

    resp = client.get(f"/auth/verify-email?token={token}")

    assert resp.status_code == 302
    assert sub_db.trial_active(uid) is True


def test_verify_email_tous_abonnes_redirects_to_abonnement(
    client, users_db_path, monkeypatch
):
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    db.init_schema()
    sub_db.init_schema()
    uid = db.create_user("t@b.c", "hash")
    token = tokens.create_verification_token(uid)

    resp = client.get(f"/auth/verify-email?token={token}")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc.startswith("/compte/abonnement")
    assert "mes-infos" not in loc


def test_verify_email_tous_abonnes_opens_no_trial(client, users_db_path, monkeypatch):
    """Sous TOUS_ABONNES, l'accès est déjà gratuit pour tout le monde : ouvrir
    un essai qui expirerait sans jamais avoir été vécu comme tel n'a aucun
    sens, et `essai=demarre` annoncerait un événement qui n'a pas eu lieu."""
    monkeypatch.setattr("src.utils.TOUS_ABONNES", True)
    db.init_schema()
    sub_db.init_schema()
    uid = db.create_user("essai-tous-abonnes@b.c", "hash")
    token = tokens.create_verification_token(uid)

    resp = client.get(f"/auth/verify-email?token={token}")

    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc == "/compte/abonnement"
    assert "essai" not in loc
    assert sub_db.trial_ends_at(uid) is None
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == str(uid)


def test_verify_email_invalid_token(client):
    resp = client.get("/auth/verify-email?token=invalide")
    assert "error=invalid_token" in resp.headers["Location"]


def test_verify_email_missing_token(client):
    resp = client.get("/auth/verify-email")
    assert "error=invalid_token" in resp.headers["Location"]


def test_verify_email_single_use(client, users_db_path):
    db.init_schema()
    sub_db.init_schema()
    uid = db.create_user("a@b.c", "h")
    token = tokens.create_verification_token(uid)
    client.get(f"/auth/verify-email?token={token}")
    resp = client.get(f"/auth/verify-email?token={token}")
    assert "error=invalid_token" in resp.headers["Location"]
