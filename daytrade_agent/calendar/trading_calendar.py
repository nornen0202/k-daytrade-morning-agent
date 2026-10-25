from __future__ import annotations

from datetime import date
from pathlib import Path

import exchange_calendars
import yaml


def is_weekday(value: date) -> bool:
    return value.weekday() < 5


def load_holidays(path: Path) -> set[date]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    holidays = data.get("holidays", []) if isinstance(data, dict) else []
    return {
        date.fromisoformat(str(item["date"]))
        for item in holidays
        if isinstance(item, dict) and item.get("date")
    }


def is_trading_day(value: date, holidays: set[date] | None = None) -> bool:
    return trading_status(value, holidays) == "open"


def trading_status(value: date, holidays: set[date] | None = None) -> str:
    amendments = Path(__file__).resolve().parents[2] / "config" / "holidays_kr.yml"
    if not amendments.exists():
        return "unknown"
    config = yaml.safe_load(amendments.read_text(encoding="utf-8"))
    if value.year not in config.get("coverage_years", []):
        return "unknown"
    holidays = (holidays or set()) | load_holidays(amendments)
    if not is_weekday(value) or value in (holidays or set()):
        return "closed"
    try:
        calendar = exchange_calendars.get_calendar("XKRX")
        return "open" if calendar.is_session(value.isoformat()) else "closed"
    except (ValueError, OverflowError):
        # Unknown calendar coverage must never become an assumed trading session.
        return "unknown"

