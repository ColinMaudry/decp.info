import os

from flask import Flask

from src.subscriptions import db
from src.utils import logger

_REQUIRED_ENV = (
    "FRISBII_API_KEY",
    "FRISBII_WEBHOOK_SECRET",
    "FRISBII_PLAN_SIMPLE",
    "FRISBII_PLAN_SOUTIEN",
)


def init_subscriptions(app: Flask) -> None:
    db.init_schema()

    from src.subscriptions.routes import subscriptions_bp, webhook

    app.register_blueprint(subscriptions_bp)

    # Le webhook reçoit des POST externes : pas de jeton CSRF possible.
    from src.auth.setup import _csrf as _auth_csrf

    if _auth_csrf is not None:
        _auth_csrf.exempt(webhook)  # exempte la seule vue webhook

    missing = [name for name in _REQUIRED_ENV if not os.getenv(name)]
    if missing:
        logger.warning(
            "Variables Frisbii manquantes (%s) : les abonnements échoueront. "
            "Définissez-les dans .env (voir .template.env).",
            ", ".join(missing),
        )
