"""Le cache de l'Annuaire protège une API publique à quota par IP.

Sans lui, faire crawler les 242 005 fiches organisme enverrait autant
d'appels à recherche-entreprises.api.gouv.fr : Googlebot exécute le JS, donc
déclenche le callback qui interroge l'Annuaire.
"""


def test_appels_repetes_ne_declenchent_qu_une_requete(monkeypatch):
    from src.app import app  # noqa: F401  (initialise le cache)
    from src.utils import data
    from src.utils.cache import cache

    siret = "99999999999999"
    appels = []

    class _Reponse:
        def raise_for_status(self):
            return self

        def json(self):
            return {"results": [{"siret": siret}]}

    def _get(url, **kwargs):
        appels.append(url)
        return _Reponse()

    monkeypatch.setattr(data, "get", _get)
    # `.uncached` n'existe que si @cache.memoize a bien décoré la fonction :
    # cet appel échouerait avec AttributeError si la mémoïsation manquait.
    data.get_annuaire_data.uncached("12345678901234")

    # Le cache de test (pyproject.toml : CACHE_DIR=tests/cache) est un
    # FileSystemCache persistant sur disque. Une entrée mémoïsée pour ce siret
    # lors d'un run précédent de la suite (timeout de 30 jours) survivrait à
    # celui-ci et ferait passer ce test à zéro appel réseau au lieu d'un, en
    # silence. On purge donc explicitement la clé avant de compter.
    cache.delete_memoized(data.get_annuaire_data, siret)
    appels.clear()

    data.get_annuaire_data(siret)
    data.get_annuaire_data(siret)
    assert len(appels) == 1


def test_seuil_de_cache_permet_de_tenir_les_organismes():
    """300 entrées (défaut flask-caching) ne suffisent pas pour 242 005 SIRET :
    vérifie que l'app relève bien le seuil par défaut à 300 000.

    `cache.app.config["CACHE_THRESHOLD"]` ne convient pas ici : Flask-Caching
    ne recopie jamais la config passée à `init_app()` dans `app.config`, donc
    cette clé est absente (KeyError) quelle que soit la valeur réellement
    appliquée. Le seuil effectif ne vit que dans le backend FileSystemCache
    construit par `init_app()`, exposé par la propriété `cache.cache`.
    """
    from src.app import app  # noqa: F401  (initialise le cache)
    from src.utils.cache import cache

    assert cache.cache._threshold >= 300_000


def test_cache_threshold_pilotable_par_variable_environnement(monkeypatch):
    """Relire `cache.app.config["CACHE_THRESHOLD"]` après coup (test ci-dessus)
    ne prouve pas que le seuil est piloté par variable d'environnement : une
    constante figée à 300 000 satisferait tout autant l'assertion, sans
    aucune lecture de variable d'environnement. On teste donc directement, en
    isolation, la fonction qui calcule le seuil — avec et sans la variable
    positionnée."""
    from src.utils.cache import cache_threshold_par_defaut

    monkeypatch.setenv("CACHE_THRESHOLD", "5")
    assert cache_threshold_par_defaut() == 5

    monkeypatch.delenv("CACHE_THRESHOLD", raising=False)
    assert cache_threshold_par_defaut() == 300_000
