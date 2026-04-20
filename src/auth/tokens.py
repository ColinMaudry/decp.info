import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from src.auth import db

VERIFICATION_TTL_HOURS = 24
RESET_TTL_HOURS = 1


def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _expires_at(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def create_verification_token(
    user_id: int, expires_in_hours: int = VERIFICATION_TTL_HOURS
) -> str:
    plain = secrets.token_urlsafe(32)
    db.create_email_verification_token(
        hash_token(plain), user_id, _expires_at(expires_in_hours)
    )
    return plain


def consume_verification_token(plain: str) -> int | None:
    row = db.find_email_verification_token(hash_token(plain))
    if row is None:
        return None
    user_id = row["user_id"]
    db.delete_email_verification_tokens_for_user(user_id)
    return user_id


def create_password_reset_token(
    user_id: int, expires_in_hours: int = RESET_TTL_HOURS
) -> str:
    db.delete_password_reset_tokens_for_user(user_id)
    plain = secrets.token_urlsafe(32)
    db.create_password_reset_token(
        hash_token(plain), user_id, _expires_at(expires_in_hours)
    )
    return plain


def consume_password_reset_token(plain: str) -> int | None:
    row = db.find_password_reset_token(hash_token(plain))
    if row is None:
        return None
    user_id = row["user_id"]
    db.delete_password_reset_tokens_for_user(user_id)
    return user_id


def validate_password_reset_token(plain: str) -> int | None:
    """Check token without consuming (used to render the reset form)."""
    row = db.find_password_reset_token(hash_token(plain))
    return row["user_id"] if row else None
