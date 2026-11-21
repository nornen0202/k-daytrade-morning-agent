from __future__ import annotations

from typing import Any

from daytrade_agent.normalizers.event_schema import (
    Candidate,
    MarketEvent,
    PriceSnapshot,
    ReportContext,
    Source,
    parse_datetime,
)


def context_from_summary(summary: dict[str, Any]) -> ReportContext:
    """Reconstruct a validated ReportContext from a persisted summary.json mapping."""
    snapshots = [
        PriceSnapshot.model_validate(item)
        for item in summary.get("price_snapshots", [])
        if isinstance(item, dict)
    ]
    by_key = {snapshot.data_key: snapshot for snapshot in snapshots}
    candidates: list[Candidate] = []
    for item in summary.get("candidates", []):
        if not isinstance(item, dict):
            continue
        data = dict(item)
        data_key = data.pop("data_key", None)
        data["price_snapshot"] = by_key.get(data_key) if data_key else None
        data.setdefault("market", "KRX")
        data.setdefault("categories", [])
        data.setdefault("score", 0.0)
        data.setdefault("main_reason", "데이터 부족")
        data.setdefault("source_ids", [])
        data.setdefault("risk_flags", [])
        data.setdefault("observation_condition", "데이터 부족")
        data.setdefault("invalidation_condition", "데이터 부족")
        candidates.append(Candidate.model_validate(data))

    raw_generated = summary.get("generated_at")
    generated_at = parse_datetime(str(raw_generated)) if raw_generated is not None else None
    if generated_at is None:
        raise ValueError("summary.generated_at must be a timezone-aware ISO datetime")

    market_context = summary.get("market_context", {})
    if not isinstance(market_context, dict):
        market_context = {}

    return ReportContext(
        report_date=str(summary["report_date"]),
        generated_at=generated_at,
        data_status=summary.get("data_status", "insufficient"),
        events=[
            MarketEvent.model_validate(item)
            for item in summary.get("events", [])
            if isinstance(item, dict)
        ],
        sources=[
            Source.model_validate(item)
            for item in summary.get("sources", [])
            if isinstance(item, dict)
        ],
        price_snapshots=snapshots,
        candidates=candidates,
        market_context=market_context,
        missing_data=[
            str(item) for item in summary.get("missing_data", []) if isinstance(item, str)
        ],
    )
