from datetime import datetime, timedelta, timezone

from src.backup.rotation import select_retained

NOW = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_most_recent_always_kept():
    ts = [NOW, NOW - timedelta(hours=2)]
    assert NOW in select_retained(ts, NOW)


def test_recent_hours_kept_by_hourly_tier():
    t = NOW - timedelta(hours=3)
    assert t in select_retained([t], NOW)


def test_two_backups_same_hour_keep_newest():
    older = NOW - timedelta(hours=2, minutes=50)
    newer = NOW - timedelta(hours=2, minutes=10)
    retained = select_retained([older, newer], NOW)
    assert newer in retained
    assert older not in retained


def test_daily_tier_keeps_old_daily_backup():
    t = NOW - timedelta(days=10)
    assert t in select_retained([t], NOW)


def test_monthly_tier_keeps_one_per_calendar_month():
    older = NOW - timedelta(days=40)  # mois M-2 ou M-1 selon calendrier
    same_month_newer = older + timedelta(days=2)
    retained = select_retained([older, same_month_newer], NOW)
    # même mois calendaire -> seul le plus récent du mois est conservé
    assert same_month_newer in retained
    assert older not in retained


def test_keeps_backup_within_12_months():
    t = NOW - timedelta(days=300)
    assert t in select_retained([t], NOW)


def test_drops_backup_older_than_12_months():
    t = NOW - timedelta(days=400)
    assert t not in select_retained([t], NOW)


def test_future_timestamps_ignored():
    t = NOW + timedelta(hours=1)
    assert t not in select_retained([t], NOW)
