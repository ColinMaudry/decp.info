import itertools

from src.auth import db as auth_db
from src.subscriptions import db as sub_db

_email_counter = itertools.count(1)


def _make_target_with_subscription():
    uid = auth_db.create_user(f"target{next(_email_counter)}@ex.fr", "hash")
    _handle, sub_id = sub_db.create_pending(uid, "cust-1", "simple")
    return uid, sub_id


def test_subscription_status_requires_admin(admin_client):
    resp = admin_client.post(
        "/admin/actions/subscription-status",
        data={"user_id": "1", "subscription_id": "1", "status": "active"},
    )
    assert resp.status_code == 404


def test_subscription_status_rejects_invalid_status(logged_in_admin_client):
    client, _admin_uid = logged_in_admin_client
    uid, sub_id = _make_target_with_subscription()

    resp = client.post(
        "/admin/actions/subscription-status",
        data={"user_id": str(uid), "subscription_id": str(sub_id), "status": "bogus"},
    )

    assert resp.status_code == 302
    assert resp.headers["Location"] == f"/admin/user/{uid}?error=invalid_status"
    assert sub_db.get_current(uid)["status"] == "pending"


def test_subscription_status_rejects_mismatched_subscription(logged_in_admin_client):
    client, _admin_uid = logged_in_admin_client
    uid, _sub_id = _make_target_with_subscription()
    other_uid, other_sub_id = _make_target_with_subscription()

    resp = client.post(
        "/admin/actions/subscription-status",
        data={
            "user_id": str(uid),
            "subscription_id": str(other_sub_id),
            "status": "active",
        },
    )

    assert resp.status_code == 302
    assert resp.headers["Location"] == f"/admin/user/{uid}?error=invalid_status"
    assert sub_db.get_current(other_uid)["status"] == "pending"


def test_subscription_status_success_updates_and_logs(logged_in_admin_client):
    from src.admin.db import list_actions

    client, _admin_uid = logged_in_admin_client
    uid, sub_id = _make_target_with_subscription()

    resp = client.post(
        "/admin/actions/subscription-status",
        data={"user_id": str(uid), "subscription_id": str(sub_id), "status": "active"},
    )

    assert resp.status_code == 302
    assert resp.headers["Location"] == f"/admin/user/{uid}?status_changed=1"
    assert sub_db.get_current(uid)["status"] == "active"

    actions = list_actions()
    assert len(actions) == 1
    assert actions[0]["action"] == "subscription_status_change"
    assert actions[0]["target_user_id"] == uid
    assert actions[0]["details"] == "pending → active"
    assert actions[0]["admin_email"] == "admin@ex.fr"
