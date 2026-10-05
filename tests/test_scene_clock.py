from datetime import datetime, timedelta, timezone

import pytest

from tools.scene_clock import moscow_i_date, parse_clock


def test_moscow_clock_crosses_midnight_independently_of_system_timezone():
    utc = datetime(2026, 10, 5, 23, 58, 12, tzinfo=timezone.utc)
    assert moscow_i_date(utc) == (2026, 10, 6, 2 * 3600 + 58 * 60 + 12)
    other_zone = utc.astimezone(timezone(timedelta(hours=-7)))
    assert moscow_i_date(other_zone) == moscow_i_date(utc)


def test_naive_time_is_not_silently_treated_as_local():
    with pytest.raises(ValueError, match="timezone"):
        moscow_i_date(datetime(2026, 10, 5, 12))


@pytest.mark.parametrize("clock, seconds", [("00:00", 0), ("12:30", 45000), ("23:59:59", 86399)])
def test_fixed_clock_parse(clock, seconds):
    assert parse_clock(clock) == seconds


@pytest.mark.parametrize("clock", ["24:00", "12:60", "01:02:60", "noon", "-1:00"])
def test_invalid_fixed_clock_rejected(clock):
    with pytest.raises(ValueError):
        parse_clock(clock)
