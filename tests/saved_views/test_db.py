from src.auth import db as auth_db
from src.saved_views import db


def _make_user(email="u@ex.fr"):
    auth_db.init_schema()
    return auth_db.create_user(email, "hash")


def test_init_schema_creates_table(users_db_path):
    db.init_schema()
    conn = auth_db.get_conn()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "saved_views" in tables


def test_upsert_creates_and_lists(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.upsert(uid, "tableau", "Ma vue", "filtres=foo")
    views = db.list_views(uid, "tableau")
    assert len(views) == 1
    assert views[0]["name"] == "Ma vue"
    assert views[0]["query"] == "filtres=foo"


def test_upsert_same_name_overwrites(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.upsert(uid, "tableau", "Ma vue", "filtres=foo")
    db.upsert(uid, "tableau", "Ma vue", "filtres=bar")
    views = db.list_views(uid, "tableau")
    assert len(views) == 1
    assert views[0]["query"] == "filtres=bar"


def test_list_views_is_isolated_per_user(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    assert db.list_views(uid2, "tableau") == []


def test_rename_only_affects_owner(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    view_id = db.list_views(uid1, "tableau")[0]["id"]
    db.rename(view_id, uid2, "Pirate")  # mauvais propriétaire → no-op
    assert db.get(view_id, uid1)["name"] == "Vue A"
    db.rename(view_id, uid1, "Vue B")
    assert db.get(view_id, uid1)["name"] == "Vue B"


def test_delete_only_affects_owner(users_db_path):
    db.init_schema()
    uid1 = _make_user("a@ex.fr")
    uid2 = _make_user("b@ex.fr")
    db.upsert(uid1, "tableau", "Vue A", "filtres=a")
    view_id = db.list_views(uid1, "tableau")[0]["id"]
    db.delete(view_id, uid2)  # mauvais propriétaire → no-op
    assert db.get(view_id, uid1) is not None
    db.delete(view_id, uid1)
    assert db.get(view_id, uid1) is None


def test_views_deleted_on_user_cascade(users_db_path):
    db.init_schema()
    uid = _make_user()
    db.upsert(uid, "tableau", "Vue A", "filtres=a")
    auth_db.delete_user(uid)
    assert db.list_views(uid, "tableau") == []
