"""L'asset est servi automatiquement par Dash (tout .js de src/assets/)."""

from pathlib import Path

ASSET = Path(__file__).resolve().parents[1] / "src" / "assets" / "goals.js"


def test_asset_present():
    assert ASSET.is_file()


def test_valide_les_valeurs_avant_emission():
    """Une valeur arbitraire de query string ne doit pas atterrir dans Matomo."""
    contenu = ASSET.read_text(encoding="utf-8")
    assert '"email"' in contenu and '"linkedin"' in contenu
    assert '"simple"' in contenu and '"soutien"' in contenu


def test_garde_sur_paq_et_nettoyage_de_l_url():
    contenu = ASSET.read_text(encoding="utf-8")
    assert "window._paq" in contenu
    # Sans replaceState, un F5 recompterait la conversion.
    assert "replaceState" in contenu


def test_emet_les_deux_evenements():
    contenu = ASSET.read_text(encoding="utf-8")
    assert "account_created" in contenu
    assert "subscription_trial" in contenu
