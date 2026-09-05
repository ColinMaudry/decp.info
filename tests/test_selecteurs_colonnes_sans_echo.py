"""Le liage store ⇄ cases sur les autres sélecteurs de colonnes (#139).

Aucune de ces trois pages n'a aujourd'hui de second écrivain de son store, donc
l'écho n'y écrase rien — le bug de #139 ne les touche pas. Mais il part quand
même à chaque chargement : un aller-retour serveur pour rien, et la course
réapparaîtrait le jour où un second écrivain serait ajouté (des vues
sauvegardées étendues à /acheteur, par exemple).

Comme pour le Tableau, les cases ne sont plus alimentées que par l'ouverture de
leur modale.
"""

from pathlib import Path

import pytest

# (module, id des cases, id de la modale, id du store)
SELECTEURS = [
    ("acheteur", "acheteur_column_list", "acheteur_columns", "acheteur-hidden-columns"),
    (
        "titulaire",
        "titulaire_column_list",
        "titulaire_columns",
        "titulaire-hidden-columns",
    ),
    (
        "observatoire",
        "observatoire_preview_column_list",
        "observatoire-preview-columns-modal",
        "observatoire-hidden-columns",
    ),
]


def _declaration(module: str, cases: str) -> str:
    """Le bloc @callback qui produit `<cases>.selected_rows`.

    Lu dans la source plutôt que dans dash._callback.GLOBAL_CALLBACK_MAP :
    cette table est un état global que d'autres tests vident en cours de
    session.
    """
    source = Path(f"src/pages/{module}.py").read_text()
    sortie = f'Output("{cases}", "selected_rows")'
    debut = source.rindex("@callback", 0, source.index(sortie))
    return source[debut : source.index("def ", debut)]


@pytest.mark.parametrize("module,cases,modale,store", SELECTEURS)
def test_les_cases_sont_alimentees_par_la_modale(module, cases, modale, store):
    assert f'Input("{modale}", "is_open")' in _declaration(module, cases)


@pytest.mark.parametrize("module,cases,modale,store", SELECTEURS)
def test_aucun_declencheur_permanent(module, cases, modale, store):
    """Ni le store, ni le miroir de ses colonnes masquées sur la table, ne
    doivent déclencher les cases : c'est ce qui crée l'écho au chargement."""
    declaration = _declaration(module, cases)

    assert f'Input("{store}", "data")' not in declaration
    assert '"hidden_columns"' not in declaration
