from dash import dcc, html, register_page

title = "À propos"

register_page(
    __name__, path="/a-propos", title=f"decp.info - {title}", name=title, order=3
)

layout = [
    html.Div(
        className="container",
        children=[
            html.H2(title),
            dcc.Markdown(
                """Outil développé par Colin Maudry, sous licence GPL v3 (libre et gratuit).

- [wiki du projet](https://github.com/ColinMaudry/decp-processing/wiki)
- [code source de decp.info](https://github.com/ColinMaudry/decp.info)
- [code source du traitement de données](https://github.com/ColinMaudry/decp-processing)

Contact :
- [colin+decp@maudry.com](mailto:colin+decp@maudry.com)
- BlueSky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
"""
            ),
        ],
    )
]
