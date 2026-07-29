import hashlib
import hmac

import pytest

from src.utils.chatwoot import (
    build_identity_script,
    build_reset_script,
    build_widget_script,
)


def test_no_token_returns_empty_string():
    assert build_widget_script(None) == ""


def test_empty_token_returns_empty_string():
    assert build_widget_script("") == ""


def test_token_produces_script_with_token_and_managed_base_url():
    script = build_widget_script("PVejdJRyKtSZdEkJtDJQ3xCd")
    assert "<script>" in script
    assert "websiteToken: 'PVejdJRyKtSZdEkJtDJQ3xCd'" in script
    assert "baseUrl: BASE_URL" in script
    assert 'BASE_URL="https://app.chatwoot.com"' in script


def test_identity_without_identifier_or_email_returns_empty_string():
    assert build_identity_script(None, "a@b.fr") == ""
    assert build_identity_script(42, None) == ""
    assert build_identity_script(42, "") == ""


def test_identity_sets_user_on_ready_with_identifier_and_email():
    script = build_identity_script(42, "colin@example.fr")
    assert 'window.addEventListener("chatwoot:ready"' in script
    assert '$chatwoot.setUser("42", {"email": "colin@example.fr"})' in script


def test_identity_without_hmac_token_omits_identifier_hash():
    assert "identifier_hash" not in build_identity_script(42, "colin@example.fr")


def test_identity_with_hmac_token_hashes_the_identifier():
    token = "un-token-hmac"  # noqa: S105
    expected = hmac.new(token.encode(), b"42", hashlib.sha256).hexdigest()
    script = build_identity_script(42, "colin@example.fr", hmac_token=token)
    assert f'"identifier_hash": "{expected}"' in script


def test_identity_escapes_angle_brackets_to_prevent_script_injection():
    script = build_identity_script(42, "</script><script>alert(1)</script>@x.fr")
    assert "</script><script>" not in script
    assert script.count("</script>") == 1
    assert "\\u003c/script" in script


def test_identity_without_custom_attributes_omits_the_call():
    script = build_identity_script(42, "colin@example.fr")
    assert "setCustomAttributes" not in script


def test_identity_with_custom_attributes_sets_them_after_set_user():
    script = build_identity_script(
        42, "colin@example.fr", custom_attributes={"statut_abonnement": "active"}
    )
    assert '$chatwoot.setCustomAttributes({"statut_abonnement": "active"})' in script
    assert script.index("setUser") < script.index("setCustomAttributes")


def test_identity_with_empty_custom_attributes_omits_the_call():
    # setCustomAttributes({}) lève côté SDK ("should have atleast one key").
    assert "setCustomAttributes" not in build_identity_script(
        42, "colin@example.fr", custom_attributes={}
    )


# --- Attributs d'abonnement (src.utils.chatwoot.subscription_attributes) ---


@pytest.fixture
def users_db_path(monkeypatch, tmp_path):
    from src.auth.db import reset_conn_for_tests

    monkeypatch.setenv("USERS_DB_PATH", str(tmp_path / "users.test.sqlite"))
    reset_conn_for_tests()
    yield
    reset_conn_for_tests()


@pytest.fixture
def user_id(users_db_path):
    from src.auth import db as auth_db
    from src.subscriptions import db as subs_db

    auth_db.init_schema()
    subs_db.init_schema()
    return auth_db.create_user("colin@example.fr", "x" * 20)


def _insert_subscription(user_id, **cols):
    from src.auth.db import get_conn

    fields = {
        "user_id": user_id,
        "created_at": "2026-01-01",
        "updated_at": "2026-01-01",
    }
    fields.update(cols)
    placeholders = ", ".join("?" for _ in fields)
    get_conn().execute(
        f"INSERT INTO subscriptions ({', '.join(fields)}) VALUES ({placeholders})",
        tuple(fields.values()),
    )


