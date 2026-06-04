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
        # Le graphique sera inséré ici en Task 2
        dcc.Markdown(
            "**À noter :** l'axe horizontal n'est pas linéaire — les seuils "
            "sont espacés régulièrement pour rester lisibles. Les étapes "
            "*Contrat* et *Paiement* n'ont aujourd'hui aucune donnée publiée "
            "en open data.",
            className="etapes-note",
        ),
    ],
)
