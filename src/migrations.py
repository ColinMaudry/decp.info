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
                # SQLite ne supporte pas ALTER TABLE … ADD COLUMN IF NOT EXISTS.
                # Sur une DB fraîche (schéma déjà à jour), on ignore l'erreur.
                if "duplicate column name" not in str(exc):
                    raise
            conn.execute(
                "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
                (migration_id, now),
            )
    conn.commit()