def test_attributs_sans_abonnement(user_id):
    from src.utils.chatwoot import subscription_attributes

    assert subscription_attributes(user_id) == {"statut_abonnement": "aucun"}


def test_attributs_avec_abonnement_actif(user_id):
    from src.utils.chatwoot import subscription_attributes

    _insert_subscription(
        user_id,
        status="active",
        plan="soutien",
        current_period_end="2026-09-01T00:00:00Z",
    )
    assert subscription_attributes(user_id) == {
        "statut_abonnement": "active",
        "offre": "Abonnement de soutien ✊",
        "fin_periode": "2026-09-01T00:00:00Z",
    }


def test_attributs_plan_inconnu_retombe_sur_la_cle_brute(user_id):
    from src.utils.chatwoot import subscription_attributes

    _insert_subscription(user_id, status="pending", plan="plan-supprime")
    attrs = subscription_attributes(user_id)
    assert attrs == {"statut_abonnement": "pending", "offre": "plan-supprime"}


def test_attributs_prend_le_dernier_abonnement(user_id):
    from src.utils.chatwoot import subscription_attributes

    _insert_subscription(user_id, status="expired", plan="simple")
    _insert_subscription(user_id, status="active", plan="simple")
    assert subscription_attributes(user_id)["statut_abonnement"] == "active"


def test_reset_script_calls_reset_on_ready():
    script = build_reset_script()
    assert 'window.addEventListener("chatwoot:ready"' in script
    assert "$chatwoot.reset()" in script


# --- Injection dans la page servie (src.app._interpolate_index_per_request) ---


class _FakeUser:
    is_authenticated = True
    id = 7
    email = "colin@example.fr"


@pytest.fixture
def client(monkeypatch):
    from src import app as app_module

    # Le widget est désactivé pendant les tests (CHATWOOT_WEBSITE_TOKEN absent),
    # or l'injection de l'identité est conditionnée à sa présence : on simule un
    # widget actif sans charger le SDK.
    monkeypatch.setattr(app_module, "chatwoot_script", "<!-- widget -->")
    return app_module.app.server.test_client()


def _anonymous(monkeypatch):
    from src import app as app_module

    monkeypatch.setattr(
        app_module, "current_user", type("A", (), {"is_authenticated": False})()
    )


def test_page_sans_widget_n_injecte_rien(monkeypatch):
    from src import app as app_module

    monkeypatch.setattr(app_module, "chatwoot_script", "")
    monkeypatch.setattr(app_module, "current_user", _FakeUser())
    html = app_module.app.server.test_client().get("/").get_data(as_text=True)
    assert "setUser" not in html


def test_page_visiteur_anonyme_n_injecte_pas_d_identite(client, monkeypatch):
    _anonymous(monkeypatch)
    html = client.get("/").get_data(as_text=True)
    assert "setUser" not in html
    assert "$chatwoot.reset()" not in html


def test_page_utilisateur_connecte_injecte_set_user_et_attributs(client, monkeypatch):
    from src import app as app_module

    monkeypatch.setattr(app_module, "current_user", _FakeUser())
    monkeypatch.setattr(
        app_module, "subscription_attributes", lambda _: {"statut_abonnement": "trial"}
    )
    html = client.get("/").get_data(as_text=True)
    assert '$chatwoot.setUser("7", {"email": "colin@example.fr"})' in html
    assert '$chatwoot.setCustomAttributes({"statut_abonnement": "trial"})' in html


def test_page_retour_de_deconnexion_injecte_le_reset(client, monkeypatch):
    _anonymous(monkeypatch)
    html = client.get("/?deconnexion=1").get_data(as_text=True)
    assert "$chatwoot.reset()" in html
    assert "setUser" not in html


def test_page_suppression_de_compte_injecte_le_reset(client, monkeypatch):
    _anonymous(monkeypatch)
    html = client.get("/?account_deleted=1").get_data(as_text=True)
    assert "$chatwoot.reset()" in html
