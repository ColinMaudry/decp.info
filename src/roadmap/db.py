from datetime import datetime, timezone

from src.auth.db import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_votes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    issue_number INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_feature_votes_issue
    ON feature_votes(issue_number);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema() -> None:
    get_conn().executescript(SCHEMA)


def record_vote(user_id: int, issue_number: int) -> None:
    get_conn().execute(
        "INSERT INTO feature_votes (user_id, issue_number, created_at) "
        "VALUES (?, ?, ?)",
        (user_id, issue_number, _now()),
    )


def vote_counts() -> dict[int, int]:
    rows = (
        get_conn()
        .execute(
            "SELECT issue_number, COUNT(*) FROM feature_votes GROUP BY issue_number"
        )
        .fetchall()
    )
    return {row[0]: row[1] for row in rows}
