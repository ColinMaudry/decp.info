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
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
    script = build_tracker_script()
    assert "trackPageView" in script
    assert "<script" in script and "</script>" in script


def test_script_vide_si_config_incomplete(monkeypatch):
    """La garde passe mais l'URL manque : pas de script muet à moitié valide."""
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.delenv("MATOMO_URL", raising=False)
    monkeypatch.setenv("MATOMO_SITE_ID", "14")
    assert build_tracker_script() == ""


def test_script_utilise_les_variables_d_environnement(monkeypatch):
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")

    script = build_tracker_script()

    assert "https://matomo.example/" in script
    assert '"42"' in script
    # Les anciennes constantes ont disparu du fragment.
    assert "analytics.maudry.com" not in script
    assert "'14'" not in script


def test_script_vide_en_development(monkeypatch):
    """Régression : test.colibre.fr ne doit rien émettre vers le site prod."""
    from src.utils.matomo import build_tracker_script

    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
    assert build_tracker_script() == ""


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
    env = {
        **os.environ,
        "MATOMO_TRACKING_ENABLED": "true",
        "DEVELOPMENT": "false",
        "MATOMO_URL": "https://matomo.example/matomo.php",
        "MATOMO_SITE_ID": "42",
    }
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


def test_avertissement_emis_au_demarrage_apres_load_dotenv():
    """Régression : `avertir_si_config_incomplete()` s'exécutait à l'import de
    `src.utils.matomo` (src/app.py:45, ex ligne 66 de matomo.py), avant le
    `load_dotenv()` de `src/app.py:47`. `tracking_enabled()` lisait alors un
    environnement sans les variables du `.env`, valait donc `False`, et la
    garde se taisait — y compris quand la configuration réelle, une fois le
    `.env` chargé, était incomplète.

    Passer les variables directement dans l'environnement du sous-processus
    ne suffit pas à exercer ce bug : elles seraient déjà lisibles avant même
    l'import de `src.app`, masquant l'ordre d'import fautif. Il faut qu'elles
    n'arrivent QUE via `load_dotenv()`, donc on les dépose dans un `.env`
    temporaire à la racine du dépôt (le seul que `find_dotenv()` trouvera,
    avant tout `.env` d'un dépôt parent) et on les retire explicitement de
    l'environnement transmis au sous-processus.
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    env_file = repo_root / ".env"
    assert not env_file.exists(), "un .env existe déjà à la racine du dépôt"
    env_file.write_text(
        "MATOMO_TRACKING_ENABLED=true\nDEVELOPMENT=false\nMATOMO_SITE_ID=42\n"
    )
    try:
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "MATOMO_TRACKING_ENABLED",
                "DEVELOPMENT",
                "MATOMO_URL",
                "MATOMO_SITE_ID",
            }
        }
        resultat = subprocess.run(
            [sys.executable, "-c", "import src.app"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        env_file.unlink()
    assert resultat.returncode == 0, resultat.stderr
    assert "Matomo" in resultat.stderr
    assert "MATOMO_URL" in resultat.stderr


def test_tracking_enabled_faux_en_development(monkeypatch):
    """Protection de test.colibre.fr : DEVELOPMENT prime sur le drapeau."""
    from src.utils.matomo import tracking_enabled

    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    assert tracking_enabled() is False


def test_tracking_enabled_faux_sans_drapeau(monkeypatch):
    from src.utils.matomo import tracking_enabled

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.delenv("MATOMO_TRACKING_ENABLED", raising=False)
    assert tracking_enabled() is False


def test_tracking_enabled_vrai_hors_development(monkeypatch):
    from src.utils.matomo import tracking_enabled

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    assert tracking_enabled() is True


def test_matomo_config_none_si_incomplete(monkeypatch):
    from src.utils.matomo import matomo_config

    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.delenv("MATOMO_SITE_ID", raising=False)
    assert matomo_config() is None


def test_matomo_config_retourne_le_couple(monkeypatch):
    from src.utils.matomo import matomo_config

    monkeypatch.setenv("MATOMO_URL", "https://matomo.example/matomo.php")
    monkeypatch.setenv("MATOMO_SITE_ID", "42")
    assert matomo_config() == ("https://matomo.example/matomo.php", "42")


def test_avertissement_si_active_mais_incomplet(monkeypatch, caplog):
    import logging

    from src.utils.matomo import avertir_si_config_incomplete

    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("MATOMO_TRACKING_ENABLED", "true")
    monkeypatch.delenv("MATOMO_URL", raising=False)
    monkeypatch.setenv("MATOMO_SITE_ID", "14")

    with caplog.at_level(logging.WARNING, logger="colibre"):
        avertir_si_config_incomplete()

    assert "MATOMO_URL" in caplog.text
    assert "MATOMO_SITE_ID" not in caplog.text


def test_pas_d_avertissement_si_suivi_desactive(monkeypatch, caplog):
    import logging

    from src.utils.matomo import avertir_si_config_incomplete

    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.delenv("MATOMO_URL", raising=False)

    with caplog.at_level(logging.WARNING, logger="colibre"):
        avertir_si_config_incomplete()

    assert caplog.text == ""
