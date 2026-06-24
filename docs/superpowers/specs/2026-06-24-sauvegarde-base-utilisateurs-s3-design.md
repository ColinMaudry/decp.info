# Sauvegarde de la base utilisateurs sur S3 — conception

Date : 2026-06-24
Statut : conception validée, prête pour le plan d'implémentation

## Contexte et objectif

`users.sqlite` contient les comptes utilisateurs (`src/auth/db.py`) **et** les tokens API
(`src/api/tokens_db.py`) — un seul fichier SQLite, ~36 Ko aujourd'hui, attendu jusqu'à
~500 utilisateurs × quelques centaines de lignes. C'est la seule donnée non reproductible
du projet (la base DECP en Parquet/DuckDB est régénérable, donc hors périmètre).

L'app tourne sur un VPS unique (systemd + gunicorn, `/var/www/<APP_NAME>`). On veut prévenir
toute perte de données par des sauvegardes régulières vers un **stockage compatible S3
(non-Amazon)**, avec rotation multi-paliers et un mécanisme de restauration.

## Décisions validées

- **Déclencheur** : timer systemd sur le VPS (indépendant de gunicorn, robuste aux
  redémarrages, pas de duplication entre workers).
- **Chiffrement** : les sauvegardes sont chiffrées côté application _avant_ l'envoi
  (données personnelles : emails, hash de mots de passe, tokens).
- **Périmètre** : le seul fichier `users.sqlite` (chemin `USERS_DB_PATH`).

## Vue d'ensemble

Un nouveau module `src/backup/` expose une CLI à trois sous-commandes : `backup`, `list`,
`restore`. Le timer systemd lance `backup` toutes les heures. Chaque exécution :

