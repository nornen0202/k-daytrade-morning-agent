from __future__ import annotations

from daytrade_agent.normalizers.event_schema import MarketEvent, PriceSnapshot


def risk_flags_for(
    events: list[MarketEvent],
    snapshot: PriceSnapshot | None,
    *,
    high_volatility_abs: float = 8.0,
    low_source_quality_below: float = 0.4,
    low_confidence_below: float = 0.45,
) -> list[str]:
    flags: list[str] = []
    if not events:
        flags.append("no_event_support")
    if any(event.data_status in {"insufficient", "stale"} for event in events):
        flags.append("data_gap")
    if events and min(event.source_quality for event in events) < low_source_quality_below:
        flags.append("low_source_quality")
    if events and min(event.confidence for event in events) < low_confidence_below:
        flags.append("low_confidence")
    if snapshot is None:
        flags.append("missing_price_snapshot")
    elif snapshot.as_of is None:
        flags.append("missing_price_timestamp")
    elif snapshot.change_rate is not None and abs(snapshot.change_rate) >= high_volatility_abs:
        flags.append("high_volatility")
    return flags or ["none"]


def risk_penalty(flags: list[str]) -> float:
    penalty_map = {
        "data_gap": 1.0,
        "low_source_quality": 0.7,
        "low_confidence": 0.7,
        "missing_price_snapshot": 1.0,
        "missing_price_timestamp": 0.8,
        "high_volatility": 1.5,
        "no_event_support": 1.0,
    }
    return sum(penalty_map.get(flag, 0.0) for flag in flags)

