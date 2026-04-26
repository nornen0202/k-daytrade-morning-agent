from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from daytrade_agent.normalizers.event_schema import MarketEvent, PriceSnapshot, Source


@dataclass(frozen=True)
class CollectorResult:
    events: list[MarketEvent] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    price_snapshots: list[PriceSnapshot] = field(default_factory=list)
    market_context: dict[str, Any] = field(default_factory=dict)
    missing_data: list[str] = field(default_factory=list)


class Collector(Protocol):
    def collect(self, report_date: str, collected_at: datetime) -> CollectorResult:
        ...


def read_fixture(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected fixture object at {path}")
    return data


def insufficient_result(category: str, reason: str) -> CollectorResult:
    return CollectorResult(missing_data=[f"{category}: {reason}"])

