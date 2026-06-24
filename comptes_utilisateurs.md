# Contexte

Je souhate ajouter la possibilité pour les utilisateurs de créer un compte utilisateur. Les données des utilisateurs sont stockés dans une base de données sqlite située à la racine du projet. Les seules données demandées sont une adresse email et un mot de passe. Un lien dans le menu supérieur, tout à droite, permet d'accéder à une page qui permet soit de se connecter, soit de créer un compte.

Il s'agit des fondations des comptes utilisateurs, d'autres fonctionnalités viendront s'ajouter.

# Inscription

Données nécessaires :

- adresse email
- mot de passe

Le mot de passe est hashé en base de données.

# Connexion

- adresse email
- mot passe

Lien vers une page de réinitialisation du mot de passe.

# Page du compte

Possibilité de changer le mot de passe.

# Configuration

Ces fonctionnalités nécessitent d'envoyer des emails. Les options nécessaire à une connexion à un service SMTP sont fournies sous la forme de variables d'environnement.
