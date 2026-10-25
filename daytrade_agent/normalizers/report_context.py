from __future__ import annotations

from daytrade_agent.normalizers.event_schema import Candidate, PriceSnapshot, ReportContext


def context_from_summary(summary: dict) -> ReportContext:
    snapshots = [PriceSnapshot.model_validate(item) for item in summary.get("price_snapshots", [])]
    by_key = {snapshot.data_key: snapshot for snapshot in snapshots}
    candidates = []
    for item in summary.get("candidates", []):
        data = dict(item)
        data["price_snapshot"] = by_key.get(data.pop("data_key", None))
        candidates.append(Candidate.model_validate(data))
    return ReportContext(
        report_date=summary["report_date"], generated_at=summary["generated_at"],
        data_status=summary.get("data_status", "insufficient"),
        events=summary.get("events", []), sources=summary.get("sources", []),
        price_snapshots=snapshots, candidates=candidates,
        market_context=summary.get("market_context", {}),
        missing_data=summary.get("missing_data", []),
    )
