from os import getenv

from src.app import app

# To use `gunicorn run:server` (prod)
server = app.server

# To use `python run.py` (dev)
if __name__ == "__main__":
    app.run(debug=True)
