"""
Migrations de schéma SQLite.

Ajouter une migration : append un tuple (id, sql) à _MIGRATIONS.
L'id doit être unique et croissant (convention : NNNN_description).
apply_pending() est idempotent ; elle peut être appelée à chaque démarrage.
"""

import sqlite3
from datetime import datetime, timezone

from src.auth.db import get_conn

_MIGRATIONS: list[tuple[str, str]] = [
    (
        "0001_add_prix_ht_to_subscriptions",
        "ALTER TABLE subscriptions ADD COLUMN prix_ht REAL",
    ),
    (
        "0002_add_siret_to_users",
        "ALTER TABLE users ADD COLUMN siret TEXT",
    ),
    (
        "0003_add_votes_balance_to_subscriptions",
        "ALTER TABLE subscriptions ADD COLUMN votes_balance INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "0004_add_votes_last_credited_at_to_subscriptions",
        "ALTER TABLE subscriptions ADD COLUMN votes_last_credited_at TEXT",
    ),
    (
        "0005_rename_votes_credited_until_to_votes_last_credited_at",
        "ALTER TABLE subscriptions RENAME COLUMN votes_credited_until TO votes_last_credited_at",
    ),
    (
        "0006_create_admin_actions",
        "CREATE TABLE IF NOT EXISTS admin_actions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "admin_email TEXT NOT NULL, "
        "action TEXT NOT NULL, "
        "target_user_id INTEGER, "
        "details TEXT, "
        "created_at TEXT NOT NULL)",
    ),
    (
        "0007_add_kind_to_api_tokens",
        "ALTER TABLE api_tokens ADD COLUMN kind TEXT NOT NULL DEFAULT 'api'",
    ),
]


def apply_pending() -> None:
    conn = get_conn()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {
        row[0] for row in conn.execute("SELECT id FROM schema_migrations").fetchall()
    }
    now = datetime.now(timezone.utc).isoformat()
    for migration_id, sql in _MIGRATIONS:
        if migration_id not in applied:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as exc:
                # Sur une DB fraîche (schéma déjà à jour), certaines migrations
                # sont sans effet : ADD COLUMN → "duplicate column name",
                # RENAME COLUMN → "no such column", et un ALTER sur une table pas
                # encore créée → "no such table" (elle sera créée plus tard par
                # init_schema avec la colonne déjà dans SCHEMA).
                err = str(exc)
                if (
                    "duplicate column name" not in err
                    and "no such column" not in err
                    and "no such table" not in err
                ):
                    raise
            conn.execute(
                "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
                (migration_id, now),
            )
    conn.commit()
