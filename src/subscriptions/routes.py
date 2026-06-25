import os

from flask import Blueprint, redirect, request
from flask_login import current_user, login_required

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
        client.get_or_create_customer(cust, current_user.email)
        db.create_pending(
            current_user.id, cust, plan_key, meta["prix_ht"] if meta else None
        )
        # Anti-abus : pas de nouvel essai si l'utilisateur en a déjà consommé un.
        no_trial = db.has_used_trial(current_user.id)
        url = client.create_subscription_session(
            handle,
            cust,
            f"{base}/compte/abonnement?paiement=succes",
            f"{base}/compte/abonnement?paiement=annule",
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
