"""L'asset est servi automatiquement par Dash (tout .js de src/assets/)."""

import re
from pathlib import Path

ASSET = Path(__file__).resolve().parents[1] / "src" / "assets" / "goals.js"


def _code_sans_commentaires() -> str:
    """Le source privé de ses commentaires `//`.

    Sans ce dépouillement, les assertions ci-dessous passeraient alors même que
    les littéraux n'apparaîtraient que dans un commentaire — elles vérifieraient
    la présence de texte, pas l'existence d'une logique.
    """
    lignes = ASSET.read_text(encoding="utf-8").splitlines()
    return "\n".join(re.sub(r"//.*$", "", ligne) for ligne in lignes)


def test_asset_present():
    assert ASSET.is_file()


def test_valide_les_valeurs_avant_emission():
    """Une valeur arbitraire de query string ne doit pas atterrir dans Matomo."""
    code = _code_sans_commentaires()
    assert re.search(r'METHODES\s*=\s*\[\s*"email"\s*,\s*"linkedin"\s*\]', code)
    assert re.search(r'PLANS\s*=\s*\[\s*"simple"\s*,\s*"soutien"\s*\]', code)


def test_garde_sur_paq_et_nettoyage_de_l_url():
    """`"window._paq" in code` est aussi satisfait par l'appel
    `window._paq.push(...)` lui-même : une régression qui supprimerait
    entièrement `if (!window._paq) return;` (un TypeError garanti à chaque
    page chargée traqueur désactivé) laisserait quand même passer cette
    assertion. On pin donc la garde par une regex sur sa forme précise, comme
    déjà fait pour METHODES/PLANS ci-dessus.
    """
    code = _code_sans_commentaires()
    assert re.search(r"if\s*\(\s*!\s*window\._paq\s*\)\s*return", code)
    # Sans replaceState, un F5 recompterait la conversion.
    assert "replaceState" in code


def test_emet_les_deux_evenements():
    code = _code_sans_commentaires()
    assert "account_created" in code
    assert "subscription_trial" in code
