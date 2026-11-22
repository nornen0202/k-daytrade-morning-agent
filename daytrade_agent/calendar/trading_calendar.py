from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import exchange_calendars
import yaml


def is_weekday(value: date) -> bool:
    return value.weekday() < 5


def _load_holidays_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
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
def _xkrx_calendar(end_year: int | None = None):
    if end_year is None:
        return exchange_calendars.get_calendar("XKRX")
    return exchange_calendars.get_calendar("XKRX", end=f"{end_year}-12-31")


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
    merged_holidays = (holidays or set()) | _holidays_from_config(config)
    if not is_weekday(value) or value in merged_holidays:
        return "closed"
    try:
        max_year = max((y for y in coverage_years if isinstance(y, int)), default=value.year)
        cal = _xkrx_calendar(max(max_year, date.today().year + 1) + 1)
        return "open" if cal.is_session(value.isoformat()) else "closed"
    except (ValueError, OverflowError):
        # Unknown calendar coverage must never become an assumed trading session.
        return "unknown"

