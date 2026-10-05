"""Wall-clock adapter; Moscow is UTC+03:00, independent of the PC's timezone.

Live hosts update iDate separately from animation time. Snapshot hosts use an
explicit fixed clock so a render remains reproducible.
"""
import re
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3), "MSK")
SNAPSHOT_CLOCK = 21 * 3600 + 15 * 60


def moscow_i_date(now: datetime | None = None) -> tuple[float, float, float, float]:
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("clock input must include a timezone")
    local = now.astimezone(MSK)
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    return float(local.year), float(local.month), float(local.day), float(seconds)


def parse_clock(text: str) -> float:
    """Parse HH:MM[:SS] in MSK for deterministic screenshots."""
    if not re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", text):
        raise ValueError("expected HH:MM or HH:MM:SS (MSK)")
    parts = [int(part) for part in text.split(":")]
    hour, minute = parts[:2]
    second = parts[2] if len(parts) == 3 else 0
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError("clock must be in 00:00:00..23:59:59")
    return float(hour * 3600 + minute * 60 + second)
