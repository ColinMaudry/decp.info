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
        fake_httpx["Response"](200, {"id": "cs_1", "url": "https://pay.test/cs_1"})
    )
    url = client.create_subscription_session(
        "plan_simple", "decpinfo-1", "https://app/ok", "https://app/ko"
    )
    assert url == "https://pay.test/cs_1"
    body = fake_httpx["calls"][0]["json"]
    assert body["prepare_subscription"] == {
        "plan": "plan_simple",
        "customer": "decpinfo-1",
    }
    assert body["accept_url"] == "https://app/ok"
    assert body["cancel_url"] == "https://app/ko"


def test_create_subscription_session_no_trial(fake_httpx):
    fake_httpx["queue"].append(
        fake_httpx["Response"](200, {"url": "https://pay.test/cs_2"})
    )
    client.create_subscription_session(
        "plan_simple", "decpinfo-1", "https://app/ok", "https://app/ko", no_trial=True
    )
    assert fake_httpx["calls"][0]["json"]["prepare_subscription"]["no_trial"] is True


def test_http_error_raises_frisbii_error(fake_httpx):
    fake_httpx["queue"].append(fake_httpx["Response"](500, {"error": "boom"}))
    with pytest.raises(client.FrisbiiError) as exc:
        client.get_plan("plan_simple")
    assert exc.value.status_code == 500
