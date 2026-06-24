import argparse
import logging
import os
import sys
from datetime import datetime, timezone

from src.backup import service
from src.backup.config import load_config
from src.backup.storage import S3Storage

logger = logging.getLogger(__name__)


def main(argv=None, env=None, storage=None) -> int:
    env = env if env is not None else os.environ
    parser = argparse.ArgumentParser(prog="python -m src.backup")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup", help="Créer une sauvegarde et appliquer la rotation")
    sub.add_parser("list", help="Lister les sauvegardes disponibles")
    p_restore = sub.add_parser("restore", help="Restaurer une sauvegarde")
    p_restore.add_argument("key", help="Clé S3 de la sauvegarde à restaurer")
    args = parser.parse_args(argv)

    config = load_config(env)
    if storage is None:
        storage = S3Storage.from_config(config)
    now = datetime.now(timezone.utc)

    if args.cmd == "backup":
        try:
            key = service.run_backup(config, storage, now)
            print(f"sauvegarde créée : {key}")
            return 0
        except Exception as exc:
            logger.error("Échec de la sauvegarde : %s", exc, exc_info=True)
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1

    if args.cmd == "list":
        backups = service.list_backups(config, storage)
        if not backups:
            print("(aucune sauvegarde)")
            return 0
        for key, ts in backups:
            print(f"{ts.isoformat()}  {key}")
        return 0

    if args.cmd == "restore":
        print("⚠ Arrêtez d'abord le service : systemctl stop decpinfo")
        backup_copy = service.restore(config, storage, args.key, now)
        print(f"restauré depuis : {args.key}")
        print(f"copie de secours de l'ancienne base : {backup_copy}")
        print("Redémarrez ensuite le service : systemctl start decpinfo")
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
