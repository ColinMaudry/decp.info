def test_migration_0007_adds_kind_to_legacy_api_tokens(monkeypatch, tmp_path):
    from src import migrations
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()

    conn = auth_db.get_conn()
    conn.execute("DROP TABLE IF EXISTS api_tokens")
    # ancienne table SANS colonne kind
    conn.execute(
        "CREATE TABLE api_tokens ("
        "id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, "
        "label TEXT NOT NULL, user_id INTEGER, created_at TEXT NOT NULL, "
        "last_used_at TEXT, count_total INTEGER NOT NULL DEFAULT 0, revoked_at TEXT)"
    )
    conn.commit()

    migrations.apply_pending()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(api_tokens)").fetchall()]
    assert "kind" in cols

    # idempotent : un second passage ne lève pas
    migrations.apply_pending()
    auth_db.reset_conn_for_tests()


def test_migration_0014_adds_trial_ends_at_to_legacy_subscriber_state(
    monkeypatch, tmp_path
):
    """Revue #132 : chaque test part de init_schema(), dont SUBSCRIPTIONS_SCHEMA
    contient déjà trial_ends_at — l'ALTER TABLE de la migration 0014 lève donc
    toujours "duplicate column name" et est avalé, sans jamais être exercé
    contre un schéma antérieur à son ajout. On reproduit ce schéma légitime en
    recréant subscriber_state sans la colonne."""
    from src import migrations
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()

    conn = auth_db.get_conn()
    conn.execute("DROP TABLE IF EXISTS subscriber_state")
    # ancien schéma SANS colonne trial_ends_at
    conn.execute(
        "CREATE TABLE subscriber_state ("
        "user_id INTEGER PRIMARY KEY, "
        "trial_used INTEGER NOT NULL DEFAULT 0, "
        "votes_balance INTEGER NOT NULL DEFAULT 0, "
        "votes_last_credited_at TEXT, "
        "updated_at TEXT NOT NULL)"
    )
    conn.commit()

    migrations.apply_pending()
    cols = [
        r[1] for r in conn.execute("PRAGMA table_info(subscriber_state)").fetchall()
    ]
    assert "trial_ends_at" in cols

    # idempotent : un second passage ne lève pas
    migrations.apply_pending()
    auth_db.reset_conn_for_tests()


def test_apply_pending_tolerates_missing_api_tokens_table(monkeypatch, tmp_path):
    from src import migrations
    from src.auth import db as auth_db
    from src.subscriptions import db as sub_db

    db_path = tmp_path / "users.test.sqlite"
    monkeypatch.setenv("USERS_DB_PATH", str(db_path))
    auth_db.reset_conn_for_tests()
    auth_db.init_schema()
    sub_db.init_schema()
    # api_tokens volontairement NON créée (chemin init_subscriptions sans init_api)
    migrations.apply_pending()  # ne doit pas lever
    auth_db.reset_conn_for_tests()
