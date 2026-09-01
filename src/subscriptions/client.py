import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

# NB : base URL et schémas d'endpoints à confirmer dans la doc Frisbii lors de la
# première intégration en environnement de test. Frisbii Billing/Pay s'appuie sur
# l'API Reepay (api.reepay.com) ; ajuster FRISBII_API_BASE_URL si besoin.
_DEFAULT_BASE_URL = "https://api.frisbii.com"
_DEFAULT_CHECKOUT_URL = "https://checkout-api.frisbii.com"
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


def _checkout_url() -> str:
    return os.getenv("FRISBII_CHECKOUT_URL") or _DEFAULT_CHECKOUT_URL


def _call(
    method: str,
    path: str,
    json: dict | None = None,
    base_url: str | None = None,
    params: dict | None = None,
) -> dict:
    try:
        resp = httpx.request(
            method,
            f"{base_url or _base_url()}{path}",
            auth=(_api_key(), ""),
            json=json,
            params=params,
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
    handle: str,
    accept_url: str,
    cancel_url: str,
    *,
    no_trial: bool,
    customer_handle: str | None = None,
    create_customer: dict | None = None,
) -> str:
    # `prepare_subscription` plutôt qu'un POST /v1/subscription suivi d'une
    # session sur le handle : l'abonnement n'est alors créé qu'une fois le
    # paiement accepté (scénario « prepared → activated » de l'API, cf. le
    # champ `activated` de l'objet Subscription).
    #
    # Le créer d'abord était la cause de l'accès sans paiement : avec
    # `signup_method: "link"`, Frisbii renvoie immédiatement l'abonnement en
    # `state: "active"` sans aucun moyen de paiement, et un checkout abandonné
    # laissait donc un abonnement actif derrière lui.
    #
    # CreatePreparedSubscription ne connaît pas `signup_method` : c'est la
    # session de checkout qui collecte le moyen de paiement.
    prepared: dict = {
        "plan": plan_handle,
        "handle": handle,
    }
    if customer_handle:
        prepared["customer"] = customer_handle
    elif create_customer:
        prepared["create_customer"] = create_customer
    if no_trial:
        prepared["no_trial"] = True
    data = _call(
        "POST",
        "/v1/session/subscription",
        json={
            "prepare_subscription": prepared,
            "accept_url": accept_url,
            "cancel_url": cancel_url,
        },
        base_url=_checkout_url(),
    )
    return data["url"]


# create_recurring_session, get_customer_payment_methods et
# set_subscription_payment_method vivaient ici : elles ne servaient qu'à
# attacher un moyen de paiement à un abonnement déjà créé chez Frisbii, un cas
# disparu avec le passage à `prepare_subscription` ci-dessus. Changer de carte
# sur un abonnement actif passe par get_payment_info_url, pas par elles.


def cancel_subscription(subscription_handle: str) -> dict:
    return _call("POST", f"/v1/subscription/{subscription_handle}/cancel")


def uncancel_subscription(subscription_handle: str) -> dict:
    return _call("POST", f"/v1/subscription/{subscription_handle}/uncancel")


def get_subscription(subscription_handle: str) -> dict:
    return _call("GET", f"/v1/subscription/{subscription_handle}")


def get_payment_info_url(sub_handle: str, accept_url: str, cancel_url: str) -> str:
    sub = get_subscription(sub_handle)
    url = sub["hosted_page_links"]["payment_info"]
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["accept_url"] = accept_url
    query["cancel_url"] = cancel_url
    new_query = urlencode(query)
    # If URL has a fragment (hash-based routing), append params to fragment
    if parts.fragment:
        return f"{urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))}#{parts.fragment}?{new_query}"
    else:
        return urlunsplit(parts._replace(query=new_query))


def get_plan(plan_handle: str) -> dict:
    return _call("GET", f"/v1/plan/{plan_handle}")


def change_subscription(
    sub_handle: str, plan_handle: str, timing: str = "renewal"
) -> dict:
    return _call(
        "PUT",
        f"/v1/subscription/{sub_handle}",
        json={"timing": timing, "plan": plan_handle},
    )
