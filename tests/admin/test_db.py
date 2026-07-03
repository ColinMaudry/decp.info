from src.admin import db as admin_db
from src.auth.db import init_schema
from src.migrations import apply_pending
from src.subscriptions.db import init_schema as init_subscriptions_schema


def _setup():
    init_schema()
    init_subscriptions_schema()
    apply_pending()


def test_log_action_then_list_actions_returns_it(users_db_path):
    _setup()

    admin_db.log_action(
        "admin@ex.fr", "subscription_status_change", 42, "active → cancelled"
    )

    rows = admin_db.list_actions()
    assert len(rows) == 1
    assert rows[0]["admin_email"] == "admin@ex.fr"
    assert rows[0]["action"] == "subscription_status_change"
    assert rows[0]["target_user_id"] == 42
    assert rows[0]["details"] == "active → cancelled"


def test_list_actions_most_recent_first(users_db_path):
    _setup()

    admin_db.log_action("admin@ex.fr", "action_one", None, None)
    admin_db.log_action("admin@ex.fr", "action_two", None, None)

    rows = admin_db.list_actions()
    assert [r["action"] for r in rows] == ["action_two", "action_one"]


def test_list_actions_respects_limit(users_db_path):
    _setup()

    for i in range(3):
        admin_db.log_action("admin@ex.fr", f"action_{i}", None, None)

    rows = admin_db.list_actions(limit=2)
    assert len(rows) == 2
