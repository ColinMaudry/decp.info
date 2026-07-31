"""Le paramètre `compte_cree` déclenche l'événement `account_created` côté
navigateur (src/assets/goals.js). Il n'est posé qu'en cas de succès complet
de l'inscription — voir le commentaire dans `signup()` (src/auth/routes.py)."""

from werkzeug.security import generate_password_hash

from src.auth import db, mailer


def _signup(client, email="nouveau@example.com", password="password12"):
    return client.post(
        "/auth/signup",
        data={
            "email": email,
            "password": password,
            "password_confirm": password,
        },
    )


def test_redirection_porte_le_discriminant(client, mail_outbox):
    reponse = _signup(client)

    assert reponse.status_code == 302
    assert "pending_verification=1" in reponse.headers["Location"]
    assert "compte_cree=email" in reponse.headers["Location"]


def test_pas_de_discriminant_si_l_envoi_du_mail_echoue(client, monkeypatch):
    """routes.py:86 supprime le compte : il ne doit pas être comptabilisé."""

    def envoi_casse(email, token):
        raise RuntimeError("SMTP indisponible")

    monkeypatch.setattr(mailer, "send_verification_email", envoi_casse)

    reponse = _signup(client, email="perdu@example.com")

    assert reponse.status_code == 302
    assert "error=email_send_failed" in reponse.headers["Location"]
    assert "compte_cree" not in reponse.headers["Location"]
    assert db.get_user_by_email("perdu@example.com") is None


def test_pas_de_discriminant_si_email_deja_pris(client, mail_outbox):
    db.create_user("pris@example.com", generate_password_hash("password12"))

    reponse = _signup(client, email="pris@example.com")

    assert reponse.status_code == 302
    assert "error=email_taken" in reponse.headers["Location"]
    assert "compte_cree" not in reponse.headers["Location"]
    assert len(mail_outbox) == 0
