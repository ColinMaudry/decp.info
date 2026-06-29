import os

from flask import Blueprint, redirect, request
from flask_login import current_user, login_required

from src.auth import db as auth_db
from src.subscriptions import client, db, plans, webhooks
from src.utils import logger

subscriptions_bp = Blueprint("subscriptions", __name__)


def _customer_handle(user_id: int) -> str:
    return f"decpinfo-{user_id}"


@subscriptions_bp.route("/subscriptions/subscribe", methods=["POST"])
@login_required
def subscribe():
    plan_key = request.form.get("plan") or ""
    handle = plans.resolve_handle(plan_key)
    if handle is None:
        return "Plan inconnu", 400

    base = os.getenv("APP_BASE_URL", "")
    if db.has_active_subscription(current_user.id):
        return redirect(f"{base}/compte/abonnement")

    cust = _customer_handle(current_user.id)
    try:
        meta = plans.plan_meta(plan_key)
        db.create_pending(
            current_user.id, cust, plan_key, meta["prix_ht"] if meta else None
        )
        no_trial = db.has_used_trial(current_user.id)
        siret = (request.form.get("siret") or "").strip()
        billing: dict = {
            "email": current_user.email,
            "first_name": request.form.get("first_name", ""),
            "last_name": request.form.get("last_name", ""),
            "address": request.form.get("address", ""),
            "city": request.form.get("city", ""),
            "postal_code": request.form.get("postal_code", ""),
            "country": request.form.get("country", "FR"),
        }
        if request.form.get("address2"):
            billing["address2"] = request.form["address2"]
        if request.form.get("company"):
            billing["company"] = request.form["company"]

        if siret:
            auth_db.set_siret(current_user.id, siret)

        customer_exists = True
        try:
            client.update_customer(cust, billing)
        except client.FrisbiiError as exc:
            if exc.status_code != 404:
                raise
            customer_exists = False

        if customer_exists:
            url = client.create_subscription_session(
                handle,
                f"{base}/compte/abonnement?paiement=succes",
                f"{base}/compte/abonnement?paiement=annule",
                customer_handle=cust,
                no_trial=no_trial,
            )
        else:
            create_customer = {"handle": cust, **billing}
            if siret:
                create_customer["metadata"] = {"siret": siret}
            url = client.create_subscription_session(
                handle,
                f"{base}/compte/abonnement?paiement=succes",
                f"{base}/compte/abonnement?paiement=annule",
                create_customer=create_customer,
                no_trial=no_trial,
            )
    except client.FrisbiiError:
        logger.exception("Échec de création de session d'abonnement Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    return redirect(url, code=303)


@subscriptions_bp.route("/subscriptions/cancel", methods=["POST"])
@login_required
def cancel():
    row = db.get_by_user(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement à résilier", 400
    try:
        sub = client.cancel_subscription(row["frisbii_subscription_handle"])
    except client.FrisbiiError:
        logger.exception("Échec de résiliation Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    db.set_cancelled(current_user.id, sub.get("expires"))
    return redirect("/compte/abonnement?resiliation=ok")


@subscriptions_bp.route("/frisbii/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    if not webhooks.verify_signature(payload, os.getenv("FRISBII_WEBHOOK_SECRET", "")):
        return "", 403

    customer = payload.get("customer")
    sub_handle = payload.get("subscription")
    if not customer or db.get_by_customer(customer) is None:
        return "", 200  # rien à rapprocher
    try:
        sub = client.get_subscription(sub_handle) if sub_handle else None
    except client.FrisbiiError:
        logger.exception("Webhook : lecture de l'abonnement Frisbii impossible")
        return "", 502  # Frisbii réessaiera
    if sub is None:
        return "", 200
    status, current_period_end = webhooks.map_subscription(sub)
    db.update_from_webhook(customer, sub_handle, status, current_period_end)
    return "", 200
