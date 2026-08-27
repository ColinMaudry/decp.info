"""Le cache de l'Annuaire protège une API publique à quota par IP.

Sans lui, faire crawler les 242 005 fiches organisme enverrait autant
d'appels à recherche-entreprises.api.gouv.fr : Googlebot exécute le JS, donc
déclenche le callback qui interroge l'Annuaire.

Deux durées de vie y cohabitent : une réponse valide (fiche trouvée comme
SIRET inconnu) est stable et tient 30 jours, un échec technique ne dit rien de
durable sur le SIRET et ne doit pas condamner la fiche à rester vide un mois.
"""

import json

import httpx
import pytest


class _Reponse:
    def __init__(self, payload=None, json_invalide=False):
        self._payload = payload
        self._json_invalide = json_invalide

    def raise_for_status(self):
        return self

    def json(self):
        if self._json_invalide:
            raise json.JSONDecodeError("attendu une valeur", "<html>", 0)
        return self._payload


@pytest.fixture
def appels(monkeypatch):
    """Remplace l'appel HTTP, compte les invocations, et purge la clé visée.

    Le cache de test (pyproject.toml : CACHE_DIR=tests/cache) est un
    FileSystemCache persistant sur disque : une entrée laissée par un run
    précédent survivrait à celui-ci (timeout de 30 jours) et ferait passer les
    tests à zéro appel réseau, en silence.
    """
    from src.app import app  # noqa: F401  (initialise le cache)
    from src.utils import data
    from src.utils.cache import cache

    faits = []

    def _installer(siret, reponse):
        cache.delete(f"annuaire:{siret}")

        def _get(url, *args, **kwargs):
            faits.append(url)
            if isinstance(reponse, Exception):
                raise reponse
            return reponse

        monkeypatch.setattr(data, "get", _get)
        return faits

    return _installer


@pytest.fixture
def timeouts_poses(monkeypatch):
    """Relève les durées de vie passées à cache.set."""
    from src.app import app  # noqa: F401  (initialise le cache)
    from src.utils.cache import cache

    poses = []
    vrai_set = cache.set

    def _set(key, value, timeout=None):
        poses.append(timeout)
        return vrai_set(key, value, timeout=timeout)

    monkeypatch.setattr(cache, "set", _set)
    return poses


_ETABLISSEMENT = {
    "nom_raison_sociale": "COMMUNE DE RENNES",
    "matching_etablissements": [
        {"code_postal": "35000", "libelle_commune": "RENNES", "adresse": "1 rue x"}
    ],
}


def test_appels_repetes_ne_declenchent_qu_une_requete(appels):
    from src.utils.data import get_annuaire_data

    siret = "99999999999999"
    faits = appels(siret, _Reponse({"results": [_ETABLISSEMENT]}))

    assert get_annuaire_data(siret) == _ETABLISSEMENT
    assert get_annuaire_data(siret) == _ETABLISSEMENT
    assert len(faits) == 1


def test_succes_memorise_trente_jours(appels, timeouts_poses):
    from src.utils.data import ANNUAIRE_TTL_SUCCES, get_annuaire_data

    siret = "99999999999998"
    appels(siret, _Reponse({"results": [_ETABLISSEMENT]}))
    get_annuaire_data(siret)

    assert timeouts_poses == [ANNUAIRE_TTL_SUCCES]


def test_siret_absent_de_l_annuaire_memorise_trente_jours(appels, timeouts_poses):
    """Réponse valide sans résultat : information stable, pas un échec."""
    from src.utils.data import ANNUAIRE_TTL_SUCCES, get_annuaire_data

    siret = "99999999999997"
    appels(siret, _Reponse({"results": []}))

    assert get_annuaire_data(siret) is None
    assert timeouts_poses == [ANNUAIRE_TTL_SUCCES]


def test_echec_technique_memorise_quinze_minutes(appels, timeouts_poses):
    from src.utils.data import ANNUAIRE_TTL_ECHEC, get_annuaire_data

    siret = "99999999999996"
    appels(siret, httpx.ConnectError("injoignable"))

    assert get_annuaire_data(siret) is None
    assert timeouts_poses == [ANNUAIRE_TTL_ECHEC]


def test_echec_technique_n_est_pas_retente_a_chaque_page(appels):
    """Sous rate-limit, retenter à chaque page vue entretiendrait le 429."""
    from src.utils.data import get_annuaire_data

    siret = "99999999999995"
    faits = appels(siret, httpx.ConnectError("injoignable"))

    get_annuaire_data(siret)
    get_annuaire_data(siret)

    assert len(faits) == 1


def test_reponse_sans_clef_results_ne_leve_pas(appels):
    from src.utils.data import get_annuaire_data

    siret = "99999999999994"
    appels(siret, _Reponse({"erreur": "quota dépassé"}))

    assert get_annuaire_data(siret) is None


def test_corps_non_json_ne_leve_pas(appels, timeouts_poses):
    from src.utils.data import ANNUAIRE_TTL_ECHEC, get_annuaire_data

    siret = "99999999999993"
    appels(siret, _Reponse(json_invalide=True))

    assert get_annuaire_data(siret) is None
    assert timeouts_poses == [ANNUAIRE_TTL_ECHEC]


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
