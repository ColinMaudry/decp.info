"""Configuration gunicorn de colibre.

Chargée automatiquement par gunicorn quand ce fichier est présent dans le
répertoire de travail ; l'ExecStart se réduit alors à `gunicorn run:server`.

Tout est piloté par variables d'environnement (fournies par `.env` ou par
l'orchestrateur), rien n'est codé en dur, afin que la prod et l'instance de test
partagent le même fichier avec des valeurs distinctes.

Choix de conception :

- `gthread` plutôt que `sync` : le défaut `sync` traite une requête à la fois
  par worker. `get_cursor()` (src/db.py) rend un curseur DuckDB par requête et
  DuckDB relâche le GIL pendant l'exécution, donc les threads apportent une vraie
  concurrence ici.
- Peu de workers, plusieurs threads : chaque worker porte une instance DuckDB
  complète en RAM, alors que les threads la partagent. Le plafond CPU réel d'un
  processus vaut `workers × DUCKDB_THREADS` (voir configure_connection dans
  src/db.py) ; les threads gthread au-delà servent à absorber la concurrence,
  pas à consommer plus de CPU.
- `timeout` généreux : le module src.db reconstruit le DuckDB à l'import. Un
  démarrage à froid dépasse largement le défaut de 30 s, ce qui ferait tuer puis
  redémarrer les workers en boucle sans jamais aboutir.
- Pas de `preload_app` : une connexion DuckDB héritée par fork() n'est pas
  supportée. Chaque worker construit/ouvre sa propre connexion ; le flock de
  _ensure_database sérialise le démarrage.
"""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8050')}"

workers = int(os.getenv("WEB_CONCURRENCY", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "8"))
worker_class = "gthread"

# Doit couvrir la reconstruction du DuckDB au démarrage à froid.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "900"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))

# Recycle les workers pour amortir une éventuelle fuite mémoire au long cours.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "5000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# Logs sur stderr : captés par systemd aujourd'hui, par l'orchestrateur
# de conteneurs demain.
accesslog = None
errorlog = "-"


def on_starting(server):
    """Repart d'un cache disque vide au démarrage du service.

    Appelé une seule fois, par le master, avant le premier fork. La purge
    vivait auparavant au niveau module de src/app.py : faute de `preload_app`,
    chaque worker l'exécutait à son import et détruisait le cache que les
    autres venaient de remplir — donc à chaque recyclage `max_requests`. Le
    TTL de 30 jours de `get_annuaire_data` n'a de sens que depuis ce
    déplacement.
    """
    from shutil import rmtree

    from src.utils.cache import cache_dir_par_defaut

    rmtree(cache_dir_par_defaut(), ignore_errors=True)
