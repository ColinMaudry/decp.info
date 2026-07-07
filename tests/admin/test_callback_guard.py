"""Régression issue #110 : le callback admin est un endpoint serveur global
(/_dash-update-component), invocable indépendamment du layout. Il DOIT revérifier
is_admin() lui-même, sinon un non-admin (voire un anonyme) lit/écrit toute la base.

Ces tests appellent le callback directement (sans navigateur) : la garde s'exécute
avant tout accès au `ctx`/à la base, donc un non-admin ne doit rien pouvoir faire.
"""

import pytest
from dash.exceptions import PreventUpdate

import src.app  # noqa: F401  # instancie l'app → register_page() des pages
from src.pages.admin import liste


def test_update_table_read_path_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(liste, "is_admin", lambda: False)
    # Chemin lecture (sélection d'une table) : ne doit RIEN renvoyer.
    with pytest.raises(PreventUpdate):
        liste._update_table("users", [], None)


def test_update_table_write_path_rejects_non_admin(monkeypatch):
    monkeypatch.setattr(liste, "is_admin", lambda: False)
    # Chemin écriture (édition de cellule simulée) : ne doit RIEN modifier.
    data = [{"id": 1, "email": "a@b.fr"}]
    data_previous = [{"id": 1, "email": "victime@b.fr"}]
    with pytest.raises(PreventUpdate):
        liste._update_table("users", data, data_previous)


def test_update_table_allows_admin(monkeypatch):
    # Avec is_admin() vrai, la garde ne bloque pas : sans changement de cellule
    # détecté, le callback renvoie 4 valeurs (pas de PreventUpdate).
    monkeypatch.setattr(liste, "is_admin", lambda: True)

    class _Ctx:
        triggered_id = "autre-composant"

    monkeypatch.setattr(liste, "ctx", _Ctx)
    result = liste._update_table("users", None, None)
    assert len(result) == 4
