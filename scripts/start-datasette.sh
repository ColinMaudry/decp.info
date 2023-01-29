#!/usr/bin/env bash

echo "Getting data from data.gouv.fr..."
wget -nv https://www.data.gouv.fr/fr/datasets/r/c6b08d03-7aa4-4132-b5b2-fd76633feecc -O datasette/db.db

datasette inspect datasette/*.db --inspect-file=datasette/inspect-data.json

echo "Starting datasette..."
datasette datasette/ --port 9090 --cors | grep -v "/static/"
