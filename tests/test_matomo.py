"""Fragment de suivi Matomo partagé entre les pages Dash et SEO SSR (#128)."""

import os


def test_desactive_par_defaut(monkeypatch):
    """La suite tourne avec MATOMO_TRACKING_ENABLED=false (pyproject.toml)."""
    from src.utils.matomo import build_tracker_script

    monkeypatch.delenv("MATOMO_TRACKING_ENABLED", raising=False)
    assert build_tracker_script() == ""


def test_desactive_explicitement(monkeypatch):
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "false")
    assert build_tracker_script() == ""


def test_active_rend_le_script_trackpageview(monkeypatch):
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    script = build_tracker_script()
    assert "trackPageView" in script
    assert "<script" in script and "</script>" in script


def test_page_dash_emet_le_script_matomo_quand_actif():
    """Régression #128 : avant la factorisation, le <script> Matomo était codé
    en dur dans `app.index_string`, donc toujours émis. La factorisation l'a
    rattaché à `MATOMO_TRACKING_ENABLED` (src/app.py), sans qu'aucun test ne
    couvre ce chemin d'émission navigateur : toute la suite tourne avec
    `MATOMO_TRACKING_ENABLED=false` (pyproject.toml), donc un test qui
    monkeypatcherait seulement `build_tracker_script()` ou la variable
    d'environnement resterait vert même si `src/app.py` faisait
    `matomo_script = ""` en dur — `app.index_string` est composé une seule
    fois, à l'import du module.

    On importe donc `src.app` dans un processus séparé, avec le traqueur
    activé, pour exercer réellement `src/app.py:320` plutôt que de
    réimplémenter sa logique dans le test. Le process séparé évite aussi de
    perturber les autres tests, qui importent déjà `src.app` (mis en cache
    par Python) avec le traqueur désactivé.
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "MATOMO_TRACKING_ENABLED": "true"}
    resultat = subprocess.run(
        [sys.executable, "-c", "from src.app import app; print(app.index_string)"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultat.returncode == 0, resultat.stderr
    assert "trackPageView" in resultat.stdout
    assert "<script" in resultat.stdout
