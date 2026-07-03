import pytest

from src.admin import tables


def test_get_rows_users_excludes_password_hash(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    auth_db.create_user("a@ex.fr", "secret-hash")

    rows = tables.get_rows("users")

    assert rows[0]["email"] == "a@ex.fr"
    assert "password_hash" not in rows[0]


def test_set_cell_rejects_unknown_table(users_db_path):
    with pytest.raises(ValueError):
        tables.set_cell("not_a_table", 1, "email", "x@ex.fr")


def test_set_cell_rejects_non_editable_column(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")

    with pytest.raises(ValueError):
        tables.set_cell("users", uid, "id", "999")


def test_set_cell_rejects_invalid_dropdown_value(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    with pytest.raises(ValueError):
        tables.set_cell("subscriptions", sub_id, "status", "not_a_status")


def test_set_cell_rejects_bad_type(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    with pytest.raises(ValueError):
        tables.set_cell("subscriptions", sub_id, "prix_ht", "not-a-number")


def test_set_cell_writes_valid_value(users_db_path):
    from src.auth import db as auth_db

    auth_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")

    tables.set_cell("users", uid, "siret", "12345678900011")

    rows = tables.get_rows("users")
    assert rows[0]["siret"] == "12345678900011"


def test_set_cell_coerces_numeric_type(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    auth_db.init_schema()
    sub_db.init_schema()
    uid = auth_db.create_user("a@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")

    tables.set_cell("subscriptions", sub_id, "prix_ht", "30")

    rows = tables.get_rows("subscriptions")
    assert rows[0]["prix_ht"] == 30.0


def test_find_changed_cell_detects_single_diff():
    data = [{"id": 1, "email": "new@ex.fr"}]
    data_previous = [{"id": 1, "email": "old@ex.fr"}]

    result = tables.find_changed_cell(data, data_previous)

    assert result == (0, "email", "old@ex.fr", "new@ex.fr")


def test_find_changed_cell_returns_none_when_identical():
    data = [{"id": 1, "email": "a@ex.fr"}]
    data_previous = [{"id": 1, "email": "a@ex.fr"}]

    assert tables.find_changed_cell(data, data_previous) is None


def test_find_changed_cell_returns_none_when_schemas_differ():
    # Mimics switching from "users" to "admin_actions" mid-callback: the two
    # tables' row lists happen to have the same length but different
    # columns, so this must not be mistaken for a genuine cell edit.
    data = [{"id": 1, "email": "a@ex.fr"}]
    data_previous = [{"id": 1, "admin_email": "x@ex.fr"}]

    assert tables.find_changed_cell(data, data_previous) is None


def test_find_changed_cell_returns_none_when_previous_is_none():
    assert tables.find_changed_cell([{"id": 1}], None) is None


def test_target_user_id_per_table():
    assert tables.TABLES["users"].target_user_id({"id": 7}) == 7
    assert tables.TABLES["subscriptions"].target_user_id({"user_id": 9}) == 9
    assert tables.TABLES["subscriber_state"].target_user_id({"user_id": 3}) == 3
    assert tables.TABLES["admin_actions"].target_user_id({"id": 1}) is None
