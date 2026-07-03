from flask import Blueprint, abort, redirect, request
from flask_login import current_user

from src.admin.db import log_action
from src.admin.guard import is_admin
from src.subscriptions.db import SUBSCRIPTION_STATUSES, get_current, set_status

admin_bp = Blueprint("admin", __name__, url_prefix="/admin/actions")


@admin_bp.before_request
def _require_admin():
    if not is_admin():
        abort(404)


@admin_bp.route("/subscription-status", methods=["POST"])
def subscription_status():
    user_id = request.form.get("user_id", type=int)
    subscription_id = request.form.get("subscription_id", type=int)
    status = request.form.get("status", "")

    if user_id is None or subscription_id is None:
        abort(400)

    current = get_current(user_id)
    if (
        status not in SUBSCRIPTION_STATUSES
        or current is None
        or current["id"] != subscription_id
    ):
        return redirect(f"/admin/user/{user_id}?error=invalid_status")

    old_status = current["status"]
    set_status(subscription_id, status)
    log_action(
        current_user.email,
        "subscription_status_change",
        user_id,
        f"{old_status} → {status}",
    )
    return redirect(f"/admin/user/{user_id}?status_changed=1")
