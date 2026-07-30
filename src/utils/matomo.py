"""Fragment de suivi Matomo, partagé entre les pages Dash (`app.index_string`)
et les pages SEO rendues côté serveur (`src/templates/seo_liste.html`).

Avant cette factorisation, le traqueur ne vivait que dans `app.index_string` :
les ~2 500 pages d'index par département et les listes de marchés (Flask, pas
Dash) en étaient donc dépourvues, y compris `/departements` qui était pourtant
tracké avant l'introduction des pages SEO SSR.

Gardé derrière `MATOMO_TRACKING_ENABLED`, comme le suivi côté API
(`src/api/tracking.py`) : la variable vaut "false" pendant les tests
(pyproject.toml, `[tool.pytest_env]`), donc aucune page de test n'émet ce
script, en dev comme en CI.
"""

import os


def build_tracker_script() -> str:
    """Bloc <script> du traqueur Matomo, ou chaîne vide si désactivé."""
    # `MATOMO_TRACKING_ENABLED` conditionnait à l'origine seulement le suivi
    # SERVEUR de l'API (src/api/tracking.py). Depuis cette factorisation, elle
    # conditionne AUSSI l'émission du traqueur navigateur (ce fragment, injecté
    # dans app.index_string ET dans seo_liste.html). Si `.env` en production
    # ne porte pas `MATOMO_TRACKING_ENABLED=true`, toute l'analytique du site
    # (serveur + navigateur) s'éteint silencieusement — pas seulement l'API.
    if os.getenv("MATOMO_TRACKING_ENABLED", "false").lower() != "true":
        return ""
    return """<script type="application/javascript">
            var _paq = window._paq = window._paq || [];
            /* tracker methods like "setCustomDimension" should be called before "trackPageView" */
            _paq.push(['trackPageView']);
            _paq.push(['enableLinkTracking']);
            (function() {
                var u="//analytics.maudry.com/";
                _paq.push(['setTrackerUrl', u+'matomo.php']);
                _paq.push(['setSiteId', '14']);
                var d=document, g=d.createElement('script'), s=d.getElementsByTagName('script')[0];
                g.async=true; g.src=u+'matomo.js'; s.parentNode.insertBefore(g,s);
            })();
        </script>"""
