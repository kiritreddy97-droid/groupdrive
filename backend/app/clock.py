"""Single source of time. Tests monkeypatch `today`/`now`; business code receives the values as arguments."""
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    """Campaign dates are calendar dates in India."""
    return now().astimezone(IST).date()


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC so comparisons never mix naive and aware."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
