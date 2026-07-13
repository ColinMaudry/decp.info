import os

import dash_bootstrap_components as dbc
from dash import dcc, html, register_page
from flask import session
from flask_login import current_user

from src.api import tokens_db
from src.pages._compte_shell import account_guard, account_shell

register_page(
    __name__,
    path="/compte/mcp",
    title="Connecteur MCP | colibre",
    name="Connecteur MCP",
    description="Connectez votre agent IA aux données colibre via le protocole MCP.",
)

MCP_ENABLED = os.getenv("DASH_MCP_ENABLED") == "true"
_TOKEN_PLACEHOLDER = "<VOTRE_JETON>"


def _mcp_url() -> str:
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    return f"{base}/_mcp" if base else "/_mcp"


def _csrf(index: str):
    return dcc.Input(
        type="hidden",
        id={"type": "csrf-input", "index": index},
        name="csrf_token",
    )


def client_instructions(url: str, token: str):
    """Construit les blocs d'instructions par client (fonction pure, testable)."""
    claude = f'claude mcp add colibre --scope user --transport http {url} --header "Authorization: Bearer {token}"'
    gemini = f'gemini mcp add --transport http --header "Authorization: Bearer {token}" colibre {url}'
    return dbc.Accordion(
        start_collapsed=True,
        always_open=False,
        children=[
            dbc.AccordionItem(
                title="Claude Code",
                children=html.Pre(html.Code(claude)),
            ),
            dbc.AccordionItem(
                title="Claude.ai / Claude Desktop / mobile",
                children=[
                    html.P("Aucun jeton à copier : ces applications utilisent OAuth."),
                    html.Ol(
                        [
                            html.Li(
                                "Paramètres → Connecteurs → Ajouter un connecteur personnalisé."
                            ),
                            html.Li(f"URL du serveur MCP : {url}"),
                            html.Li(
                                "Laissez le champ « Client Secret » vide (client public)."
                            ),
                            html.Li(
                                "Connectez-vous avec votre compte colibre, puis « Autoriser »."
                            ),
                        ]
                    ),
                ],
            ),
            dbc.AccordionItem(
                title="Gemini CLI",
                children=[
                    html.Pre(html.Code(gemini)),
                    html.P(
                        "Ou dans ~/.gemini/settings.json : un serveur mcpServers.colibre "
                        f'avec "httpUrl": "{url}" et "headers": '
                        f'{{"Authorization": "Bearer {token}"}}.'
                    ),
                ],
            ),
            dbc.AccordionItem(
                title="Mistral Le Chat",
                children=html.P(
                    "Dans les connecteurs MCP, ajoutez un serveur HTTP d'URL "
                    f"{url}, authentification « API Token », en-tête "
                    f"« Authorization » = « Bearer {token} »."
                ),
            ),
            dbc.AccordionItem(
                title="ChatGPT",
                children=[
                    html.P(
                        "ChatGPT utilise aussi OAuth (aucun jeton à copier). Dans les "
                        "connecteurs, ajoutez un connecteur par URL :"
                    ),
                    html.Ol(
                        [
                            html.Li(f"URL du serveur MCP : {url}"),
                            html.Li(
                                "Connectez-vous avec colibre, puis autorisez l'accès."
                            ),
                        ]
                    ),
                    html.P(
                        "La disponibilité des connecteurs dépend de votre plan ChatGPT.",
                        className="text-muted",
                    ),
                ],
            ),
        ],
    )


def _token_row(row: dict):
    statut = "Révoqué" if row["revoked_at"] else "Actif"
    actions = []
    if not row["revoked_at"]:
        actions = [
            html.Form(
                method="POST",
                action=f"/compte/mcp/revoquer/{row['id']}",
                children=[
                    _csrf(f"revoke-{row['id']}"),
                    dbc.Button(
                        "Révoquer",
                        type="submit",
                        color="danger",
                        size="sm",
                        outline=True,
                    ),
                ],
            )
        ]
    return html.Tr(
        [
            html.Td(row["label"]),
            html.Td(row["created_at"]),
            html.Td(row["last_used_at"] or "—"),
            html.Td(statut),
            html.Td(actions),
        ]
    )


def layout(**_):
    guard = account_guard("/compte/mcp", require_subscription=True)
    if guard is not None:
        return guard

    if not MCP_ENABLED:
        contenu = html.Div(
            [
                html.H2("Connecteur MCP"),
                dbc.Alert(
                    "Le connecteur MCP sera bientôt disponible. Revenez prochainement.",
                    color="info",
                ),
            ]
        )
        return account_shell("mcp", contenu)

    url = _mcp_url()
    new_token = session.pop("mcp_new_token", None)

    alerts = []
    if new_token:
        alerts.append(
            dbc.Alert(
                [
                    html.Strong("Votre nouveau jeton (copiez-le maintenant, "),
                    html.Strong("il ne sera plus affiché) :"),
                    html.Pre(html.Code(new_token)),
                ],
                color="success",
            )
        )

    tokens = tokens_db.list_user_tokens(
        os.environ["USERS_DB_PATH"], current_user.id, "mcp"
    )
    table = (
        dbc.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Nom"),
                            html.Th("Créé le"),
                            html.Th("Dernière utilisation"),
                            html.Th("Statut"),
                            html.Th(""),
                        ]
                    )
                ),
                html.Tbody([_token_row(dict(r)) for r in tokens]),
            ],
            striped=True,
            bordered=False,
            hover=True,
        )
        if tokens
        else html.P("Aucun jeton pour le moment.")
    )

    create_form = html.Form(
        method="POST",
        action="/compte/mcp/creer",
        className="mb-4",
        children=[
            _csrf("mcp-create"),
            dbc.Label("Nom du jeton (ex. « Claude sur mon portable »)"),
            dbc.Input(type="text", name="label", required=True, className="mb-2"),
            dbc.Button("Générer un jeton", type="submit", color="secondary"),
        ],
    )

    snippet_token = new_token or _TOKEN_PLACEHOLDER
    contenu = html.Div(
        [
            html.H2("Connecteur MCP"),
            html.P(
                "Les clients en ligne de commande (Claude Code, Gemini, Mistral) se "
                "connectent avec un jeton généré ci-dessous. Les applications grand "
                "public (Claude.ai, ChatGPT) se connectent par OAuth, sans jeton à "
                "copier. Dans tous les cas, un abonnement actif est requis."
            ),
            *alerts,
            html.H4("Générer un jeton", className="mt-3"),
            create_form,
            html.H4("Mes jetons", className="mt-4"),
            table,
            html.H4("Connecter un client", className="mt-4"),
            html.P(f"URL du serveur MCP : {url}"),
            client_instructions(url, snippet_token),
        ]
    )
    return account_shell("mcp", contenu)
