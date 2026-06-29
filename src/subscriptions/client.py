import os

import httpx

# NB : base URL et schémas d'endpoints à confirmer dans la doc Frisbii lors de la
# première intégration en environnement de test. Frisbii Billing/Pay s'appuie sur
# l'API Reepay (api.reepay.com) ; ajuster FRISBII_API_BASE_URL si besoin.
_DEFAULT_BASE_URL = "https://api.frisbii.com"
_TIMEOUT = 15.0


class FrisbiiError(Exception):
    def __init__(self, status_code: int, body):
        super().__init__(f"Frisbii API error {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def _api_key() -> str:
    return os.getenv("FRISBII_API_KEY", "")


def _base_url() -> str:
    return os.getenv("FRISBII_API_BASE_URL") or _DEFAULT_BASE_URL


def _call(method: str, path: str, json: dict | None = None) -> dict:
    try:
        resp = httpx.request(
            method,
            f"{_base_url()}{path}",
            auth=(_api_key(), ""),
            json=json,
            timeout=_TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise FrisbiiError(0, str(exc)) from exc
    if resp.status_code >= 400:
        print(resp.text)
        raise FrisbiiError(resp.status_code, resp.text)
    return resp.json()


def get_customer(handle: str) -> dict:
    return _call("GET", f"/v1/customer/{handle}")


def update_customer(handle: str, data: dict) -> dict:
    return _call("PUT", f"/v1/customer/{handle}", json=data)


def create_subscription_session(
    plan_handle: str,
    accept_url: str,
    cancel_url: str,
    no_trial: bool = False,
    customer_handle: str | None = None,
    create_customer: dict | None = None,
) -> str:
    body: dict = {
        "plan": plan_handle,
        "signup_method": "link",
        "generate_handle": True,
        "accept_url": accept_url,
        "cancel_url": cancel_url,
    }
    if customer_handle:
        body["customer"] = customer_handle
    elif create_customer:
        body["create_customer"] = create_customer
    if no_trial:
        body["no_trial"] = True
    data = _call("POST", "/v1/subscription", json=body)
    return data["hosted_page_links"]["payment_info"]


def cancel_subscription(subscription_handle: str) -> dict:
    return _call("POST", f"/v1/subscription/{subscription_handle}/cancel")


def get_subscription(subscription_handle: str) -> dict:
    return _call("GET", f"/v1/subscription/{subscription_handle}")


def get_plan(plan_handle: str) -> dict:
    return _call("GET", f"/v1/plan/{plan_handle}")
