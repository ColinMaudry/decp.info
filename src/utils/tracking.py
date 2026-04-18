import os
import uuid
from time import localtime

from httpx import post

from src.utils import DEVELOPMENT


def track_search(query, category):
    if len(query) >= 4 and not DEVELOPMENT and os.getenv("MATOMO_DOMAIN"):
        url = "https://decp.info"
        params = {
            "idsite": os.getenv("MATOMO_ID_SITE"),
            "url": url,
            "rec": "1",
            "action_name": "search" if category == "home_page_search" else "filter",
            "search_cat": category,
            "rand": uuid.uuid4().hex,
            "apiv": "1",
            "h": localtime().tm_hour,
            "m": localtime().tm_min,
            "s": localtime().tm_sec,
            "search": query,
            "token_auth": os.getenv("MATOMO_TOKEN"),
        }
        post(
            url=f"https://{os.getenv('MATOMO_DOMAIN')}/matomo.php",
            params=params,
        ).raise_for_status()
