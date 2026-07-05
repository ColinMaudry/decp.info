import pytest

from src.subscriptions import client


def test_auth_and_base_url_used(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "colibre-1"}))
    client.get_customer("colibre-1")
    call = fake_httpx["calls"][0]
    assert call["url"] == "https://api.test/v1/customer/colibre-1"
    assert call["auth"] == ("priv_test", "")


def test_get_customer(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "colibre-1"}))
    result = client.get_customer("colibre-1")
    assert result == {"handle": "colibre-1"}


def test_update_customer(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "colibre-1"}))
    client.update_customer("colibre-1", {"email": "a@b.fr"})
    call = fake_httpx["calls"][0]
    assert call["method"] == "PUT"
    assert call["json"] == {"email": "a@b.fr"}


def test_create_subscription_session_with_customer_handle(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "abo-1-1"}))
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {"id": "cs_1", "url": "https://checkout.reepay.com/#/subscription/cs_1"},
        )
    )
    url = client.create_subscription_session(
        "plan_simple",
        "abo-1-1",
        "https://app/ok",
        "https://app/ko",
        customer_handle="colibre-1",
    )
    assert url == "https://checkout.reepay.com/#/subscription/cs_1"

    create_body = fake_httpx["calls"][0]["json"]
    assert create_body["plan"] == "plan_simple"
    assert create_body["handle"] == "abo-1-1"
    assert create_body["customer"] == "colibre-1"
    assert create_body["signup_method"] == "link"
    assert "generate_handle" not in create_body
    assert "prepare_subscription" not in create_body
    # accept_url/cancel_url n'existent pas dans CreateSubscription : ils
    # doivent passer par la session de checkout dédiée, pas ce body.
    assert "accept_url" not in create_body
    assert "cancel_url" not in create_body

    session_call = fake_httpx["calls"][1]
    assert (
        session_call["url"]
        == "https://checkout-api.frisbii.com/v1/session/subscription"
    )
    assert session_call["json"] == {
        "subscription": "abo-1-1",
        "accept_url": "https://app/ok",
        "cancel_url": "https://app/ko",
    }


def test_create_subscription_session_no_trial(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "abo-1-2"}))
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200, {"url": "https://checkout.reepay.com/#/subscription/cs_2"}
        )
    )
    client.create_subscription_session(
        "plan_simple",
        "abo-1-2",
        "https://app/ok",
        "https://app/ko",
        no_trial=True,
        customer_handle="colibre-1",
    )
    assert fake_httpx["calls"][0]["json"]["no_trial"] is True


def test_http_error_raises_frisbii_error(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](500, {"error": "boom"}))
    with pytest.raises(client.FrisbiiError) as exc:
        client.get_plan("plan_simple")
    assert exc.value.status_code == 500


def test_get_payment_info_url_appends_query_params(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "handle": "abo-1-1",
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/#/subscription/pay/en_GB/x/abo-1-1"
                },
            },
        )
    )
    url = client.get_payment_info_url(
        "abo-1-1",
        "https://app/compte/abonnement?carte=succes",
        "https://app/compte/abonnement?carte=annule",
    )
    assert url.startswith(
        "https://checkout.reepay.com/#/subscription/pay/en_GB/x/abo-1-1"
    )
    assert "accept_url=https%3A%2F%2Fapp%2Fcompte%2Fabonnement%3Fcarte%3Dsucces" in url
    assert "cancel_url=https%3A%2F%2Fapp%2Fcompte%2Fabonnement%3Fcarte%3Dannule" in url


def test_get_payment_info_url_merges_existing_query_string(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "handle": "abo-1-2",
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/pay/abo-1-2?locale=fr"
                },
            },
        )
    )
    url = client.get_payment_info_url("abo-1-2", "https://app/ok", "https://app/ko")
    assert "locale=fr" in url
    assert "accept_url=https%3A%2F%2Fapp%2Fok" in url
    assert "cancel_url=https%3A%2F%2Fapp%2Fko" in url


def test_change_subscription_sends_timing_and_plan(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "abo-1-1"}))
    client.change_subscription("abo-1-1", "plan_soutien", timing="renewal")
    call = fake_httpx["calls"][0]
    assert call["method"] == "PUT"
    assert call["url"] == "https://api.test/v1/subscription/abo-1-1"
    assert call["json"] == {"timing": "renewal", "plan": "plan_soutien"}


def test_change_subscription_immediate_timing(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "abo-1-2"}))
    client.change_subscription("abo-1-2", "plan_simple", timing="immediate")
    assert fake_httpx["calls"][0]["json"]["timing"] == "immediate"
