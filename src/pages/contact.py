import os
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dash import Input, Output, State, callback, dcc, html, register_page
from flask import request

from src.utils import meta_content

name = "Contact"
register_page(
    __name__,
    path="/contact",
    title=meta_content["title"],
    name=name,
    description=meta_content["description"],
    image_url=meta_content["image_url"],
    order=6,
)

layout = html.Div(
    className="container",
    children=[
        html.H2("Contact", id="contact"),
        html.P(
            "Votre message arrivera directement dans ma boîte mail, et je reviendrai vers vous rapidement."
        ),
        html.Div(
            [
                html.Label("Votre nom"),
                dcc.Input(
                    id="input-name",
                    type="text",
                    style={"width": "100%", "padding": "8px", "margin": "8px 0"},
                ),
                html.Label("Votre adresse email"),
                dcc.Input(
                    id="input-email",
                    type="email",
                    style={"width": "100%", "padding": "8px", "margin": "8px 0"},
                ),
                html.Label("Message"),
                dcc.Textarea(
                    id="input-message",
                    style={
                        "width": "100%",
                        "height": 200,
                        "padding": "8px",
                        "margin": "8px 0",
                    },
                ),
                html.Button(
                    "Envoyer    ",
                    id="submit-button",
                    n_clicks=0,
                    style={"marginTop": "10px"},
                ),
                html.Div(
                    id="output-message", style={"marginTop": "10px", "color": "green"}
                ),
            ],
            style={
                "maxWidth": "600px",
                "margin": "auto",
                "padding": "20px",
                "lineHeight": "20px",
            },
        ),
        dcc.Markdown("""
- Bluesky : [@col1m.bsky.social](https://bsky.app/profile/col1m.bsky.social)
- Mastodon : [col1m@mamot.fr](https://mamot.fr/@col1m)
- LinkedIn : [colinmaudry](https://www.linkedin.com/in/colinmaudry/)
- venez discuter de la transparence de la commande publique [sur le forum teamopendata.org](https://teamopendata.org/c/commande-publique/101)
"""),
    ],
)

rate_limit_store = {}  # {ip: last_timestamp}
RATE_LIMIT_WINDOW = 300  # 5 minutes


def is_rate_limited():
    ip = request.remote_addr
    now = time.time()
    last_time = rate_limit_store.get(ip)

    if last_time and (now - last_time) < RATE_LIMIT_WINDOW:
        return True  # rate limited !
    rate_limit_store[ip] = now  # màj du timestamp
    return False


def sanitize_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)


@callback(
    Output("output-message", "children"),
    Input("submit-button", "n_clicks"),
    State("input-name", "value"),
    State("input-email", "value"),
    State("input-message", "value"),
    prevent_initial_call=True,
)
def send_email(n_clicks, form_name, form_email, form_message):
    if not all([form_name, form_email, form_message]):
        return html.Div(
            "Veuillez s'il vous plaît remplir tous les champs.", style={"color": "red"}
        )

    client_ip = request.remote_addr
    if is_rate_limited():
        wait_time = int(RATE_LIMIT_WINDOW - (time.time() - rate_limit_store[client_ip]))
        return html.Div(
            f"⏳ J'ai mis en place une protection contre le spam, et vous m'avez écrit il y a moins de 5 minutes. "
            f"Veuillez s'il vous plaît attendre {wait_time} secondes avant de renvoyer un message.",
            style={"color": "black"},
        )

    try:
        # Configuration du serveur SMTP
        smtp_server = os.getenv("SENDER_SERVER_DOMAIN")
        smtp_port = 587
        login_email = os.getenv("LOGIN_EMAIL")
        from_email = os.getenv("FROM_EMAIL")
        to_email = os.getenv("TO_EMAIL", from_email)
        login_password = os.getenv("LOGIN_PASSWORD")

        print(
            smtp_server,
            smtp_port,
            login_email,
            from_email,
            to_email,
            login_password,
            sep="\n",
        )

        # Création de l'email
        email = MIMEMultipart()
        email["From"] = from_email
        email["To"] = to_email
        email["Subject"] = f"[decp.info] Message de {form_name}"

        body = f"""
        Nom : {form_name}
        Email : {form_email}

        Message :
        {form_message}
        """
        email.attach(MIMEText(body, "plain"))

        # Send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(login_email, login_password)
        server.sendmail(from_email, to_email, email.as_string())
        server.quit()

        return html.Div("✅ Envoi réussi", style={"color": "green"})

    except Exception as e:
        print(e)
        return html.Div(
            f"❌ Échec de l'envoi du message : {str(e)}", style={"color": "red"}
        )
