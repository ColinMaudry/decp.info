import argparse
import os
import sys

from dotenv import load_dotenv

# Doit précéder l'import de src.api : celui-ci importe transitivement src.db,
# qui construit/ouvre la base DuckDB au chargement du module en lisant
# DATA_FILE_PARQUET_PATH. Charger le .env après cet import est trop tard —
# la variable est vide et la construction de la base échoue.
load_dotenv()

from src.api import tokens_db  # noqa: E402


def main(argv=None, env=None) -> int:
    env = env if env is not None else os.environ
    parser = argparse.ArgumentParser(prog="python -m src.api.tokens_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Créer un token API")
    p_create.add_argument("--label", required=True)
    p_create.add_argument("--user-id", type=int, default=None)

    sub.add_parser("list", help="Lister les tokens")

    p_revoke = sub.add_parser("revoke", help="Révoquer un token")
    p_revoke.add_argument("token_id", type=int)

    args = parser.parse_args(argv)
    db_path = env["USERS_DB_PATH"]
    tokens_db.init_schema(db_path)

    if args.cmd == "create":
        token, token_id = tokens_db.create_token(db_path, args.label, args.user_id)
        print(f"id={token_id} label={args.label}")
        print(f"token (à conserver, ne sera plus affiché) : {token}")
        return 0

    if args.cmd == "list":
        rows = tokens_db.list_tokens(db_path)
        if not rows:
            print("(aucun token)")
            return 0
        print(
            f"{'id':<4} {'label':<40} {'created_at':<26} {'last_used_at':<26} {'count':<7} revoked"
        )
        for r in rows:
            print(
                f"{r['id']:<4} {r['label']:<40} {r['created_at']:<26} "
                f"{(r['last_used_at'] or '-'):<26} {r['count_total']:<7} "
                f"{r['revoked_at'] or ''}"
            )
        return 0

    if args.cmd == "revoke":
        tokens_db.revoke_token(db_path, args.token_id)
        print(f"token id={args.token_id} révoqué")
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
