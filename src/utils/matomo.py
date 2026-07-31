"""Fragment de suivi Matomo, partagé entre les pages Dash (`app.index_string`)
et les pages SEO rendues côté serveur (`src/templates/seo_liste.html`).

Avant cette factorisation, le traqueur ne vivait que dans `app.index_string` :
les ~2 500 pages d'index par département et les listes de marchés (Flask, pas
Dash) en étaient donc dépourvues, y compris `/departements` qui était pourtant
tracké avant l'introduction des pages SEO SSR.

Gardé derrière `tracking_enabled()`, qui combine `DEVELOPMENT` et
`MATOMO_TRACKING_ENABLED` : cette dernière vaut "false" pendant les tests
(pyproject.toml, `[tool.pytest_env]`), donc aucune page de test n'émet ce
script, en dev comme en CI.
"""

import json
import os

from src.utils import logger


def tracking_enabled() -> bool:
    """Interrupteur unique de tout le suivi Matomo du projet.

    `DEVELOPMENT` prime sur `MATOMO_TRACKING_ENABLED` : c'est ce qui empêche
    test.colibre.fr et les instances de développement d'alimenter le Matomo de
    production, sans dépendre d'un `.env` correctement rempli sur le serveur.

    La lecture se fait à l'appel et non via la constante `DEVELOPMENT` de
    `src/utils/__init__.py:33`, figée au premier import : `pyproject.toml:56`
    pinne `DEVELOPMENT=true` pour toute la suite de tests, donc une garde
    reposant sur la constante rendrait intestable le chemin « traqueur émis
    quand il est activé » — précisément celui que l'incident #128 avait laissé
    passer.
    """
    if os.getenv("DEVELOPMENT", "False").lower() == "true":
        return False
    return os.getenv("MATOMO_TRACKING_ENABLED", "false").lower() == "true"


def matomo_config() -> tuple[str, str] | None:
    """(url de la Tracking API, id du site), ou None si l'un des deux manque."""
    url = os.getenv("MATOMO_URL")
    site_id = os.getenv("MATOMO_SITE_ID")
    if not url or not site_id:
        return None
    return url, site_id


def avertir_si_config_incomplete() -> None:
    """Rend bruyante une configuration Matomo incomplète.

    Le suivi de l'API est resté muet en production pendant des mois parce que
    `MATOMO_URL`/`MATOMO_SITE_ID` manquaient au `.env` et que le code se
    contentait d'un retour anticipé silencieux.
    """
    if not tracking_enabled() or matomo_config() is not None:
        return
    manquantes = [n for n in ("MATOMO_URL", "MATOMO_SITE_ID") if not os.getenv(n)]
    logger.warning(
        "Matomo : suivi activé mais configuration incomplète, variable(s) "
        "manquante(s) : %s. Aucun événement ne sera émis.",
        ", ".join(manquantes),
    )


def build_tracker_script() -> str:
    """Bloc <script> du traqueur Matomo, ou chaîne vide si désactivé."""
    if not tracking_enabled():
        return ""
    config = matomo_config()
    if config is None:
        return ""
    url, site_id = config
    # `MATOMO_URL` pointe la Tracking API (…/matomo.php) ; le loader JS veut la
    # racine, à laquelle il recolle lui-même `matomo.php` et `matomo.js`.
    base = url[: -len("matomo.php")] if url.endswith("matomo.php") else url
    if not base.endswith("/"):
        base += "/"
    # json.dumps plutôt qu'une interpolation : une apostrophe ou un guillemet
    # dans la variable produit un littéral JS valide au lieu de casser le script.
    return """<script type="application/javascript">
            var _paq = window._paq = window._paq || [];
            /* tracker methods like "setCustomDimension" should be called before "trackPageView" */
            _paq.push(['trackPageView']);
            _paq.push(['enableLinkTracking']);
            (function() {
                var u=__BASE__;
                _paq.push(['setTrackerUrl', u+'matomo.php']);
                _paq.push(['setSiteId', __SITE_ID__]);
                var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0];
                g.async=true; g.src=u+'matomo.js'; s.parentNode.insertBefore(g,s);
            })();
        </script>""".replace("__BASE__", json.dumps(base)).replace(
        "__SITE_ID__", json.dumps(site_id)
    )
