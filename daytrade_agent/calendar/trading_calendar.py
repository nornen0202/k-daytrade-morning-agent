from __future__ import annotations

from datetime import date
from pathlib import Path

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
    return is_weekday(value) and value not in (holidays or set())

