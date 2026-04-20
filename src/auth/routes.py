from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, redirect, request
from werkzeug.security import generate_password_hash

from src.auth import db, mailer, tokens
from src.utils import logger

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

MIN_PASSWORD_LENGTH = 8


def _redirect_with_error(path: str, error: str, email: str | None = None):
    url = f"{path}?error={error}"
    if email:
        url += f"&email={email}"
    return redirect(url)


@auth_bp.route("/signup", methods=["POST"])
def signup():
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    password_confirm = request.form.get("password_confirm") or ""

    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.normalized.lower()
    except EmailNotValidError:
        return _redirect_with_error("/inscription", "invalid_email", email)

    if len(password) < MIN_PASSWORD_LENGTH:
        return _redirect_with_error("/inscription", "password_too_short", email)
    if password != password_confirm:
        return _redirect_with_error("/inscription", "password_mismatch", email)

    if db.get_user_by_email(email) is not None:
        return _redirect_with_error("/inscription", "email_taken", email)

    user_id = db.create_user(email, generate_password_hash(password))
    token = tokens.create_verification_token(user_id)
    try:
        mailer.send_verification_email(email, token)
    except Exception:
        logger.exception("Échec d'envoi de l'email de vérification")
        db.delete_user(user_id)
        return _redirect_with_error("/inscription", "email_send_failed", email)

    return redirect("/connexion?pending_verification=1")


@auth_bp.route("/verify-email", methods=["GET"])
def verify_email():
    token = request.args.get("token") or ""
    if not token:
        return redirect("/verification-email?error=invalid_token")
    user_id = tokens.consume_verification_token(token)
    if user_id is None:
        return redirect("/verification-email?error=invalid_token")
    db.set_email_verified(user_id)
    return redirect("/connexion?verified=1")
