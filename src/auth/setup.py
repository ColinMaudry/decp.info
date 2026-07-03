import os

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from src.auth import db, mailer
from src.auth.models import load_user
from src.auth.oauth import init_oauth
from src.utils import DEVELOPMENT, logger

_csrf: CSRFProtect | None = None
_login_manager: LoginManager | None = None


def safe_next(url: str | None, fallback: str = "/") -> str:
    if not url or not url.startswith("/") or url.startswith("//"):
        return fallback
    return url


def init_auth(app: Flask) -> None:
    global _csrf, _login_manager

    secret = os.getenv("SECRET_KEY") or app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "SECRET_KEY est obligatoire pour l'authentification. "
            "Définissez-la dans .env (voir .template.env)."
        )
    app.config["SECRET_KEY"] = secret
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = not DEVELOPMENT
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 jours

    db.init_schema()
    db.purge_expired_tokens()

    mailer.init_mailer()

    _login_manager = LoginManager()
    _login_manager.login_view = "/connexion"
    _login_manager.user_loader(load_user)
    _login_manager.init_app(app)

    from src.auth.routes import auth_bp

    app.register_blueprint(auth_bp)

    from src.admin.routes import admin_bp

    app.register_blueprint(admin_bp)

    init_oauth(app)

    _csrf = CSRFProtect(app)

    if not os.getenv("BREVO_API_KEY"):
        logger.warning(
            "BREVO_API_KEY non défini : les emails d'auth échoueront. "
            "Définissez les variables BREVO_* dans .env pour envoyer des emails."
        )

    if not os.getenv("LINKEDIN_CLIENT_ID"):
        logger.warning(
            "LINKEDIN_CLIENT_ID non défini : la connexion LinkedIn échouera. "
            "Définissez LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET dans .env."
        )

    if not os.getenv("APP_BASE_URL"):
        logger.warning(
            "APP_BASE_URL non défini : le callback LinkedIn produira une URI relative invalide."
        )
