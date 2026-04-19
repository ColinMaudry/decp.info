import logging
import os

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
DEVELOPMENT = os.getenv("DEVELOPMENT", "False").lower() == "true"
logger = logging.getLogger("decp.info")

if DEVELOPMENT:
    logger.setLevel(logging.DEBUG)

DOMAIN_NAME = (
    "test.decp.info"
    if os.getenv("DEVELOPMENT", "False").lower() == "true"
    else "decp.info"
)
