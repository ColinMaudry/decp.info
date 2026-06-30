from src.api import tokens_cli, tokens_db


def _run(args, env):
    return tokens_cli.main(args, env=env)


def test_create_prints_plaintext_token_once(temp_db, capsys):
    rc = _run(["create", "--label", "alice"], env={"USERS_DB_PATH": str(temp_db)})
    out = capsys.readouterr().out
    assert rc == 0
    assert "colibre_" in out
    tokens = tokens_db.list_tokens(temp_db)
    assert len(tokens) == 1
    assert tokens[0]["label"] == "alice"


def test_list_shows_tokens(temp_db, capsys):
    tokens_db.create_token(temp_db, "alice")
    tokens_db.create_token(temp_db, "bob")
    rc = _run(["list"], env={"USERS_DB_PATH": str(temp_db)})
    out = capsys.readouterr().out
    assert rc == 0
    assert "alice" in out
    assert "bob" in out


def test_revoke_sets_revoked_at(temp_db, capsys):
    _, token_id = tokens_db.create_token(temp_db, "alice")
    rc = _run(["revoke", str(token_id)], env={"USERS_DB_PATH": str(temp_db)})
    assert rc == 0
    tokens = tokens_db.list_tokens(temp_db)
    assert tokens[0]["revoked_at"] is not None
