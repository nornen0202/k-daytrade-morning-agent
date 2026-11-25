from __future__ import annotations

from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

SEOUL = ZoneInfo("Asia/Seoul")
MORNING_START = time(8, 45)


def premarket_cutoff(value: date) -> datetime:
    return datetime.combine(value, time(9), SEOUL)


def is_weekday(value: date) -> bool:
    return value.weekday() < 5


def _load_holidays_config(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _holidays_from_config(data: dict) -> set[date]:
    holidays = data.get("holidays", [])
    if not isinstance(holidays, list):
        return set()
    return {
        date.fromisoformat(str(item["date"]))
        for item in holidays
        if isinstance(item, dict) and item.get("date")
    }


def load_holidays(path: Path) -> set[date]:
    return _holidays_from_config(_load_holidays_config(path))


@lru_cache(maxsize=4)
def _xkrx_calendar(year: int):
    import exchange_calendars

    return exchange_calendars.get_calendar("XKRX", start=f"{year}-01-01", end=f"{year}-12-31")


def is_trading_day(value: date, holidays: set[date] | None = None) -> bool:
    return trading_status(value, holidays) == "open"


def trading_status(value: date, holidays: set[date] | None = None) -> str:
    amendments = Path(__file__).resolve().parents[2] / "config" / "holidays_kr.yml"
    config = _load_holidays_config(amendments)
    if not config:
        return "unknown"
    coverage_years = config.get("coverage_years", [])
    if not isinstance(coverage_years, list) or value.year not in coverage_years:
        return "unknown"
    if not is_weekday(value) or value in (holidays or set()):
        return "closed"
    try:
        if value in _holidays_from_config(config):
            return "closed"
        cal = _xkrx_calendar(value.year)
        # is_session rejects holidays before the first session or after the last session.
        return "open" if value.isoformat() in cal.sessions else "closed"
    except (ValueError, OverflowError):
        # Unknown calendar coverage must never become an assumed trading session.
        return "unknown"

