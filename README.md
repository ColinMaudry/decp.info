# decp.info

Outil d'exploration et de téléchargement des données essentielles de la commande publique.

=> [decp.info](https://decp.info)

## Installation et lancement

```shell
python -m venv .venv
source .venv/bin/activate
pip install .
gunicorn app:server
```
## Dépôts de code connexes

- [decp-processing](https://github.com/ColinMaudry/decp-processing) (traitement et publication des données)
- [decp-table-schema](https://github.com/ColinMaudry/decp-table-schema) (schéma de données tabulaire)

## Notes de version

### 2.0.0-alpha

- Data table fonctionnelle

### 1.5.0 (28/01/2023

- fixation des dépendances Python pour plus de stabilité en cas de réinstallation (Pipfile)

#### 1.4.1 (14/06/2021)

- ajout des traductions des opérations de filtrage à toutes les vues, pas seulement /db/decp

### 1.4.0 (14/06/2021)

- traduction des opérations de filtrage (ex : contains => contient)
- élargissement des menus de filtrage
- correction du titre de la page des notes de versions

### 1.3.0 (03/06/2021)

- utilisation de noms de colonnes plus lisibles dans l'application
- suppression des références à la licence et aux données source sur la page d'accueil
- correction des liens vers le code source
- correction de l'indentation des puces dans les notes de version

### 1.2.0 (28/05/2021)

- ajout d'une page "Notes de version"
- meilleur lien pour la documentation des champs
- déplacement du code de decp.info depuis [ColinMaudry/decp-table-schema-utils](https://github.com/ColinMaudry/decp-table-schema-utils) vers [ColinMaudry/decp.info](https://github.com/ColinMaudry/decp.info)

### 1.1.0 (25/05/2021)

- ajout de nouvelles vues :
  - Marchés publics sans leurs titulaires : vue dédiée aux titulaires de marchés avec des données provenant du répertoire SIRENE
  - Données sur les titulaires et géolocalisation : vue sans les titulaires pour analyser les nombres de marchés et les montants
- amélioration de la page d'accueil
- développement de la page "db" avec description des vues et liste des colonnes
- les codes APE sont cliquables
- ajout des mentions légales
- ajout d'un formulatire d'inscription à une lettre d'information
- correction de bugs :
  - correction du format de certaines dates dans les données

### 1.0.0

- publication sur https://decp.info
- ajout d'une vue équivalente au format DECP réglementaire
- personnalisation de datasette
- script de conversion quotidien basé sur [dataflows](https://github.com/datahq/dataflows)
