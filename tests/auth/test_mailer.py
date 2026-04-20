import pytest
from flask import Flask
from flask_mail import Mail

from src.auth import mailer


@pytest.fixture
def mail_app(monkeypatch, tmp_path):
    app = Flask(
        __name__,
        template_folder=str(
            (__import__("pathlib").Path(mailer.__file__).parent / "templates").resolve()
        ),
    )
    app.config["MAIL_SUPPRESS_SEND"] = True
    app.config["MAIL_DEFAULT_SENDER"] = "noreply@decp.info"
    app.config["TESTING"] = True
    mail = Mail(app)
    monkeypatch.setattr(mailer, "_mail", mail)
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    return app


def test_send_verification_email(mail_app):
    with mail_app.app_context(), mail_app.test_request_context():
        with mail_app.extensions["mail"].record_messages() as outbox:
            mailer.send_verification_email("a@b.c", "TOKEN123")
    assert len(outbox) == 1
    msg = outbox[0]
    assert msg.recipients == ["a@b.c"]
    assert "verification-email?token=TOKEN123" in msg.body
    assert "verification-email?token=TOKEN123" in msg.html


def test_send_reset_email(mail_app):
    with mail_app.app_context(), mail_app.test_request_context():
        with mail_app.extensions["mail"].record_messages() as outbox:
            mailer.send_reset_email("a@b.c", "RESET456")
    assert len(outbox) == 1
    msg = outbox[0]
    assert "reinitialiser-mot-de-passe?token=RESET456" in msg.body
