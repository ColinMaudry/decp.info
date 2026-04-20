import sqlite3

from src.auth import db


class User:
    def __init__(self, row: sqlite3.Row):
        self.id: int = row["id"]
        self.email: str = row["email"]
        self.email_verified: bool = bool(row["email_verified"])

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


def load_user(user_id: str) -> User | None:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    row = db.get_user_by_id(uid)
    return User(row) if row else None
