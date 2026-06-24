# Spécifications fonctionnelles et techniques d'un profil d'acheteur

> Source : [Arrêté du 22 mars 2019](https://www.legifrance.gouv.fr/loda/id/JORFTEXT000038318516) relatif aux fonctionnalités et exigences minimales des profils d'acheteurs (NOR : ECOM1831551A). Annexe 7 du Code de la commande publique. En vigueur depuis le 1er avril 2019.

## 1. Fonctionnalités pour l'acheteur (marchés publics)

_Réf. : Article 1, I_

Le profil d'acheteur doit permettre à l'acheteur de :

| ID     | Fonctionnalité                     | Description                                                                                                                                                 |
| ------ | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ACH-01 | Identification et authentification | S'identifier et s'authentifier sur la plateforme                                                                                                            |
| ACH-02 | Publication d'avis                 | Publier des avis d'appel à la concurrence et leurs éventuelles modifications                                                                                |
| ACH-03 | Mise à disposition des DCE         | Mettre à disposition des documents de la consultation                                                                                                       |
| ACH-04 | Réception des candidatures         | Réceptionner et conserver des candidatures, y compris sous forme de DUME (Document Unique de Marché Européen) électronique (échange de données structurées) |
| ACH-05 | Réception des offres               | Réceptionner et conserver des offres, y compris hors délais                                                                                                 |
| ACH-06 | Données essentielles               | Compléter un formulaire de publication des données essentielles (DECP), ou importer ces données depuis un autre SI                                          |
| ACH-07 | Courrier électronique              | Accéder à un service de courrier électronique (au sens de l'article 1 de la loi n° 2004-575)                                                                |
| ACH-08 | Historique et traçabilité          | Accéder à un historique des événements : enregistrement et traçabilité des actions (retrait, dépôt de documents, etc.)                                      |
| ACH-09 | Réponses aux questions             | Répondre aux questions soumises par les entreprises                                                                                                         |
| ACH-10 | Justificatifs et preuves           | Obtenir les documents justificatifs et moyens de preuve directement auprès d'autres administrations lorsque c'est possible                                  |

## 2. Fonctionnalités pour l'opérateur économique (marchés publics)

_Réf. : Article 1, II_

Le profil d'acheteur doit permettre à l'opérateur économique de :

| ID    | Fonctionnalité                     | Description                                                                                                                                                    |
| ----- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OE-01 | Identification et authentification | S'identifier et s'authentifier sur la plateforme                                                                                                               |
| OE-02 | Prérequis techniques               | Connaître les prérequis techniques et les modules d'extension nécessaires pour utiliser le profil d'acheteur                                                   |
| OE-03 | Test de configuration              | Accéder à un espace de test permettant de vérifier l'adéquation de la configuration du poste de travail avec les prérequis techniques                          |
| OE-04 | Recherche                          | Effectuer une recherche donnant accès aux avis d'appel à la concurrence, aux consultations et aux données essentielles                                         |
| OE-05 | Consultation des documents         | Consulter et télécharger en accès gratuit, libre, direct et complet les documents de la consultation, les avis d'appel à la concurrence et leurs modifications |
| OE-06 | Simulation de dépôt                | Accéder à un espace permettant de simuler le dépôt de documents                                                                                                |
| OE-07 | Dépôt de candidature               | Déposer une candidature, y compris sous forme de DUME électronique (données structurées)                                                                       |
| OE-08 | Dépôt d'offres                     | Déposer des offres, y compris les dépôts successifs (quand la procédure le requiert) et les offres signées électroniquement                                    |
| OE-09 | Assistance                         | Solliciter une assistance ou consulter un support utilisateur pour les problématiques techniques                                                               |
| OE-10 | Questions à l'acheteur             | Formuler des questions à l'acheteur                                                                                                                            |
| OE-11 | Données essentielles               | Consulter et télécharger les données essentielles de la commande publique                                                                                      |

## 3. Exigences techniques, de sécurité et d'accessibilité (marchés publics)

_Réf. : Article 2_

### 3.1. Conformité aux référentiels

| ID     | Exigence         | Référentiel                                                                                      |
| ------ | ---------------- | ------------------------------------------------------------------------------------------------ |
| SEC-01 | Sécurité         | Conformité au Référentiel Général de Sécurité (RGS) — art. 9 de l'ordonnance n° 2005-1516        |
| SEC-02 | Interopérabilité | Conformité au Référentiel Général d'Interopérabilité (RGI) — art. 9 de l'ordonnance n° 2005-1516 |
| SEC-03 | Accessibilité    | Conformité au Référentiel Général d'Accessibilité (RGAA) — art. 11 de l'ordonnance n° 2005-1516  |

### 3.2. Exigences techniques

| ID      | Exigence                        | Description                                                                                                                                                                                                                                                                                                                                                 |
| ------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TECH-01 | Formats de fichiers             | Accepter les fichiers communément disponibles, et notamment les formats `.XML` et `.JSON`                                                                                                                                                                                                                                                                   |
| TECH-02 | Information sur les formats     | Indiquer la taille et les formats des documents et avis d'appel à la concurrence                                                                                                                                                                                                                                                                            |
| TECH-03 | Horodatage qualifié             | L'horodatage doit être qualifié conformément au règlement eIDAS (n° 910/2014)                                                                                                                                                                                                                                                                               |
| TECH-04 | Intégrité des données           | Assurer l'intégrité des données                                                                                                                                                                                                                                                                                                                             |
| TECH-05 | Responsive design               | Permettre une visualisation adaptée au média utilisé (responsive)                                                                                                                                                                                                                                                                                           |
| TECH-06 | Confidentialité des soumissions | Garantir la confidentialité des candidatures, offres et demandes de participation jusqu'à l'expiration du délai de soumission. Les documents sont inaccessibles avant cette date, puis accessibles uniquement aux personnes autorisées. Recours obligatoire à des moyens de cryptologie, de gestion des droits d'accès/privilèges, ou technique équivalente |
| TECH-07 | Interopérabilité                | Être interopérable avec les autres outils et dispositifs de communication électronique et d'échanges d'informations utilisés dans le cadre de la commande publique                                                                                                                                                                                          |

### 3.3. Accusé de réception

_Réf. : Article 2, III_

Chaque dépôt de documents par un opérateur économique doit déclencher **immédiatement** l'envoi d'un accusé de réception automatique contenant :

| ID    | Champ                      | Description                                              |
| ----- | -------------------------- | -------------------------------------------------------- |
| AR-01 | Identification du déposant | Identification de l'opérateur économique auteur du dépôt |
| AR-02 | Nom de l'acheteur          | Nom de l'acheteur public                                 |
| AR-03 | Consultation               | Intitulé et objet de la consultation concernée           |
| AR-04 | Horodatage                 | Date et heure de réception des documents                 |
| AR-05 | Liste des documents        | Liste détaillée des documents transmis                   |

## 4. Fonctionnalités spécifiques aux concessions

_Réf. : Article 3_

### 4.1. Fonctionnalités pour l'autorité concédante

| ID          | Fonctionnalité                     | Description                                                                                                            |
| ----------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| CONC-ACH-01 | Identification et authentification | S'identifier et s'authentifier                                                                                         |
| CONC-ACH-02 | Mise à disposition des DCE         | Mettre à disposition des documents de la consultation                                                                  |
| CONC-ACH-03 | Réception des candidatures         | Réceptionner et conserver des candidatures                                                                             |
| CONC-ACH-04 | Réception des offres               | Réceptionner et conserver des offres, y compris hors délais                                                            |
| CONC-ACH-05 | Données essentielles               | Compléter un formulaire de publication des données essentielles ou importer ces données depuis un autre SI             |
| CONC-ACH-06 | Historique et traçabilité          | Accéder à un historique des événements : enregistrement et traçabilité des actions (retrait, dépôt de documents, etc.) |

### 4.2. Fonctionnalités pour l'opérateur économique (concessions)

| ID         | Fonctionnalité                     | Description                                                                                          |
| ---------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------- |
| CONC-OE-01 | Identification et authentification | S'identifier et s'authentifier                                                                       |
| CONC-OE-02 | Prérequis techniques               | Connaître les prérequis techniques et modules d'extension nécessaires                                |
| CONC-OE-03 | Test de configuration              | Accéder à un espace de test de la configuration du poste de travail                                  |
| CONC-OE-04 | Recherche                          | Effectuer une recherche donnant accès aux consultations et aux données essentielles                  |
| CONC-OE-05 | Consultation des documents         | Consulter et télécharger en accès gratuit, libre, direct et complet les documents de la consultation |
| CONC-OE-06 | Simulation de dépôt                | Accéder à un espace de simulation de dépôt de documents                                              |
| CONC-OE-07 | Dépôt de candidature               | Déposer une candidature                                                                              |
| CONC-OE-08 | Dépôt d'offres                     | Déposer des offres                                                                                   |
| CONC-OE-09 | Assistance                         | Solliciter une assistance ou consulter un support utilisateur                                        |
| CONC-OE-10 | Données essentielles               | Consulter et télécharger les données essentielles                                                    |

### 4.3. Exigences techniques (concessions)

| ID          | Exigence                    | Description                                                                                                                                                                                   |
| ----------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CONC-SEC-01 | Confidentialité             | Garantir la confidentialité des candidatures, offres et demandes de participation jusqu'à expiration du délai. Recours à la cryptologie, gestion des droits d'accès, ou technique équivalente |
| CONC-SEC-02 | Intégrité                   | Assurer l'intégrité des données                                                                                                                                                               |
| CONC-SEC-03 | Responsive design           | Permettre une visualisation adaptée au média utilisé                                                                                                                                          |
| CONC-SEC-04 | Conformité aux référentiels | Conformité au RGS, RGI et RGAA (art. 9 et 11 de l'ordonnance n° 2005-1516)                                                                                                                    |

### 4.4. Accusé de réception (concessions)

Mêmes exigences que pour les marchés publics (section 3.3), à l'exception du champ AR-02 qui mentionne le nom de **l'autorité concédante** au lieu de l'acheteur public.

## 5. Référencement du profil d'acheteur

_Réf. : Article 4_

### 5.1. Publication

Le profil d'acheteur doit figurer sur une liste publiée sur le portail unique interministériel de données ouvertes (data.gouv.fr).

### 5.2. Identification

Chaque profil d'acheteur est identifié par :

| ID     | Champ         | Description                                            |
| ------ | ------------- | ------------------------------------------------------ |
| REF-01 | SIRET         | Numéro SIRET de l'acheteur                             |
| REF-02 | URL du profil | Adresse URL du profil d'acheteur                       |
| REF-03 | URL du DCAT   | Adresse URL du catalogue DCAT des données essentielles |
| REF-04 | Coordonnées   | Coordonnées du ou des acheteurs concernés              |

### 5.3. Déclaration

La déclaration du profil est effectuée par l'acheteur ou une personne habilitée sur le portail de données ouvertes. Elle comporte :

- L'identité du déclarant
- L'identité de l'organisme chargé de la gestion du profil d'acheteur
- L'adresse URL du profil d'acheteur
- L'adresse URL du DCAT
- Les coordonnées du ou des acheteurs concernés

## 6. Dispositions particulières outre-mer

_Réf. : Article 5_

| Territoire                                 | Adaptation                                                                                                                                                                            |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Saint-Barthélemy, Saint-Pierre-et-Miquelon | Horodatage qualifié conformément aux dispositions applicables en métropole en vertu du règlement eIDAS                                                                                |
| Nouvelle-Calédonie, Polynésie française    | Horodatage qualifié conformément aux dispositions applicables localement. Applicable uniquement aux contrats de l'État et de ses établissements publics                               |
| Wallis-et-Futuna, TAAF                     | Horodatage qualifié conformément aux dispositions applicables en métropole en vertu du règlement eIDAS. Applicable uniquement aux contrats de l'État et de ses établissements publics |

## 7. Matrice de correspondance fonctionnelle

Récapitulatif des fonctionnalités par type de contrat et rôle utilisateur :

| Fonctionnalité                             | Acheteur (marchés) | OE (marchés) | Autorité concédante | OE (concessions) |
| ------------------------------------------ | :----------------: | :----------: | :-----------------: | :--------------: |
| Authentification                           |         x          |      x       |          x          |        x         |
| Publication d'avis                         |         x          |              |                     |                  |
| Mise à disposition DCE                     |         x          |              |          x          |                  |
| Consultation/téléchargement DCE            |                    |      x       |                     |        x         |
| Réception candidatures                     |         x          |              |          x          |                  |
| Dépôt candidature (dont DUME)              |                    |      x       |                     |        x         |
| Réception offres                           |         x          |              |          x          |                  |
| Dépôt offres (dont signature électronique) |                    |      x       |                     |        x         |
| Données essentielles (saisie/import)       |         x          |              |          x          |                  |
| Données essentielles (consultation)        |                    |      x       |                     |        x         |
| Courrier électronique                      |         x          |              |                     |                  |
| Historique/traçabilité                     |         x          |              |          x          |                  |
| Réponse aux questions                      |         x          |              |                     |                  |
| Questions à l'acheteur                     |                    |      x       |                     |                  |
| Justificatifs via autres administrations   |         x          |              |                     |                  |
| Prérequis techniques                       |                    |      x       |                     |        x         |
| Test de configuration                      |                    |      x       |                     |        x         |
| Recherche                                  |                    |      x       |                     |        x         |
| Simulation de dépôt                        |                    |      x       |                     |        x         |
| Assistance/support                         |                    |      x       |                     |        x         |
