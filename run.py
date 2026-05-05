from flask_cors import CORS

from src.app import app

# To use `gunicorn run:server` (prod)
server = app.server
CORS(server)

# To use `python run.py` (dev)
if __name__ == "__main__":
    app.run(debug=True)
