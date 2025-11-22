# decp.info

> v2.2.2

Outil d'exploration et de téléchargement des données essentielles de la commande publique.

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

##### 2.2.2 (22 novembre 2025)

- Correction d'un bug dans le téléchargement Excel

##### 2.2.1 (15 novembre 2025)

- Le moteur de recherche ignore les tirets ("franche comté" trouve "Bourgogne-Franche-Comté)
- Phrase "tagline" au-dessus du champ de recherche
- Les infos de Contact rebasculent dans À propos
- Police de caractère "Open Sans" généralisée

#### 2.2.0 (13 novembre 2025)

- Moteur de recherche (acheteurs et titulaires) en page d'accueil ([#58](https://github.com/ColinMaudry/decp.info/issues/58))
- Top acheteurs / titulaires par montant attribué/remporté (([#55](https://github.com/ColinMaudry/decp.info/issues/55)))
- Moins de colonnes affichées par défaut dans Tableau ([#54](https://github.com/ColinMaudry/decp.info/issues/54))

##### 2.1.7 (11 novembre 2025)

- Remplacement du formulaire de contact par une adresse email

##### 2.1.6 (15 octobre 2025)

- Stabilisation de la vue marché

##### 2.1.5 (10 octobre 2025)

- réparation des filtres (notamment < > sur les montants)
- remplacement des valeurs "null" dans les tableaux par des cellules vides

##### 2.1.4 (8 octobre 2025)

- possibilité de filtrer sur le champ "Source"
- création automatique d'une release Github quand je push un tag

##### 2.1.3 (4 octobre 2025)

- tentative d'auto-release à chaque création de tag git
- adaptation au format TableSchema

##### 2.1.2 (3 octobre 2025)

- dataframe global plutôt que lazyframe, pour plus de résilience et charger toutes les données en mémoire

##### 2.1.1 (1er octobre 2025)

- ajout d'une section dans À propos sur la qualité et l'exhaustivité des données ([#43](https://github.com/ColinMaudry/decp.info/issues/43))
- ajout du nombre de marchés en plus du nombre de lignes dans la vue Tableau

#### 2.1.0 (30 septembre 2025)

- Ajout des vues [acheteur](https://decp.info/acheteurs/24350013900189) ([#28](https://github.com/ColinMaudry/decp.info/issues/28)), [titulaire](https://decp.info/titulaires/51903758414786) ([#35](https://github.com/ColinMaudry/decp.info/issues/35)) et [marché](https://decp.info/marches/532239472000482025S00004) ([#40](https://github.com/ColinMaudry/decp.info/issues/40)) 🔎
- Ajout des balises HTML meta Open Graph et Twitter ([#39](https://github.com/ColinMaudry/decp.info/issues/39)) pour de beaux aperçus de liens 🖼️
- Formulaire de contact ([#48](https://github.com/ColinMaudry/decp.info/issues/48)) 📨
- Nom de colonnes plus_agréables ([#33](https://github.com/ColinMaudry/decp.info/issues/33)) 💅
- Définition des colonnes quand vous passez votre souris sur les en-têtes ([#33](https://github.com/ColinMaudry/decp.info/issues/33)) 📖
- Affichage du numéro de version près du logo et lien vers ici 🤓
- Variables globales uniquement en lecture (😁)

##### 2.0.1 (23 septembre 2025)

- Bloquage du bouton de téléchargement si trop de lignes (+ 65000) [#38](https://github.com/ColinMaudry/decp.info/issues/38)
- Amélioration du script de déploiement (deploy.sh)
- Meilleures instructions d'installation et lancement
- Coquilles 🐚

### 2.0.0 (23 septembre 2025)

- détails des sources de données
- section "À propos" plus développée
- correction de bugs dans les filtres de la data table

#### 2.0.0-alpha

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
