from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, redirect, request
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from src.auth import db, mailer, tokens
from src.auth.models import User
from src.auth.setup import safe_next
from src.utils import logger

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

MIN_PASSWORD_LENGTH = 8

# Hash bidon pré-calculé pour uniformiser le timing login
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


def resolve_oauth_user(
    provider: str, subject: str, email: str, email_verified: bool
) -> User:
    identity = db.get_oauth_identity(provider, subject)
    if identity is not None:
        return User(db.get_user_by_id(identity["user_id"]))

    row = db.get_user_by_email(email)
    if row is not None:
        db.link_oauth_identity(provider, subject, row["id"])
        if email_verified and not row["email_verified"]:
            db.set_email_verified(row["id"])
        return User(db.get_user_by_id(row["id"]))

    user_id = db.create_oauth_user(email)
    db.link_oauth_identity(provider, subject, user_id)
    return User(db.get_user_by_id(user_id))


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


@auth_bp.route("/login", methods=["POST"])
def login():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    next_url = safe_next(request.form.get("next"), fallback="/compte/admin")

    row = db.get_user_by_email(email)
    if row is None:
        check_password_hash(_DUMMY_HASH, password)  # uniformiser le temps
        return _redirect_with_error("/connexion", "invalid_credentials", email)

    if not check_password_hash(row["password_hash"], password):
        return _redirect_with_error("/connexion", "invalid_credentials", email)

    if not row["email_verified"]:
        return _redirect_with_error("/connexion", "email_not_verified", email)

    login_user(User(row), remember=True)
    return redirect(next_url)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    return redirect("/")


@auth_bp.route("/request-password-reset", methods=["POST"])
def request_password_reset():
    email = (request.form.get("email") or "").strip().lower()
    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.normalized.lower()
    except EmailNotValidError:
        return redirect("/mot-de-passe-oublie?pending=1")

    row = db.get_user_by_email(email)
    if row is None:
        return redirect("/mot-de-passe-oublie?pending=1")

    token = tokens.create_password_reset_token(row["id"])
    try:
        mailer.send_reset_email(email, token)
    except Exception:
        logger.exception("Échec d'envoi de l'email de réinitialisation")
        return _redirect_with_error("/mot-de-passe-oublie", "email_send_failed", email)
    return redirect("/mot-de-passe-oublie?pending=1")


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    token = request.form.get("token") or ""
    password = request.form.get("password") or ""
    password_confirm = request.form.get("password_confirm") or ""

    user_id = tokens.validate_password_reset_token(token)
    if user_id is None:
        return redirect(
            f"/reinitialiser-mot-de-passe?token={token}&error=invalid_token"
        )

    if len(password) < MIN_PASSWORD_LENGTH:
        return redirect(
            f"/reinitialiser-mot-de-passe?token={token}&error=password_too_short"
        )
    if password != password_confirm:
        return redirect(
            f"/reinitialiser-mot-de-passe?token={token}&error=password_mismatch"
        )

    consumed = tokens.consume_password_reset_token(token)
    if consumed is None:
        return redirect(
            f"/reinitialiser-mot-de-passe?token={token}&error=invalid_token"
        )

    db.update_password_hash(consumed, generate_password_hash(password))
    return redirect("/connexion?password_changed=1")


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_pw = request.form.get("current_password") or ""
    password = request.form.get("password") or ""
    password_confirm = request.form.get("password_confirm") or ""

    row = db.get_user_by_id(current_user.id)
    if not check_password_hash(row["password_hash"], current_pw):
        return _redirect_with_error("/compte/admin", "invalid_current_password")

    if len(password) < MIN_PASSWORD_LENGTH:
        return _redirect_with_error("/compte/admin", "password_too_short")
    if password != password_confirm:
        return _redirect_with_error("/compte/admin", "password_mismatch")

    db.update_password_hash(current_user.id, generate_password_hash(password))
    return redirect("/compte/admin?password_changed=1")


@auth_bp.route("/change-email", methods=["POST"])
@login_required
def change_email():
    email = (request.form.get("email") or "").strip()
    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.normalized.lower()
    except EmailNotValidError:
        return _redirect_with_error("/compte/admin", "invalid_email")

    if db.get_user_by_email(email) is not None:
        return _redirect_with_error("/compte/admin", "email_taken")

    db.set_pending_email(current_user.id, email)
    db.delete_email_verification_tokens_for_user(current_user.id)
    token = tokens.create_verification_token(current_user.id)
    try:
        mailer.send_email_change_email(email, token)
    except Exception:
        logger.exception("Échec d'envoi de l'email de changement d'adresse")
        return _redirect_with_error("/compte/admin", "email_send_failed")

    return redirect("/compte/admin?email_pending=1")


@auth_bp.route("/confirm-email-change", methods=["GET"])
def confirm_email_change():
    token = request.args.get("token") or ""
    user_id = tokens.consume_verification_token(token)
    if user_id is None:
        return redirect("/compte/admin?error=invalid_token")
    new_email = db.promote_pending_email(user_id)
    if new_email is None:
        return redirect("/compte/admin?error=invalid_token")
    return redirect("/compte/admin?email_changed=1")


@auth_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    current_pw = request.form.get("current_password") or ""
    row = db.get_user_by_id(current_user.id)
    if not check_password_hash(row["password_hash"], current_pw):
        return _redirect_with_error("/compte/admin", "invalid_current_password")

    user_id = current_user.id
    db.delete_email_verification_tokens_for_user(user_id)
    db.delete_password_reset_tokens_for_user(user_id)
    db.delete_user(user_id)
    logout_user()
    return redirect("/?account_deleted=1")
