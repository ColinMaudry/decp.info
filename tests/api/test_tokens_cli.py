import subprocess
import sys
from pathlib import Path

from src.api import tokens_cli, tokens_db


def _run(args, env):
    return tokens_cli.main(args, env=env)


def test_import_de_tokens_db_ne_tire_pas_duckdb():
    """`src.api` ne doit pas importer `src.db` au chargement du paquet.

    `src/db.py` construit ou ouvre la base DuckDB en effet de bord d'import.
    Tant que `src/api/__init__.py` importait `routes` au niveau module, un
    simple `from src.api import tokens_db` — du SQLite pur — déclenchait ce
    bootstrap.

    En production le CLI en mourait : sous `python -m src.api.tokens_cli`,
    runpy importe le paquet parent AVANT d'exécuter le corps du module, donc
    le `load_dotenv()` en tête de tokens_cli.py ne pouvait pas s'exécuter à
    temps. Sans .env, DUCKDB_PATH retombait sur `./decp.duckdb` (inexistant,
    la vraie base étant ailleurs) et DATA_FILE_PARQUET_PATH était vide, d'où
    une reconstruction tentée puis `AssertionError`.

    Sous-processus obligatoire : dans la suite de tests, `src.db` est déjà
    importé par d'autres modules, donc `sys.modules` ne prouverait rien ici.
    """
    code = "import src.api.tokens_db, sys; print('src.db' in sys.modules)"
    resultat = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    assert resultat.returncode == 0, resultat.stderr
    assert resultat.stdout.strip() == "False"


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
