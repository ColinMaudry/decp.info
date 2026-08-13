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


def test_subscription_trial_reagit_au_parametre_essai_pas_a_souscription_plan():
    """Depuis que l'essai ne passe plus par un checkout Frisbii, il n'y a
    plus de retour de paiement portant `souscription=trial&plan=...` : le
    déclencheur est désormais `essai=demarre`, posé par src/auth/routes.py
    à l'ouverture effective de l'essai (vérification d'email, inscription
    LinkedIn)."""
    code = _code_sans_commentaires()
    assert re.search(r'params\.get\(\s*"essai"\s*\)\s*===\s*"demarre"', code)
    assert 'params.get("souscription")' not in code
    assert 'params.get("plan")' not in code


def test_subscription_trial_retire_essai_de_l_url_apres_emission():
    """Sans ce nettoyage, un F5 après le démarrage de l'essai recompterait
    la conversion — même garde anti-recomptage que pour `compte_cree`."""
    code = _code_sans_commentaires()
    assert re.search(r'retirerParams\(\s*\[\s*"essai"\s*\]\s*\)', code)


def test_plans_a_disparu_le_bloc_subscription_trial_toujours_present():
    """PLANS n'a plus lieu d'être : l'émission de subscription_trial ne
    dépend plus d'un plan choisi au checkout. On ancre cette absence à une
    preuve positive que l'appel `window._paq.push` du bloc subscription_trial
    existe toujours, sinon un fichier vidé de tout contenu satisferait aussi
    bien l'assertion d'absence."""
    code = _code_sans_commentaires()
    assert re.search(
        r'window\._paq\.push\(\s*\[\s*"trackEvent"\s*,\s*"Abonnement"\s*,\s*"subscription_trial"\s*\]\s*\)',
        code,
    )
    assert "PLANS" not in code