1. produit un **snapshot cohérent** de `users.sqlite` (API de backup en ligne de SQLite,
   sûre même en cas d'écriture concurrente) ;
2. le **compresse** (gzip) puis le **chiffre** ;
3. l'**envoie** sur le S3 sous une clé horodatée ;
4. applique la **rotation** : recalcule l'ensemble à conserver et supprime les obsolètes.

## Schéma de rétention

Union de quatre paliers — une sauvegarde est conservée si elle qualifie pour _au moins un_
palier :

| Palier       | Granularité           | Horizon             | ~ Nb gardés |
| ------------ | --------------------- | ------------------- | ----------- |
| Horaire      | 1 par heure           | 12 dernières heures | ~12         |
| Bi-quotidien | 1 par tranche de 12 h | 72 dernières heures | ~6          |
| Quotidien    | 1 par jour            | 21 derniers jours   | ~21         |
| Mensuel      | 1 par mois calendaire | 12 derniers mois    | ~12         |

Soit ~51 fichiers au régime permanent, chacun de quelques dizaines de Ko → stockage
négligeable.

### Algorithme — fonction pure

`select_retained(timestamps: list[datetime], now: datetime) -> set[datetime]` :

- Pour chaque palier à période fixe (horaire, bi-quotidien, quotidien) : regrouper les
  horodatages par tranche (`floor((now - t) / période)`), et pour chaque tranche comprise
  dans l'horizon, garder le **plus récent** de la tranche.
- Pour le palier mensuel : regrouper par **mois calendaire** (`(année, mois)`) car les mois
  ont des durées variables ; garder le plus récent de chaque mois sur les 12 derniers mois.
- Le résultat est l'**union** des ensembles retenus de tous les paliers.
- L'ensemble à supprimer = tous les horodatages présents − ensemble retenu.

Aucune I/O dans cette fonction : elle prend la liste des horodatages (extraits des clés S3)
et `now`, et renvoie quoi garder. Testée unitairement de façon exhaustive (chevauchements
de paliers, bascules d'horizon, mois variables, ensemble vide).

## Modules (`src/backup/`)

Chaque module a une responsabilité unique et une interface explicite, testable isolément.

- **`rotation.py`** — `select_retained` (fonction pure, pas d'I/O). Cœur logique, tests
  unitaires nombreux.
- **`snapshot.py`** — produit un snapshot SQLite cohérent via l'API de backup en ligne
  (`sqlite3.connect(src).backup(dest)`) vers un fichier temporaire, puis gzip. Renvoie le
  chemin du fichier compressé.
- **`crypto.py`** — chiffrement/déchiffrement symétrique authentifié (Fernet, lib
  `cryptography`). Clé lue depuis `BACKUP_ENCRYPTION_KEY`. Round-trip testé.
- **`storage.py`** — wrapper S3 (`upload`, `list`, `download`, `delete`) via `boto3` avec
  `endpoint_url` (compatible tout fournisseur S3 non-Amazon). Configuration lue depuis l'env.
- **`cli.py`** — `argparse` : `backup`, `list`, `restore`. Point d'entrée appelé par le timer
  systemd et par l'opérateur pour la restauration.

### Nommage des objets S3

Clé : `<S3_BACKUP_PREFIX>/users-<YYYYMMDDTHHMMSSZ>.sqlite.gz.enc`, horodatage UTC ISO 8601
compact, triable lexicographiquement. La rotation extrait l'horodatage depuis la clé.

## Procédure de sauvegarde (`backup`)

1. Snapshot cohérent de `users.sqlite` → fichier temporaire.
2. gzip.
3. Chiffrement Fernet.
4. Upload sur S3 sous la clé horodatée.
5. Rotation : lister les clés sous le préfixe, parser les horodatages, calculer l'ensemble
   retenu via `select_retained`, supprimer le reste.
6. Nettoyage des fichiers temporaires (y compris en cas d'erreur).

Journalisation de chaque étape (succès/échec, clés uploadées/supprimées) pour suivi dans
les logs systemd.

## Procédure de restauration (`restore`, manuelle, avec garde-fous)

- `list` → affiche les sauvegardes disponibles (clé, date, taille), triées.
- `restore <clé>` :
  1. télécharge l'objet ;
  2. déchiffre puis décompresse vers un fichier temporaire ;
  3. **vérifie l'intégrité** SQLite (`PRAGMA integrity_check`) — refuse de restaurer si KO ;
  4. fait une **copie de secours** de la base courante (`users.sqlite.bak-<ts>`) ;
  5. remplace de façon atomique (`os.replace`).
- Le script avertit d'**arrêter le service** (`systemctl stop <APP_NAME>`) avant la
  restauration et de le redémarrer après.

La restauration est volontairement **manuelle** : un outil de reprise sur sinistre ne doit
jamais restaurer automatiquement.

## Déploiement et configuration

- Unités systemd dans `deploy/` :
  - `decpinfo-backup.service` (type `oneshot`, exécute `python -m src.backup backup`) ;
  - `decpinfo-backup.timer` (`OnCalendar=hourly`, `Persistent=true` pour rattraper un
    créneau manqué après un redémarrage).
- Nouvelles variables dans `.template.env` :
  - `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
    `S3_BACKUP_PREFIX`, `BACKUP_ENCRYPTION_KEY`.
- Nouvelles dépendances : `boto3`, `cryptography`.
- **Gestion de la clé de chiffrement** : `BACKUP_ENCRYPTION_KEY` doit être sauvegardée
  hors du serveur (gestionnaire de secrets / coffre). Si elle est perdue, les sauvegardes
  sont irrécupérables.

## Tests

- **Unitaires** : `select_retained` (chevauchements, horizons, mois variables, vide) ;
  round-trip `crypto` ; nommage/parsing des clés.
- **Intégration** : snapshot d'une base SQLite réelle → vérifie une base valide ;
  cycle complet backup → list → restore sur un faux backend S3 (mock `boto3` ou `moto`),
  vérifie l'égalité du contenu restauré et la copie de secours créée.

## Hors périmètre

- Sauvegarde de la base DECP (régénérable).
- Restauration automatique / orchestration multi-serveurs.
- Réplication temps réel.
