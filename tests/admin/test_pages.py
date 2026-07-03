import uuid

from dash.testing.composite import DashComposite
from selenium.webdriver.support.ui import Select
from werkzeug.security import generate_password_hash

from src.auth import db as auth_db
from src.subscriptions import db as sub_db

PASSWORD = "s3cretpass!"


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@ex.fr"


def _make_verified_user(email: str) -> int:
    auth_db.init_schema()
    uid = auth_db.create_user(email, generate_password_hash(PASSWORD))
    auth_db.set_email_verified(uid)
    return uid


def _cleanup_user(user_id: int) -> None:
    conn = auth_db.get_conn()
    conn.execute("DELETE FROM admin_actions WHERE target_user_id = ?", (user_id,))
    conn.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM subscriber_state WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    # tests/users.test.sqlite is committed to git and shared by the whole
    # Selenium session (USERS_DB_PATH is set globally in pyproject.toml).
    # Row DELETEs alone leave the file byte-diffed: AUTOINCREMENT tables
    # record their high-water mark in sqlite_sequence, and that table is
    # never rolled back by DELETE (by SQLite design). Reset it explicitly so
    # a full test run leaves the committed file untouched (`git status`
    # clean), matching the pre-existing convention for this file where
    # users/subscriptions already sit at seq=0.
    conn.execute(
        "UPDATE sqlite_sequence SET seq = 0 "
        "WHERE name IN ('users', 'subscriptions', 'admin_actions')"
    )


def _login(dash_duo: DashComposite, email: str):
    dash_duo.driver.get(dash_duo.server_url + "/connexion")
    dash_duo.wait_for_element("input[name=email]", timeout=8).send_keys(email)
    dash_duo.driver.find_element("css selector", "input[name=password]").send_keys(
        PASSWORD
    )
    dash_duo.driver.find_element("css selector", "button[type=submit]").click()


def test_admin_anonymous_gets_404(dash_duo: DashComposite):
    from src.app import app

    dash_duo.start_server(app)
    dash_duo.driver.get(dash_duo.server_url + "/admin")
    dash_duo.wait_for_text_to_equal("#admin-404-heading", "404", timeout=8)


def test_admin_non_admin_gets_404(dash_duo: DashComposite, monkeypatch):
    from src.app import app

    monkeypatch.setenv("ADMIN_EMAIL", "admin-only@ex.fr")
    email = _unique_email("regular")
    uid = _make_verified_user(email)
    try:
        dash_duo.start_server(app)
        _login(dash_duo, email)
        # Confirm login actually succeeded before relying on the admin guard.
        # A failed login (bad credentials, unverified email, ...) redirects
        # back to /connexion rather than raising, leaving the session
        # anonymous — which would also yield a 404 at /admin and make this
        # test indistinguishable from test_admin_anonymous_gets_404. Since
        # this user has no subscription, a successful login redirects to
        # /compte/abonnement (see _post_login_url in src/auth/routes.py).
        dash_duo.wait_for_text_to_equal("h2", "Abonnement", timeout=8)
        assert "/connexion" not in dash_duo.driver.current_url

        dash_duo.driver.get(dash_duo.server_url + "/admin")
        dash_duo.wait_for_text_to_equal("#admin-404-heading", "404", timeout=8)
    finally:
        _cleanup_user(uid)


def test_admin_full_flow(dash_duo: DashComposite, monkeypatch):
    from src.app import app

    admin_email = _unique_email("admin")
    monkeypatch.setenv("ADMIN_EMAIL", admin_email)
    admin_uid = _make_verified_user(admin_email)

    target_email = _unique_email("target")
    target_uid = _make_verified_user(target_email)
    sub_db.init_schema()
    _handle, sub_id = sub_db.create_pending(target_uid, "cust-e2e", "simple", 20.0)
    sub_db.set_status(sub_id, "active")

    try:
        dash_duo.start_server(app)
        _login(dash_duo, admin_email)

        dash_duo.driver.get(dash_duo.server_url + "/admin")
        dash_duo.wait_for_text_to_equal("h2", "Panneau admin", timeout=8)
        assert target_email in dash_duo.driver.page_source

        dash_duo.driver.get(f"{dash_duo.server_url}/admin/user/{target_uid}")
        dash_duo.wait_for_text_to_equal("h2", "Panneau admin", timeout=8)
        assert target_email in dash_duo.driver.page_source

        select = Select(
            dash_duo.driver.find_element("css selector", "select[name=status]")
        )
        select.select_by_value("cancelled")
        dash_duo.driver.find_element("css selector", "button[type=submit]").click()

        dash_duo.wait_for_text_to_equal(
            ".alert-success", "Statut de l'abonnement mis à jour.", timeout=8
        )
        assert "cancelled" in dash_duo.driver.page_source

        dash_duo.driver.get(dash_duo.server_url + "/admin/journal")
        dash_duo.wait_for_text_to_equal("h2", "Journal des actions admin", timeout=8)
        assert "subscription_status_change" in dash_duo.driver.page_source
        assert "active → cancelled" in dash_duo.driver.page_source
    finally:
        _cleanup_user(target_uid)
        _cleanup_user(admin_uid)
