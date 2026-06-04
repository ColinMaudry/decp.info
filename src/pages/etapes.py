from dash import dcc, html, register_page

from src.utils.seo import META_CONTENT

NAME = "Quelles données pour quelles étapes et quels seuils ?"

register_page(
    __name__,
    path="/etapes",
    title=f"{NAME} | decp.info",
    name="Étapes et données",
    description=(
        "À chaque étape d'un marché public (programmation, publicité, "
        "attribution), quelles données sont publiées et à partir de quel "
        "seuil : DECP, BOAMP, JOUE, journaux d'annonces légales, Approch."
    ),
    image_url=META_CONTENT["image_url"],
)


def _lane(*bars):
    """Une ligne d'étape : fond segmenté en 5 + barres positionnées."""
    return html.Div(
        className="etapes-lane",
        children=[
            html.Div(
                className="etapes-segs",
                children=[html.Div() for _ in range(5)],
            ),
            *bars,
        ],
    )


def _bar(label, color, style):
    base = {"backgroundColor": color}
    base.update(style)
    return html.Div(label, className="etapes-bar", style=base)


def build_chart():
    return html.Div(
        className="etapes-chart-scroll",
        children=html.Div(
            className="etapes-chart",
            children=[
                # En-tête : coin vide + 5 marqueurs de seuils
                html.Div(className="etapes-corner"),
                html.Div(
                    className="etapes-xhead",
                    children=[
                        html.Div("0 €", className="etapes-xcell"),
                        html.Div(
                            [html.Strong("40 000 €"), "seuil DECP"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("90 000 €"), "publicité"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("140 k€ / 216 k€"), "seuils formalisés (UE)"],
                            className="etapes-xcell",
                        ),
                        html.Div(
                            [html.Strong("5,404 M€"), "travaux (UE)"],
                            className="etapes-xcell",
                        ),
                    ],
                ),
                # Programmation
                html.Div("Programmation", className="etapes-stage"),
                _lane(
                    _bar(
                        "Approch — sourcing / préinformation (non réglementaire)",
                        "#7c5cff",
                        {"left": "2%", "right": "2%"},
                    ),
                ),
                # Publicité (appel d'offres)
                html.Div(
                    ["Publicité ", html.Small("(appel d'offres)")],
                    className="etapes-stage",
                ),
                _lane(
                    _bar(
                        "Journaux d'annonces légales",
                        "#f79009",
                        {"left": "40%", "right": "40%", "top": "6px", "height": "20px"},
                    ),
                    _bar(
                        "BOAMP",
                        "#1570ef",
                        {"left": "40%", "right": "2%", "top": "28px", "height": "20px"},
                    ),
                    _bar(
                        "JOUE — avis de marché",
                        "#0e9384",
                        {"left": "60%", "right": "2%", "top": "6px", "height": "20px"},
                    ),
                ),
                # Attribution
                html.Div("Attribution", className="etapes-stage"),
                _lane(
                    _bar(
                        "DECP — données essentielles",
                        "#12b76a",
                        {"left": "20%", "right": "2%", "top": "6px", "height": "20px"},
                    ),
                    _bar(
                        "JOUE — avis d'attribution",
                        "#0e9384",
                        {"left": "60%", "right": "2%", "top": "28px", "height": "20px"},
                    ),
                ),
                # Contrat (vide)
                html.Div("Contrat", className="etapes-stage"),
                html.Div(
                    "— aucune donnée publiée aujourd'hui —",
                    className="etapes-lane etapes-empty",
                ),
                # Paiement (vide)
                html.Div("Paiement", className="etapes-stage"),
                html.Div(
                    "— aucune donnée publiée aujourd'hui —",
                    className="etapes-lane etapes-empty",
                ),
            ],
        ),
    )


# Données par étape, partagées par la vue mobile.
# Chaque item : (libellé, couleur, plage de seuils en texte).
STAGES_MOBILE = [
    (
        "Programmation",
        [
            ("Approch", "#7c5cff", "tous montants — publication non réglementaire"),
        ],
    ),
    (
        "Publicité (appel d'offres)",
        [
            (
                "Journaux d'annonces légales",
                "#f79009",
                "de 90 000 € au seuil formalisé",
            ),
            ("BOAMP", "#1570ef", "à partir de 90 000 €"),
            (
                "JOUE — avis de marché",
                "#0e9384",
                "à partir des seuils formalisés (140 k€ / 216 k€)",
            ),
        ],
    ),
    (
        "Attribution",
        [
            ("DECP — données essentielles", "#12b76a", "à partir de 40 000 €"),
            ("JOUE — avis d'attribution", "#0e9384", "à partir des seuils formalisés"),
        ],
    ),
    ("Contrat", []),
    ("Paiement", []),
]


def build_mobile():
    blocks = []
    for stage, items in STAGES_MOBILE:
        if items:
            children = [
                html.Div(
                    [
                        html.I(style={"backgroundColor": color}),
                        html.Span(label, className="etapes-m-label"),
                        html.Span(seuil, className="etapes-m-seuil"),
                    ],
                    className="etapes-m-item",
                )
                for label, color, seuil in items
            ]
        else:
            children = [
                html.Div(
                    "aucune donnée publiée aujourd'hui",
                    className="etapes-m-item etapes-m-empty",
                )
            ]
        blocks.append(
            html.Div(
                [html.H4(stage, className="etapes-m-stage"), *children],
                className="etapes-m-block",
            )
        )
    return html.Div(blocks, className="etapes-mobile")


def build_legend():
    items = [
        ("Approch", "#7c5cff"),
        ("Journaux d'annonces légales", "#f79009"),
        ("BOAMP", "#1570ef"),
        ("JOUE", "#0e9384"),
        ("DECP", "#12b76a"),
    ]
    return html.Div(
        className="etapes-legend",
        children=[
            html.Span(
                [
                    html.I(style={"backgroundColor": color}),
                    label,
                ]
            )
            for label, color in items
        ],
    )


layout = html.Div(
    className="container",
    children=[
        html.H2(NAME),
        dcc.Markdown(
            "Un marché public passe par plusieurs étapes. À chacune, des "
            "données peuvent être publiées — selon le montant du marché et "
            "des obligations réglementaires. Ce graphique situe les "
            "principales publications de données par **étape** (de haut en "
            "bas) et par **seuil** (de gauche à droite, en euros hors taxes)."
        ),
        build_chart(),
        build_mobile(),
        build_legend(),
        dcc.Markdown(
            "**À noter :** l'axe horizontal n'est pas linéaire — les seuils "
            "sont espacés régulièrement pour rester lisibles. Les étapes "
            "*Contrat* et *Paiement* n'ont aujourd'hui aucune donnée publiée "
            "en open data.",
            className="etapes-note",
        ),
    ],
)
