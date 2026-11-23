from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from daytrade_agent.collectors.base import CollectorResult, read_fixture
from daytrade_agent.config import AppConfig
from daytrade_agent.normalizers.event_schema import (
    MarketEvent,
    PriceSnapshot,
    Source,
    parse_datetime,
    stable_id,
)

FIXTURE_VARIANTS = ("standard", "no-quotes", "mixed-timestamps", "stale")


def collect_mock(
    config: AppConfig, report_date: str, collected_at: datetime, *, variant: str = "standard",
) -> CollectorResult:
    if variant not in FIXTURE_VARIANTS:
        raise ValueError(f"unknown fixture: {variant}")
    fixture = read_fixture(config.fixture_dir / "sample_events.json")
    anchor = date.fromisoformat(fixture["anchor_date"])
    selected = date.fromisoformat(report_date)
    delta = selected - anchor
    if variant == "stale":
        delta -= timedelta(days=7)

    def shifted(raw: dict[str, Any], time_field: str) -> dict[str, Any]:
        item = dict(raw)
        value = parse_datetime(item.get(time_field))
        if value is not None:
            item[time_field] = (value + delta).isoformat()
        for name in ("event_id", "data_key"):
            if name in item:
                item[name] = item[name].replace(anchor.strftime("%Y%m%d"),
                                                selected.strftime("%Y%m%d"))
        return item

    events = [_event_from_raw(shifted(item, "published_at")) for item in fixture["events"]]
    if variant == "mixed-timestamps":
        for event, offset in zip(events, [timedelta(seconds=1), -timedelta(days=7)], strict=False):
            event.published_at = collected_at + offset
    sources = [_source_from_event(event, collected_at) for event in events]
    snapshots = []
    market_context = {}
    if variant != "no-quotes":
        snapshots = [_snapshot_from_raw(shifted(item, "as_of"))
                     for item in fixture["price_snapshots"]]
        market_context = {key: shifted(item, "as_of")
                          for key, item in fixture["market_context"].items()}
    return CollectorResult(
        events=events,
        sources=sources,
        price_snapshots=snapshots,
        market_context=market_context,
        missing_data=["합성 fixture 시세 없음"] if variant == "no-quotes" else [],
    )


def collect_category_mock(
    config: AppConfig,
    category: str,
    collected_at: datetime,
) -> CollectorResult:
    full = collect_mock(config, collected_at.date().isoformat(), collected_at)
    events = [event for event in full.events if event.category == category]
    source_ids = {event.source_id for event in events}
    sources = [source for source in full.sources if source.source_id in source_ids]
    return CollectorResult(events=events, sources=sources)


def collect_mock_prices(config: AppConfig, collected_at: datetime) -> CollectorResult:
    full = collect_mock(config, collected_at.date().isoformat(), collected_at)
    return CollectorResult(
        price_snapshots=full.price_snapshots,
        market_context=full.market_context,
    )


def _event_from_raw(raw: dict[str, Any]) -> MarketEvent:
    source_id = str(raw.get("source_id") or stable_id("src", raw.get("title", "")))
    return MarketEvent(
        event_id=str(raw.get("event_id") or stable_id("evt", source_id, raw.get("title", ""))),
        category=raw["category"],
        title=str(raw.get("title") or "데이터 부족"),
        summary=str(raw.get("summary") or "데이터 부족"),
        published_at=parse_datetime(raw.get("published_at")),
        source_id=source_id,
        source_url=raw.get("source_url"),
        source_name=str(raw.get("source_name") or "mock"),
        source_quality=float(raw.get("source_quality", 0.5)),
        affected_sectors=[str(item) for item in raw.get("affected_sectors", [])],
        candidate_symbols=[str(item) for item in raw.get("candidate_symbols", [])],
        confidence=float(raw.get("confidence", 0.5)),
        data_status=raw.get("data_status", "ok"),
    )


def _source_from_event(event: MarketEvent, collected_at: datetime) -> Source:
    return Source(
        source_id=event.source_id,
        source_name=event.source_name,
        source_url=event.source_url,
        source_type=event.category,
        published_at=event.published_at,
        collected_at=collected_at,
        source_quality=event.source_quality,
    )


def _snapshot_from_raw(raw: dict[str, Any]) -> PriceSnapshot:
    return PriceSnapshot(
        symbol=str(raw["symbol"]),
        name=str(raw.get("name") or raw["symbol"]),
        market=str(raw.get("market") or "KOSPI"),
        last_price=raw.get("last_price"),
        change_rate=raw.get("change_rate"),
        volume=raw.get("volume"),
        trading_value=raw.get("trading_value"),
        session_type=str(raw.get("session_type") or "regular"),
        as_of=parse_datetime(raw.get("as_of")),
        provider=str(raw.get("provider") or "mock"),
        data_key=str(
            raw.get("data_key") or stable_id("price", raw["symbol"], raw.get("as_of", ""))
        ),
        data_status=raw.get("data_status", "ok"),
    )
