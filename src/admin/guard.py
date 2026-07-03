import os

from flask_login import current_user


def is_admin() -> bool:
    admin_email = os.getenv("ADMIN_EMAIL")
    return bool(
        admin_email
        and current_user.is_authenticated
        and current_user.email.lower() == admin_email.lower()
    )
