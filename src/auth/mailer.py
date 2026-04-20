import os
from pathlib import Path

from flask import Flask, render_template
from flask_mail import Mail, Message

TEMPLATES_DIR = Path(__file__).parent / "templates"

_mail: Mail | None = None


def init_mailer(app: Flask) -> None:
    global _mail
    app.config["MAIL_SERVER"] = os.getenv("SMTP_HOST", "")
    app.config["MAIL_PORT"] = int(os.getenv("SMTP_PORT", "587"))
    app.config["MAIL_USERNAME"] = os.getenv("SMTP_USERNAME") or None
    app.config["MAIL_PASSWORD"] = os.getenv("SMTP_PASSWORD") or None
    app.config["MAIL_USE_TLS"] = os.getenv("SMTP_USE_TLS", "True").lower() == "true"
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_FROM", "noreply@decp.info")
    app.config["MAIL_SUPPRESS_SEND"] = (
        os.getenv("DEVELOPMENT", "False").lower() == "true"
    )
    # Inclure les templates du package auth dans la recherche Jinja
    if hasattr(app.jinja_loader, "searchpath"):
        app.jinja_loader.searchpath.append(str(TEMPLATES_DIR))
    else:
        import jinja2

        app.jinja_loader = jinja2.ChoiceLoader(
            [app.jinja_loader, jinja2.FileSystemLoader(str(TEMPLATES_DIR))]
        )
    _mail = Mail(app)


def _base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8050").rstrip("/")


def _send(
    subject: str,
    recipient: str,
    txt_template: str,
    html_template: str,
    **ctx,
) -> None:
    assert _mail is not None, "Mailer non initialisé (init_mailer(app) non appelé)"
    msg = Message(subject=subject, recipients=[recipient])
    msg.body = render_template(txt_template, **ctx)
    msg.html = render_template(html_template, **ctx)
    _mail.send(msg)


def send_verification_email(email: str, token: str) -> None:
    link = f"{_base_url()}/verification-email?token={token}"
    _send(
        "Vérification de votre adresse email — decp.info",
        email,
        "emails/verify_email.txt",
        "emails/verify_email.html",
        link=link,
    )


def send_reset_email(email: str, token: str) -> None:
    link = f"{_base_url()}/reinitialiser-mot-de-passe?token={token}"
    _send(
        "Réinitialisation de votre mot de passe — decp.info",
        email,
        "emails/reset_password.txt",
        "emails/reset_password.html",
        link=link,
    )
