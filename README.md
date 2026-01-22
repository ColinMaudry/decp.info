# decp.info

> v2.4.1
> Outil d'exploration et de téléchargement des données essentielles de la commande publique.

=> [decp.info](https://decp.info)

## Installation et lancement

```shell
python -m venv .venv
source .venv/bin/activate
pip install .

# Copie et personnalisation du .env
cp template.env .env
nano .env

# Pour la production
gunicorn app:server

# Pour avoir le debuggage et le hot reload
python run.py
```

## Déploiement

- **Production** (branche `main`, [decp.info](https://decp.info)) : déploiement manuel via un déclenchement de la Github Action [Déploiement](https://github.com/ColinMaudry/decp.info/actions/workflows/deploy.yaml)
- **Test** (branche `dev`, [test.decp.info](https://test.decp.info)) : déploiement automatique à chaque push sur la branche `dev`, via la même Github Action.

Ne pas oublier de mettre à jour les fichier .env.

## Liens connexes

- [decp-processing](https://github.com/ColinMaudry/decp-processing) (traitement et publication des données)
- [colin.maudry.com](https://colin.maudry.com) (blog)

## Notes de version

Voir [CHANGELOG](https://github.com/ColinMaudry/decp.info/blob/main/CHANGELOG.md).
