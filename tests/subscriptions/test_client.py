import pytest

from src.subscriptions import client


def test_auth_and_base_url_used(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "decpinfo-1"}))
    client.get_or_create_customer("decpinfo-1", "a@b.fr")
    call = fake_httpx["calls"][0]
    assert call["url"] == "https://api.test/v1/customer/decpinfo-1"
    assert call["auth"] == ("priv_test", "")


def test_get_or_create_customer_existing(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "decpinfo-1"}))
    result = client.get_or_create_customer("decpinfo-1", "a@b.fr")
    assert result == {"handle": "decpinfo-1"}
    assert len(fake_httpx["calls"]) == 1  # pas de POST de création


def test_get_or_create_customer_creates_on_404(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](404, {"error": "not found"}))
    fake_httpx["queue"].append(fake_httpx["Response"](200, {"handle": "decpinfo-1"}))
    result = client.get_or_create_customer("decpinfo-1", "a@b.fr")
    assert result == {"handle": "decpinfo-1"}
    assert fake_httpx["calls"][1]["method"] == "POST"
    assert fake_httpx["calls"][1]["json"] == {"handle": "decpinfo-1", "email": "a@b.fr"}


def test_create_subscription_session_returns_url(fake_httpx):
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
        "plan_simple", "decpinfo-1", "https://app/ok", "https://app/ko"
    )
    assert url == "https://checkout.reepay.com/#/sub-1"
    body = fake_httpx["calls"][0]["json"]
    assert body["plan"] == "plan_simple"
    assert body["customer"] == "decpinfo-1"
    assert body["signup_method"] == "link"
    assert "prepare_subscription" not in body
    assert "accept_url" not in body


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
        "plan_simple", "decpinfo-1", "https://app/ok", "https://app/ko", no_trial=True
    )
    assert fake_httpx["calls"][0]["json"]["no_trial"] is True


def test_http_error_raises_frisbii_error(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](500, {"error": "boom"}))
    with pytest.raises(client.FrisbiiError) as exc:
        client.get_plan("plan_simple")
    assert exc.value.status_code == 500
