# decp.info

Outil d'exploration et de téléchargement des données essentielles de la commande publique.

=> https://decp.info

Dépôts de code connexe :

- [decp-table-schema-utils](https://github.com/ColinMaudry/decp-table-schema-utils) (traitement et publication des données)
- [decp-table-schema](https://github.com/ColinMaudry/decp-table-schema) (schéma de données tabulaire)

## Notes de version

### 1.2.0 (28/05/2021)

- déplacement du code de decp.info depuis [ColinMaudry/decp-table-schema-utils](https://github.com/ColinMaudry/decp-table-schema-utils) vers [ColinMaudry/decp.info](https://github.com/ColinMaudry/decp.info)
- remplacement du fichier `.sqlite.gz` par `.sqlite` 

### 1.1.0 (25/05/2021)

- ajout de nouvelles vues :
  - vue dédiée aux titulaires de marchés (`decp-titulaires`) avec données provenant du répertoire SIRENE
  - vue sans les titulaires (`decp-sans-titulaires`) pour analyser les nombres de marchés et les montants
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
