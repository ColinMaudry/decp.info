import os

from brevo import (
    Brevo,
    SendTransacEmailRequestSender,
    SendTransacEmailRequestToItem,
)
from brevo.core.api_error import ApiError

from src.utils import DEVELOPMENT, logger

_client: Brevo | None = None


def init_mailer() -> None:
    """Construit le client Brevo à partir des variables d'environnement."""
    global _client
    api_key = os.getenv("BREVO_API_KEY", "")
    _client = Brevo(api_key=api_key)


def _base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8050").rstrip("/")


def _sender() -> SendTransacEmailRequestSender:
    return SendTransacEmailRequestSender(
        email=os.getenv("MAIL_FROM", "noreply@colibre"),
        name=os.getenv("MAIL_FROM_NAME", "colibre"),
    )


def _template_id(env_var: str) -> int:
    raw = os.getenv(env_var, "")
    if not raw:
        raise RuntimeError(f"{env_var} non défini (template Brevo)")
    return int(raw)


def _send_template(template_id: int, recipient: str, params: dict) -> None:
    assert _client is not None, "Mailer non initialisé (init_mailer() non appelé)"
    sandbox_headers = {"X-Sib-Sandbox": "drop"} if DEVELOPMENT else None
    try:
        _client.transactional_emails.send_transac_email(
            template_id=template_id,
            params=params,
            sender=_sender(),
            to=[SendTransacEmailRequestToItem(email=recipient)],
            headers=sandbox_headers,
        )
    except ApiError:
        logger.exception(
            "Échec d'envoi Brevo (template %s) à %s", template_id, recipient
        )
        raise


def send_verification_email(email: str, token: str) -> None:
    link = f"{_base_url()}/auth/verify-email?token={token}"
    _send_template(_template_id("BREVO_TEMPLATE_VERIFY_ID"), email, {"link": link})


def send_reset_email(email: str, token: str) -> None:
    link = f"{_base_url()}/reinitialiser-mot-de-passe?token={token}"
    _send_template(_template_id("BREVO_TEMPLATE_RESET_ID"), email, {"link": link})


def send_email_change_email(email: str, token: str) -> None:
    link = f"{_base_url()}/auth/confirm-email-change?token={token}"
    _send_template(_template_id("BREVO_TEMPLATE_VERIFY_ID"), email, {"link": link})
