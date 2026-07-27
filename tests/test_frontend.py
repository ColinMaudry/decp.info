def test_format_datetime_french_converts_utc_to_paris():
    from src.utils.frontend import format_datetime_french

    # 13h57 UTC un 29 juillet = 15h57 à Paris (UTC+2 en été)
    assert (
        format_datetime_french("2026-07-29T13:57:43.177+00:00")
        == "29 juillet 2026 à 15h57"
    )


def test_format_datetime_french_handles_z_suffix_and_winter_offset():
    from src.utils.frontend import format_datetime_french

    assert format_datetime_french("2026-01-15T09:05:00Z") == "15 janvier 2026 à 10h05"


def test_format_datetime_french_uses_1er():
    from src.utils.frontend import format_datetime_french

    assert format_datetime_french("2026-03-01T00:30:00Z") == "1er mars 2026 à 1h30"


def test_format_datetime_french_passthrough_on_garbage():
    from src.utils.frontend import format_datetime_french

    assert format_datetime_french("pas une date") == "pas une date"
