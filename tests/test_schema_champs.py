"""Liste des champs publiés affichée dans /projet/donnees (issue #136)."""

import pytest

from src.figures import make_schema_grid
from src.utils.data import DATA_SCHEMA, field_type_label, schema_field_rows
from tests.helpers import walk_components


@pytest.mark.parametrize(
    ("type_tableschema", "libelle"),
    [
        ("string", "Chaîne de caractères"),
        ("number", "Nombre décimal"),
        ("integer", "Nombre entier"),
        ("boolean", "Booléen (oui/non)"),
        ("date", "Date"),
        ("datetime", "Date et heure"),
        ("time", "Heure"),
        ("year", "Année"),
    ],
)
def test_field_type_label_traduit_les_types_tableschema(type_tableschema, libelle):
    assert field_type_label({"type": type_tableschema}) == libelle


def test_field_type_label_string_uri_donne_url():
    assert field_type_label({"type": "string", "format": "uri"}) == "URL"


def test_field_type_label_type_inconnu_replie_sur_le_type_brut():
    assert field_type_label({"type": "geopoint"}) == "geopoint"


def test_schema_field_rows_exclut_la_colonne_loupe_marche():
    assert "marche" not in {row["champ"] for row in schema_field_rows()}


def test_schema_field_rows_couvre_le_schema_dans_son_ordre():
    attendus = [nom for nom in DATA_SCHEMA if nom != "marche"]
    assert [row["champ"] for row in schema_field_rows()] == attendus


def test_schema_field_rows_nom_porte_l_ancre_le_titre_gras_et_le_champ():
    ligne = next(
        row for row in schema_field_rows() if row["champ"] == "acheteur_categorie"
    )
    assert ligne["nom"] == (
        '<span id="acheteur_categorie"></span>'
        "**Catégorie de l'acheteur** (acheteur_categorie)"
    )


def test_schema_field_rows_reprend_description_et_type():
    ligne = next(row for row in schema_field_rows() if row["champ"] == "montant")
    assert ligne["description"] == DATA_SCHEMA["montant"]["description"]
    assert ligne["type"] == "Nombre décimal"


def test_make_schema_grid_expose_nom_type_description_en_markdown():
    grid = make_schema_grid()
    champs = [col["field"] for col in grid.columnDefs]
    assert champs == ["nom", "type", "description"]
    assert grid.columnDefs[0]["cellRenderer"] == "markdown"
    assert grid.dangerously_allow_code is True


def test_make_schema_grid_rend_toutes_les_lignes_pour_les_ancres():
    grid = make_schema_grid()
    assert grid.rowData == schema_field_rows()
    assert grid.dashGridOptions["domLayout"] == "autoHeight"


def _layout_donnees():
    from src.app import app  # noqa: F401
    from src.pages.projet import donnees as page

    return list(walk_components(page.layout()))


def test_page_donnees_expose_la_section_liste_des_champs():
    noeuds = _layout_donnees()
    titres = [
        n
        for n in noeuds
        if type(n).__name__ == "H2" and getattr(n, "id", None) == "champs"
    ]
    assert len(titres) == 1
    assert titres[0].children == "Liste des champs"
    assert any(getattr(n, "id", None) == "schema_champs_grid" for n in noeuds)


def test_page_donnees_explique_l_absence_de_donnees_actuelles():
    textes = [n.children for n in _layout_donnees() if type(n).__name__ == "Markdown"]
    paragraphe = next(
        t for t in textes if "publiés en Open Data et accessibles via l'API" in t
    )
    assert "**Données actuelles**" in paragraphe
    assert 'donneesActuelles = "oui"' in paragraphe


def test_page_donnees_place_les_champs_avant_les_sources():
    titres = [
        n.id
        for n in _layout_donnees()
        if type(n).__name__ == "H2" and getattr(n, "id", None)
    ]
    assert titres == ["donnees-brutes", "qualite", "champs", "sources"]
