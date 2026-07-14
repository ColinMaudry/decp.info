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

MCP_ENABLED = os.getenv("DASH_MCP_ENABLED", "").lower() == "true"
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
    gemini = f'gemini mcp add --scope user --transport http --header "Authorization: Bearer {token}" colibre {url}'
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
                                "Icône utilisateur → Paramètres → Connecteurs → Ajouter → Ajouter un connecteur personnalisé."
                            ),
                            html.Li("Nom : colibre"),
                            html.Li(f"URL du serveur MCP distant : {url}"),
                            html.Li(
                                'Laissez les champs "Client ID" et "Client secret" vides.'
                            ),
                            html.Li(
                                'Connectez-vous avec votre compte colibre, puis "Autoriser".'
                            ),
                        ]
                    ),
                ],
            ),
            dbc.AccordionItem(
                title="Gemini CLI",
                children=[
                    html.Pre(html.Code(gemini)),
                ],
            ),
            dbc.AccordionItem(
                title="Mistral Vibe",
                children=dcc.Markdown(f"""
                    1. Sur l'[interface Work](https://chat.mistral.ai/work), cliquez sur **Connectez vos applications...**
                    2. Cliquez sur **+ Ajouter un connecteur**
                    3. Cliquez sur **Connecteur personnalisé**
                    4. Titre : colibre, Description : Base de données ouverte des marchés publics français (par exemple)
                    5. Serveur : `{url}`
                    6. Méthode d'authentification : Authentification par token API
                    7. Valeur du header : Bearer <VOTRE_JETON>
                    8. Cliquez sur **Créer**
                    """),
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


def prompt_tips():
    """Exemples de prompts pour guider l'utilisateur (fonction pure, testable)."""
    exemples = [
        "Depuis colibre, trouve le dernier marché public attribué par le "
        "département du Morbihan.",
        "Donne-moi les statistiques de l'acheteur Rennes Métropole : nombre de "
        "marchés, montant total et principaux titulaires.",
        "Quelles entreprises ont remporté le plus de marchés d'informatique "
        "(CPV 72) en Ille-et-Vilaine depuis 2023 ?",
        "Reprends ces marchés en n'affichant que l'objet, le montant et la date "
        "de notification, avec le lien vers chaque fiche.",
    ]
    return html.Div(
        [
            html.P(
                "L'assistant découvre seul les outils disponibles : décrivez "
                "votre besoin en langage naturel. Quelques exemples :"
            ),
            html.Ul([html.Li(html.Em(f"« {p} »")) for p in exemples]),
            html.P(
                "Astuce colonnes : demandez à l'assistant de vous proposer les "
                "colonnes disponibles pour choisir précisément ce qui s'affiche sous la forme, si possible d'une liste de cases à cocher "
                "(les colonnes par défaut restent pré-sélectionnées). Chaque "
                "marché renvoyé inclut un lien direct vers sa fiche sur colibre.",
                className="text-muted",
            ),
        ]
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
                "Un connecteur MCP est une interface proposée par un outil (ici colibre) pour faciliter "
                "son interrogation par un agent IA tel que Mistral, Claude ou ChatGPT. "
                "Dans le cas de colibre, cela vous permet de poser des questions très précises aux données, "
                "et d'obtenir une réponse rapide, précise et peu couteuse."
            ),
            html.P(
                "L'utilisation de cette fonctionnalité étant liée à un abonnement, vous devez d'abord vous authentifiez auprès "
                "dans les options de votre agent IA. La méthode varie selon les outils."
            ),
            html.H4("Connecter un client", className="mt-4"),
            client_instructions(url, snippet_token),
            *alerts,
            html.H4("Générer un jeton", className="mt-3"),
            create_form,
            html.H4("Mes jetons", className="mt-4"),
            table,
            html.H4("Conseils de prompts", className="mt-4"),
            prompt_tips(),
        ]
    )
    return account_shell("mcp", contenu)
