import os

from flask import Blueprint, redirect, request
from flask_login import current_user, login_required

from src.auth import db as auth_db
from src.subscriptions import client, db, handles, plans, webhooks
from src.utils import logger

subscriptions_bp = Blueprint("subscriptions", __name__)


@subscriptions_bp.route("/subscriptions/subscribe", methods=["POST"])
@login_required
def subscribe():
    plan_key = request.form.get("plan") or ""
    plan_handle = plans.resolve_handle(plan_key)
    if plan_handle is None:
        return "Plan inconnu", 400

    base = os.getenv("APP_BASE_URL", "")
    if db.has_active_subscription(current_user.id):
        return redirect(f"{base}/compte/abonnement")

    cust = handles.customer_handle(current_user.id)
    meta = plans.plan_meta(plan_key)
    sub_handle, subscription_id = db.create_pending(
        current_user.id, cust, plan_key, meta["prix_ht"] if meta else None
    )
    try:
        # L'essai n'existe plus côté Frisbii : il est tenu par colibre
        # (subscriber_state.trial_ends_at) et se termine sans débit. Toute
        # souscription est donc immédiatement payante.
        accept_url = f"{base}/compte/abonnement?paiement=succes"
        cancel_url = f"{base}/compte/abonnement?paiement=annule"
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
                plan_handle,
                sub_handle,
                accept_url,
                cancel_url,
                customer_handle=cust,
                no_trial=True,
            )
        else:
            create_customer = {"handle": cust, **billing}
            if siret:
                create_customer["metadata"] = {"siret": siret}
            url = client.create_subscription_session(
                plan_handle,
                sub_handle,
                accept_url,
                cancel_url,
                create_customer=create_customer,
                no_trial=True,
            )
    except client.FrisbiiError:
        logger.exception("Échec de création de session d'abonnement Frisbii")
        db.mark_failed(subscription_id)
        return redirect("/compte/abonnement?error=frisbii")
    return redirect(url, code=303)


# Les routes /subscriptions/add-payment et son callback vivaient ici. Elles
# attachaient un moyen de paiement à un abonnement déjà créé chez Frisbii : ce
# cas n'existe plus depuis que la souscription à un abonnement passe par
# `prepare_subscription` (src/subscriptions/client.py), qui ne crée l'abonnement
# qu'une fois le paiement accepté. Une ligne `pending` ne désigne donc plus
# aucun abonnement Frisbii, et le bloc de reprise renvoie vers le parcours
# normal (/compte/abonnement/mes-infos).


@subscriptions_bp.route("/subscriptions/change-payment-method", methods=["POST"])
@login_required
def change_payment_method():
    base = os.getenv("APP_BASE_URL", "")
    row = db.get_current(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement actif", 400
    try:
        url = client.get_payment_info_url(
            row["frisbii_subscription_handle"],
            f"{base}/compte/abonnement?carte=succes",
            f"{base}/compte/abonnement?carte=annule",
        )
    except client.FrisbiiError:
        logger.exception("Échec de récupération du lien de paiement Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    return redirect(url, code=303)


@subscriptions_bp.route("/subscriptions/update", methods=["POST"])
@login_required
def update():
    new_plan_key = request.form.get("plan") or ""
    new_handle = plans.resolve_handle(new_plan_key)
    if new_handle is None:
        return "Plan inconnu", 400

    row = db.get_current(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement à mettre à jour", 400

    cust = handles.customer_handle(current_user.id)
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

    try:
        if siret:
            auth_db.set_siret(current_user.id, siret)
        client.update_customer(cust, billing)
        if new_handle != plans.resolve_handle(row["plan"]):
            timing = "immediate" if row["status"] == "pending" else "renewal"
            client.change_subscription(
                row["frisbii_subscription_handle"], new_handle, timing
            )
    except client.FrisbiiError:
        logger.exception("Échec de mise à jour de l'abonnement Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    return redirect("/compte/abonnement?maj=succes", code=303)


@subscriptions_bp.route("/subscriptions/cancel", methods=["POST"])
@login_required
def cancel():
    row = db.get_current(current_user.id)
    if row is None or not row["frisbii_subscription_handle"]:
        return "Aucun abonnement à résilier", 400
    try:
        sub = client.cancel_subscription(row["frisbii_subscription_handle"])
    except client.FrisbiiError:
        logger.exception("Échec de résiliation Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    db.set_cancelled(row["id"], sub.get("expires"))
    return redirect("/compte/abonnement?resiliation=ok")


@subscriptions_bp.route("/subscriptions/reactivate", methods=["POST"])
@login_required
def reactivate():
    row = db.get_current(current_user.id)
    if (
        row is None
        or row["status"] != "cancelled"
        or not row["frisbii_subscription_handle"]
        or not db.period_end_in_future(row["current_period_end"])
    ):
        return "Aucun abonnement résilié à réactiver", 400
    try:
        sub = client.uncancel_subscription(row["frisbii_subscription_handle"])
    except client.FrisbiiError:
        logger.exception("Échec de réactivation Frisbii")
        return redirect("/compte/abonnement?error=frisbii")
    db.set_reactivated(row["id"], sub.get("next_period_start"))
    return redirect("/compte/abonnement?reactivation=ok")


@subscriptions_bp.route("/frisbii/webhook", methods=["POST"])
def webhook():
    payload = request.get_json(silent=True) or {}
    if not webhooks.verify_signature(payload, os.getenv("FRISBII_WEBHOOK_SECRET", "")):
        logger.warning(
            "Webhook Frisbii : signature invalide (event %s)", payload.get("id")
        )
        return "", 403

    customer = payload.get("customer")
    sub_handle = payload.get("subscription")
    if not customer or not db.customer_known(customer):
        return "", 200  # rien à rapprocher
    try:
        sub = client.get_subscription(sub_handle) if sub_handle else None
    except client.FrisbiiError:
        logger.exception("Webhook : lecture de l'abonnement Frisbii impossible")
        return "", 502  # Frisbii réessaiera
    if sub is None:
        return "", 200
    status, current_period_end = webhooks.map_subscription(sub)
    db.update_from_webhook(sub_handle, status, current_period_end)
    return "", 200
