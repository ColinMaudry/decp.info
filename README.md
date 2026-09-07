# colibre

> **Note:** Ce projet a été rebaptisé de **decp.info** à **colibre** en 2026.

> Outil d'exploration et de téléchargement des données essentielles de la commande publique.

=> [colibre.fr](https://colibre.fr)

## Installation et lancement

```shell
# Copie et personnalisation du .env
cp template.env .env
nano .env

# Pour la production
uv run gunicorn app:server

# Pour avoir le debuggage et le hot reload
uv run run.py
```

## Déploiement

- **Production** (branche `main`, [colibre.fr](https://colibre.fr)) : déploiement manuel via un déclenchement de la Github Action [Déploiement](https://github.com/ColinMaudry/colibre/actions/workflows/deploy.yaml)
- **Test** (branche `dev`, [test.colibre.fr](https://test.colibre.fr)) : déploiement automatique à chaque push sur la branche `dev`, via la même Github Action.

Ne pas oublier de mettre à jour les fichier .env.

### Sauvegarde de la base utilisateurs

`users.sqlite` est sauvegardée toutes les heures sur S3 via un timer systemd.

Les unités systemd sont versionnées dans `deploy/`. Elles s'installent une seule fois, en root sur le serveur :

```bash
cd /var/www/colibre
cp deploy/colibre-backup.service deploy/colibre-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now colibre-backup.timer
systemctl list-timers colibre-backup.timer   # vérifier le prochain déclenchement
```

Le service s'exécute sous l'utilisateur `colibre` depuis `/var/www/colibre` et lit ses
identifiants dans le `.env` de l'app : renseignez `S3_BUCKET`, `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY` et `BACKUP_ENCRYPTION_KEY` (voir `.template.env`) avant d'activer
le timer. Pour consulter la dernière exécution : `journalctl -u colibre-backup.service -n 20`.

Pour lister les sauvegardes disponibles :

```bash
uv run python -m src.backup list
```

`uv run` active le venv du projet mais ne charge **pas** le `.env` : d'où le `--env-file`,
sans lequel la commande échoue sur `KeyError: 'USERS_DB_PATH'`.

Pour restaurer une sauvegarde, arrêtez le service, restaurez la base, puis redémarrez :

```bash
systemctl stop colibre
uv run --env-file .env python -m src.backup restore backups/users-YYYYMMDDTHHMMSSZ.sqlite.gz.enc
systemctl start colibre
```

## Migrations de base de données

Les migrations SQLite s'appliquent **automatiquement au démarrage de l'app** — aucune action manuelle requise. Il suffit de redémarrer le service après un déploiement.

Pour vérifier quelles migrations ont été appliquées :

```bash
sqlite3 users.sqlite "SELECT id, applied_at FROM schema_migrations ORDER BY applied_at;"
```

Pour ajouter une migration, voir les instructions dans `src/migrations.py`.

## Liens connexes

- [decp-processing](https://github.com/ColinMaudry/decp-processing) (traitement et publication des données)
- [colin.maudry.com](https://colin.maudry.com) (blog)

## Notes de version

Voir [CHANGELOG](https://github.com/ColinMaudry/colibre/blob/main/CHANGELOG.md).
