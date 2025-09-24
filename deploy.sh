#!bin/bash

# Utilisé principalement avec les Github Actions
# cf. .github/workflows/deploy.yaml

appname = "$1"

systemctl stop $appname
cd /var/www/$appname
git pull
source .venv/bin/activate
pip install .
deactivate
chown -R $appname:www-data *
systemctl start $appname
