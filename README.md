# decp.info

> Outil d'exploration et de téléchargement des données essentielles de la commande publique.

=> [decp.info](https://decp.info)

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

- **Production** (branche `main`, [decp.info](https://decp.info)) : déploiement manuel via un déclenchement de la Github Action [Déploiement](https://github.com/ColinMaudry/decp.info/actions/workflows/deploy.yaml)
- **Test** (branche `dev`, [test.decp.info](https://test.decp.info)) : déploiement automatique à chaque push sur la branche `dev`, via la même Github Action.

Ne pas oublier de mettre à jour les fichier .env.

### Sauvegarde de la base utilisateurs

`users.sqlite` est sauvegardée toutes les heures sur S3 via un timer systemd. Pour lister les sauvegardes disponibles :

```bash
python -m src.backup list
```

Pour restaurer une sauvegarde, arrêtez le service, restaurez la base, puis redémarrez :

```bash
systemctl stop decpinfo
python -m src.backup restore backups/users-YYYYMMDDTHHMMSSZ.sqlite.gz.enc
systemctl start decpinfo
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

Voir [CHANGELOG](https://github.com/ColinMaudry/decp.info/blob/main/CHANGELOG.md).
