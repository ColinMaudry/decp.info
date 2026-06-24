from datetime import datetime, timezone

import pytest

from src.backup.naming import make_key, parse_timestamp


def test_make_key_format():
    ts = datetime(2026, 6, 24, 14, 5, 9, tzinfo=timezone.utc)
    assert make_key("backups", ts) == "backups/users-20260624T140509Z.sqlite.gz.enc"


def test_make_key_strips_trailing_slash():
    ts = datetime(2026, 6, 24, 14, 5, 9, tzinfo=timezone.utc)
    assert make_key("backups/", ts).startswith("backups/users-")


def test_roundtrip():
    ts = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert parse_timestamp(make_key("p", ts)) == ts


def test_parse_rejects_unknown_key():
    with pytest.raises(ValueError):
        parse_timestamp("backups/users.sqlite.bak")
