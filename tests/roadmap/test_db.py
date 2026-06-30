from src.auth import db as auth_db
from src.roadmap import db as roadmap_db


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def test_init_schema_creates_feature_votes(users_db_path):
    roadmap_db.init_schema()
    conn = auth_db.get_conn()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "feature_votes" in tables


def test_record_vote_and_counts(users_db_path):
    roadmap_db.init_schema()
    uid = _make_user()
    roadmap_db.record_vote(uid, 42)
    roadmap_db.record_vote(uid, 42)  # vote multiple autorisé
    roadmap_db.record_vote(uid, 7)
    assert roadmap_db.vote_counts() == {42: 2, 7: 1}


def test_vote_counts_empty(users_db_path):
    roadmap_db.init_schema()
    assert roadmap_db.vote_counts() == {}
