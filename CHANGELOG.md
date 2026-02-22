##### 2.6.2 (22 février 2026)

- Correction du téléchargemnent buggé dans /tableau

##### 2.6.1 (17 février 2026)

- Corrections la création des liens canoniques (SEO)

#### 2.6.0 (5 février 2026)

- Suite de la refonte graphique
- Persistence des filtres, des tris et des choix de colonnes sur toutes les pages
- Joli tableau pour choisir les colonnes à afficher
- Meilleure gestion des acheteurs et titulaires absents de la base SIRENE
- Amélioration du SEO (liens canoniques)

##### 2.5.1 (29 janvier 2026)

- Mise en production un peu hâtive ([#67](https://github.com/ColinMaudry/decp.info/issues/67), [#68](https://github.com/ColinMaudry/decp.info/issues/68))

#### 2.5.0 (29 janvier 2026)

- Refonte graphique et amélioration des textes d'aide
- Amélioration du filtrage du tableau à partir d'une URL
- Renforcement du SEO avec une arborescence permettant l'accès aux marchés et des snippets JSON-LD
- Suppression de la dépendance à Google Fonts grâce à [Bunny Fonts](https://fonts.bunny.net) 🇪🇺 🇸🇮

##### 2.4.1 (22 janvier 2026)

- Meilleure gestion des colonnes absentes du schéma

#### 2.4.0 (22 janvier 2026)

- Site à peu près utilisable sur petit écran (smartphone) ([#63](https://github.com/ColinMaudry/decp.info/issues/63))
- Ajout de nouvelles statistiques dans [/statistiques](https://decp.info/statistiques) (stats par année, doublons par source)
- Amélioration du référencement Web (sitemap, titres, descriptions) ([#50](https://github.com/ColinMaudry/decp.info/issues/50))
- Possibilité dans les champs non-numériques de filtrer le texte selon son début ou sa fin (`text*` et `*text`)
- Ajout d'une table des matières dans la page [À propos](https://decp.infi/a-propos) ([#36](https://github.com/ColinMaudry/decp.info/issues/36))
- Désactivation du bloquage des robot d'agents de LLM (robots.txt)

##### 2.3.1 (16 janvier 2026)

- Les champs absents du [schéma](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire?resource_id=9a4144c0-ee44-4dec-bee5-bbef38191d9a) sont ignorés pour éviter les erreurs

#### 2.3.0 (24 décembre 2025)

- Possibilité de filtrer, trier etc. dans les vues acheteur et titulaire
- Possibilité de partager les filtres, tris et choix de colonnes via une adresse Web ([exemple](https://decp.info/tableau?filtres=%7Bobjet%7D+icontains+%22d%C3%A9corations+de+no%C3%ABl%22+%26%26+%7BdateNotification%7D+icontains+2025&colonnes=uid%2Cacheteur_id%2Cacheteur_nom%2Ctitulaire_id%2Ctitulaire_nom%2Cobjet%2Cmontant%2CdateNotification%2Cdistance%2Cacheteur_departement_code))
- Possibilité de filtrer une colonne avec plusieurs mots

##### 2.2.3 (4 décembre 2025)

- mise à jour de l'adresse email de contact (colmo.tech)
- message sur l'indisponibilité des données MINEF

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
