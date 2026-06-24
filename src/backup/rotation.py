from collections.abc import Iterable
from datetime import datetime, timedelta

# (période, horizon) pour les paliers à période fixe
_FIXED_TIERS = (
    (timedelta(hours=1), timedelta(hours=12)),  # horaire / 12 h
    (timedelta(hours=12), timedelta(hours=72)),  # 12 h / 72 h
    (timedelta(days=1), timedelta(days=21)),  # quotidien / 21 j
)
_MONTHLY_HORIZON = 12  # mois calendaires


def _select_fixed(timestamps, now, period, horizon):
    cutoff = now - horizon
    buckets: dict[int, datetime] = {}
    for t in timestamps:
        if t > now or t < cutoff:
            continue
        idx = int((now - t) // period)
        if idx not in buckets or t > buckets[idx]:
            buckets[idx] = t
    return set(buckets.values())


def _month_index(d: datetime) -> int:
    return d.year * 12 + (d.month - 1)


def _select_monthly(timestamps, now):
    now_idx = _month_index(now)
    buckets: dict[int, datetime] = {}
    for t in timestamps:
        if t > now:
            continue
        idx = _month_index(t)
        if idx > now_idx or now_idx - idx >= _MONTHLY_HORIZON:
            continue
        if idx not in buckets or t > buckets[idx]:
            buckets[idx] = t
    return set(buckets.values())


def select_retained(timestamps: Iterable[datetime], now: datetime) -> set[datetime]:
    items = list(timestamps)
    retained: set[datetime] = set()
    for period, horizon in _FIXED_TIERS:
        retained |= _select_fixed(items, now, period, horizon)
    retained |= _select_monthly(items, now)
    return retained
