import os

from authlib.integrations.flask_client import OAuth
from flask import Flask

LINKEDIN_DISCOVERY_URL = (
    "https://www.linkedin.com/oauth/.well-known/openid-configuration"
)

oauth = OAuth()


def init_oauth(app: Flask) -> None:
    oauth.init_app(app)
    oauth.register(
        name="linkedin",
        client_id=os.getenv("LINKEDIN_CLIENT_ID"),
        client_secret=os.getenv("LINKEDIN_CLIENT_SECRET"),
        server_metadata_url=LINKEDIN_DISCOVERY_URL,
        client_kwargs={"scope": "openid profile email"},
    )
