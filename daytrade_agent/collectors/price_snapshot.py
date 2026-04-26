from __future__ import annotations

from datetime import datetime

import requests

from daytrade_agent.collectors.base import CollectorResult, insufficient_result
from daytrade_agent.collectors.mock import collect_mock_prices
from daytrade_agent.config import AppConfig
from daytrade_agent.normalizers.event_schema import PriceSnapshot, parse_datetime, stable_id


def collect(
    config: AppConfig,
    report_date: str,
    collected_at: datetime,
    dry_run: bool,
    symbols: list[str] | None = None,
) -> CollectorResult:
    if dry_run:
        return collect_mock_prices(config, collected_at)

    provider_url = config.env("QUOTE_PROVIDER_URL")
    if not provider_url:
        return insufficient_result("price_snapshot", "QUOTE_PROVIDER_URL is not configured")

    headers = {}
    api_key = config.env("QUOTE_PROVIDER_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.get(
        provider_url,
        params={"date": report_date, "symbols": ",".join(sorted(set(symbols or [])))},
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    raw_snapshots = payload.get("snapshots", []) if isinstance(payload, dict) else []
    market_context = payload.get("market_context", {}) if isinstance(payload, dict) else {}
    snapshots = [_snapshot_from_raw(item) for item in raw_snapshots if isinstance(item, dict)]
    return CollectorResult(price_snapshots=snapshots, market_context=market_context)


def _snapshot_from_raw(raw: dict[str, object]) -> PriceSnapshot:
    symbol = str(raw["symbol"])
    return PriceSnapshot(
        symbol=symbol,
        name=str(raw.get("name") or symbol),
        market=str(raw.get("market") or "KOSPI"),
        last_price=raw.get("last_price"),
        change_rate=raw.get("change_rate"),
        volume=raw.get("volume"),
        trading_value=raw.get("trading_value"),
        session_type=str(raw.get("session_type") or "regular"),
        as_of=parse_datetime(raw.get("as_of")),
        provider=str(raw.get("provider") or "quote_provider"),
        data_key=str(raw.get("data_key") or stable_id("price", symbol, raw.get("as_of", ""))),
        data_status=raw.get("data_status", "ok"),
    )

