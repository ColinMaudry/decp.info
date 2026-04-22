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
