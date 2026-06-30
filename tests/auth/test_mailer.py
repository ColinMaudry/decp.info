import pytest

from src.auth import mailer


class _FakeTransac:
    def __init__(self):
        self.calls = []

    def send_transac_email(self, **kwargs):
        self.calls.append(kwargs)


class _FakeClient:
    def __init__(self):
        self.transactional_emails = _FakeTransac()


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(mailer, "_client", client)
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8050")
    monkeypatch.setenv("BREVO_TEMPLATE_VERIFY_ID", "11")
    monkeypatch.setenv("BREVO_TEMPLATE_RESET_ID", "22")
    monkeypatch.setenv("MAIL_FROM", "noreply@colibre")
    monkeypatch.setenv("MAIL_FROM_NAME", "colibre")
    return client


def test_send_verification_email(fake_client):
    mailer.send_verification_email("a@b.c", "TOKEN123")
    calls = fake_client.transactional_emails.calls
    assert len(calls) == 1
    call = calls[0]
    assert call["template_id"] == 11
    assert call["to"][0].email == "a@b.c"
    assert call["sender"].email == "noreply@colibre"
    assert "/auth/verify-email?token=TOKEN123" in call["params"]["link"]
    assert call["headers"] == {"X-Sib-Sandbox": "drop"}  # DEVELOPMENT=true en tests


def test_send_reset_email(fake_client):
    mailer.send_reset_email("a@b.c", "RESET456")
    calls = fake_client.transactional_emails.calls
    assert len(calls) == 1
    call = calls[0]
    assert call["template_id"] == 22
    assert "reinitialiser-mot-de-passe?token=RESET456" in call["params"]["link"]


def test_init_mailer_builds_client(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setattr(mailer, "_client", None)
    mailer.init_mailer()
    assert mailer._client is not None


def test_send_without_init_raises(monkeypatch):
    monkeypatch.setattr(mailer, "_client", None)
    monkeypatch.setenv("BREVO_TEMPLATE_VERIFY_ID", "11")
    with pytest.raises(AssertionError):
        mailer.send_verification_email("a@b.c", "TOKEN123")


def test_send_email_change_email(fake_client):
    mailer.send_email_change_email("new@example.fr", "tok123")

    calls = fake_client.transactional_emails.calls
    assert len(calls) == 1
    call = calls[0]
    assert call["template_id"] == 11
    assert call["to"][0].email == "new@example.fr"
    assert "/auth/confirm-email-change?token=tok123" in call["params"]["link"]
