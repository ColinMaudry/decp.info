import os

import pytest

from src.auth import mailer

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("BREVO_API_KEY"),
    reason="BREVO_API_KEY absent — test d'intégration Brevo ignoré",
)
def test_send_verification_email_sandbox(monkeypatch):
    # Force le mode sandbox : Brevo valide la requête sans délivrer.
    monkeypatch.setenv("BREVO_SANDBOX", "true")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    mailer.init_mailer()
    # Ne doit pas lever : l'API Brevo accepte la requête en sandbox.
    mailer.send_verification_email(
        os.getenv("MAIL_FROM", "noreply@decp.info"), "INTEGRATION_TOKEN"
    )
