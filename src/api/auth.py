import os
from functools import wraps

from flask import abort, g, jsonify, make_response, request

from src.api import tokens_db

API_AUTH_DISABLED = os.getenv("API_AUTH_DISABLED", "False").lower() == "true"


def _abort_401(message: str):
    resp = make_response(jsonify({"message": message}), 401)
    abort(resp)


def require_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        print(API_AUTH_DISABLED)
        if not API_AUTH_DISABLED:
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                _abort_401("missing_token")
            token = header[len("Bearer ") :].strip()
            if not token:
                _abort_401("missing_token")
            db_path = os.environ["USERS_DB_PATH"]
            row = tokens_db.get_token_by_plaintext(db_path, token)
            if row is None:
                _abort_401("invalid_token")
            if row["revoked_at"] is not None:
                _abort_401("revoked_token")
            g.token_id = row["id"]
        return fn(*args, **kwargs)

    return wrapper
