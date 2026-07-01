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
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/#/sub-1"
                }
            },
        )
    )
    url = client.create_subscription_session(
        "plan_simple",
        "https://app/ok",
        "https://app/ko",
        customer_handle="colibre-1",
    )
    assert url == "https://checkout.reepay.com/#/sub-1"
    body = fake_httpx["calls"][0]["json"]
    assert body["plan"] == "plan_simple"
    assert body["customer"] == "colibre-1"
    assert body["signup_method"] == "link"
    assert "prepare_subscription" not in body


def test_create_subscription_session_no_trial(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](
            200,
            {
                "hosted_page_links": {
                    "payment_info": "https://checkout.reepay.com/#/sub-2"
                }
            },
        )
    )
    client.create_subscription_session(
        "plan_simple",
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
