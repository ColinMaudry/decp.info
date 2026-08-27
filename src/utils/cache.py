import os

from flask_caching import Cache

# Isolé dans un fichier dédié pour éviter les imports circulaires : ce module
# ne dépend que de flask_caching (et de la stdlib), jamais de src.app, afin
# que src.utils.data (importé très tôt, ex. par src.pages.tableau) puisse
# mémoïser ses appels sans jamais avoir à importer src.app.
cache = Cache()


def cache_dir_par_defaut() -> str:
    """Répertoire du cache disque, piloté par CACHE_DIR.

    Lu à la fois par src.app (init du cache) et par le hook `on_starting` de
    gunicorn.conf.py (purge au démarrage du master) : la valeur par défaut est
    définie ici pour n'exister qu'à un seul endroit.
    """
    return os.getenv("CACHE_DIR", "/tmp/colibre-cache")


def cache_threshold_par_defaut() -> int:
    """Seuil du cache, piloté par la variable d'environnement CACHE_THRESHOLD
    (300 000 par défaut).

    flask-caching évince les entrées les plus anciennes (`_prune`) à chaque
    écriture au-delà de ce seuil ; son défaut (300) rendrait inopérante la
    mémoïsation des 242 005 SIRET de l'Annuaire des entreprises — le crawl SEO
    de ce chantier viderait le cache avant même de l'avoir rempli. Mesure
    d'attente : le backend Redis arrive par #123 puis #62, et la bascule se
    fera par CACHE_TYPE sans toucher aux décorateurs @cache.memoize.
    """
    return int(os.getenv("CACHE_THRESHOLD", 300_000))
