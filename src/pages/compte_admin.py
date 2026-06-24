import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, register_page
from flask_login import current_user

from src.pages._compte_shell import account_guard, account_shell

register_page(
    __name__,
    path="/compte/admin",
    title="Mon compte | decp.info",
    name="Mon compte",
    description="Gestion de votre compte decp.info.",
)

ERROR_MESSAGES = {
    "invalid_current_password": "Le mot de passe actuel est incorrect.",
    "password_too_short": "Le nouveau mot de passe doit faire au moins 8 caractères.",
    "password_mismatch": "Les nouveaux mots de passe ne correspondent pas.",
    "invalid_email": "L'adresse email n'est pas valide.",
    "email_taken": "Cette adresse email est déjà utilisée.",
    "email_send_failed": "L'envoi de l'email de confirmation a échoué.",
    "invalid_token": "Le lien de confirmation est invalide ou expiré.",
}

SUCCESS_MESSAGES = {
    "password_changed": "Mot de passe mis à jour.",
    "email_pending": "Un email de confirmation a été envoyé à la nouvelle adresse.",
    "email_changed": "Votre adresse email a été mise à jour.",
}


def _csrf(index: str):
    return dcc.Input(
        type="hidden",
        id={"type": "csrf-input", "index": index},
        name="csrf_token",
    )


def _email_section():
    return html.Div(
        [
            html.H4("Adresse email", className="mt-2"),
            html.P([html.Strong("Email actuel : "), current_user.email]),
            html.Form(
                method="POST",
                action="/auth/change-email",
                children=[
                    _csrf("change-email"),
                    dbc.Label("Nouvelle adresse email"),
                    dbc.Input(
                        type="email", name="email", required=True, className="mb-3"
                    ),
                    dbc.Button("Mettre à jour l'email", type="submit", color="primary"),
                ],
            ),
        ]
    )


def _password_section():
    return html.Div(
        [
            html.H4("Mot de passe", className="mt-4"),
            html.Form(
                method="POST",
                action="/auth/change-password",
                children=[
                    _csrf("change-password"),
                    dbc.Label("Mot de passe actuel"),
                    dbc.Input(
                        type="password",
                        name="current_password",
                        required=True,
                        className="mb-3",
                    ),
                    dbc.Label("Nouveau mot de passe (8 caractères minimum)"),
                    dbc.Input(
                        type="password",
                        name="password",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Label("Confirmer le nouveau mot de passe"),
                    dbc.Input(
                        type="password",
                        name="password_confirm",
                        required=True,
                        minLength=8,
                        className="mb-3",
                    ),
                    dbc.Button(
                        "Changer le mot de passe", type="submit", color="primary"
                    ),
                ],
            ),
        ]
    )


def _danger_section():
    return html.Div(
        [
            html.H4(
                "Zone danger",
                className="mt-3",
                style={"color": "#d9230f"},
            ),
            html.P("La suppression de votre compte est définitive."),
            dbc.Button(
                "Supprimer mon compte",
                id="delete-open",
                color="primary",
                outline=True,
            ),
            dbc.Modal(
                id="delete-modal",
                is_open=False,
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("Supprimer le compte")),
                    html.Form(
                        method="POST",
                        action="/auth/delete-account",
                        children=[
                            dbc.ModalBody(
                                [
                                    _csrf("delete-account"),
                                    html.P(
                                        "Cette action est définitive. "
                                        "Saisissez votre mot de passe pour confirmer."
                                    ),
                                    dbc.Input(
                                        type="password",
                                        name="current_password",
                                        required=True,
                                        placeholder="Mot de passe",
                                    ),
                                ]
                            ),
                            dbc.ModalFooter(
                                [
                                    dbc.Button(
                                        "Annuler", id="delete-cancel", color="secondary"
                                    ),
                                    dbc.Button(
                                        "Supprimer définitivement",
                                        type="submit",
                                        color="danger",
                                    ),
                                ]
                            ),
                        ],
                    ),
                ],
            ),
        ],
        className="rounded p-3 mt-4",
        style={"border": "1px solid #d9230f"},
    )


def _logout_section():
    return html.Form(
        method="POST",
        action="/auth/logout",
        className="mt-4",
        children=[
            _csrf("logout"),
            dbc.Button("Déconnexion", type="submit", color="secondary", outline=True),
        ],
    )


def layout(
    error=None, password_changed=None, email_pending=None, email_changed=None, **_
):
    guard = account_guard("/compte/admin", require_subscription=False)
    if guard is not None:
        return guard

    alerts = []
    if error in ERROR_MESSAGES:
        alerts.append(dbc.Alert(ERROR_MESSAGES[error], color="danger"))
    for flag, value in (
        ("password_changed", password_changed),
        ("email_pending", email_pending),
        ("email_changed", email_changed),
    ):
        if value == "1":
            alerts.append(dbc.Alert(SUCCESS_MESSAGES[flag], color="success"))

    contenu = html.Div(
        [
            html.H2("Compte"),
            *alerts,
            _email_section(),
            html.Hr(className="mt-4"),
            _password_section(),
            html.Hr(className="mt-4"),
            _danger_section(),
            _logout_section(),
        ]
    )
    return account_shell("admin", contenu)


@callback(
    Output("delete-modal", "is_open"),
    Input("delete-open", "n_clicks"),
    Input("delete-cancel", "n_clicks"),
    State("delete-modal", "is_open"),
    prevent_initial_call=True,
)
def _toggle_delete_modal(_open, _cancel, is_open):
    return not is_open
