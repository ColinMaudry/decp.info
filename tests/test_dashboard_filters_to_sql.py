from datetime import datetime, timedelta

from src.utils.table_sql import dashboard_filters_to_sql


def test_no_filters_uses_default_365_day_window():
    where_sql, params = dashboard_filters_to_sql()
    assert where_sql == '"dateNotification" > ?'
    assert len(params) == 1
    assert isinstance(params[0], datetime)
    expected = datetime.now() - timedelta(days=365)
    assert abs((params[0] - expected).total_seconds()) < 2


def test_year_filter_overrides_default_window():
    where_sql, params = dashboard_filters_to_sql(dashboard_year="2025")
    assert where_sql == 'YEAR("dateNotification") = ?'
    assert params == [2025]


def test_marche_type_equality():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_type="Marché",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "type" = ?'
    assert params == [2025, "Marché"]


def test_innovant_value_all_is_skipped():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_innovant="all",
    )
    assert where_sql == 'YEAR("dateNotification") = ?'
    assert params == [2025]


def test_innovant_value_oui_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_innovant="oui",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "marcheInnovant" = ?'
    assert params == [2025, "oui"]


def test_sous_traitance_value_non_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_sous_traitance_declaree="non",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "sousTraitanceDeclaree" = ?'
    assert params == [2025, "non"]


def test_acheteur_id_uses_like_wildcards():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_id="12345678900010",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_id" LIKE ?'
    assert params == [2025, "%12345678900010%"]


def test_titulaire_id_uses_like_wildcards():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_titulaire_id="999",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "titulaire_id" LIKE ?'
    assert params == [2025, "%999%"]


def test_marche_objet_uses_case_insensitive_ilike():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_objet="travaux",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "objet" ILIKE ?'
    assert params == [2025, "%travaux%"]


def test_code_cpv_uses_prefix_like():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_code_cpv="4521",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "codeCPV" LIKE ?'
    assert params == [2025, "4521%"]


def test_acheteur_departement_multiple_uses_in_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_departement_code=["75", "92", "93"],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? AND "acheteur_departement_code" IN (?, ?, ?)'
    )
    assert params == [2025, "75", "92", "93"]


def test_acheteur_categorie_adds_clause():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_categorie="Commune",
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_categorie" = ?'
    assert params == [2025, "Commune"]


def test_titulaire_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_titulaire_categorie="PME",
        dashboard_titulaire_departement_code=["35"],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        'AND "titulaire_categorie" = ? '
        'AND "titulaire_departement_code" IN (?)'
    )
    assert params == [2025, "PME", "35"]


def test_acheteur_id_present_skips_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_acheteur_id="123",
        dashboard_acheteur_categorie="Commune",
        dashboard_acheteur_departement_code=["75"],
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "acheteur_id" LIKE ?'
    assert params == [2025, "%123%"]


def test_titulaire_id_present_skips_categorie_and_departement():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_titulaire_id="999",
        dashboard_titulaire_categorie="PME",
        dashboard_titulaire_departement_code=["35"],
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "titulaire_id" LIKE ?'
    assert params == [2025, "%999%"]


def test_marche_techniques_uses_list_has_any():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_techniques=["Enchère", "Accord-cadre"],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_any(string_split(\"techniques\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Enchère", "Accord-cadre"]]


def test_considerations_sociales_uses_list_has_any():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_considerations_sociales=["Clause sociale"],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_any(string_split(\"considerationsSociales\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Clause sociale"]]


def test_considerations_environnementales_uses_list_has_any():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_marche_considerations_environnementales=["Clause env."],
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? '
        "AND list_has_any(string_split(\"considerationsEnvironnementales\", ', '), ?::VARCHAR[])"
    )
    assert params == [2025, ["Clause env."]]


def test_montant_min_only():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_min=1000,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant" >= ?'
    assert params == [2025, 1000]


def test_montant_max_only():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_max=500,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant" <= ?'
    assert params == [2025, 500]


def test_montant_zero_is_a_valid_lower_bound():
    # 0 est falsy mais reste un filtre valide (distinct de None)
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_min=0,
    )
    assert where_sql == 'YEAR("dateNotification") = ? AND "montant" >= ?'
    assert params == [2025, 0]


def test_montant_min_and_max_combined():
    where_sql, params = dashboard_filters_to_sql(
        dashboard_year="2025",
        dashboard_montant_min=100,
        dashboard_montant_max=1000,
    )
    assert where_sql == (
        'YEAR("dateNotification") = ? AND "montant" >= ? AND "montant" <= ?'
    )
    assert params == [2025, 100, 1000]
