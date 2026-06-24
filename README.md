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

Voir `CLAUDE.md` pour la documentation complète de déploiement.

## Liens connexes

- [decp-processing](https://github.com/ColinMaudry/decp-processing) (traitement et publication des données)
- [colin.maudry.com](https://colin.maudry.com) (blog)

## Notes de version

Voir [CHANGELOG](https://github.com/ColinMaudry/decp.info/blob/main/CHANGELOG.md).
