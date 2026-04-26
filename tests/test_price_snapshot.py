from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from daytrade_agent.collectors.price_snapshot import collect
from daytrade_agent.config import AppConfig


def test_price_snapshot_uses_yfinance_when_quote_provider_missing(monkeypatch):
    config = AppConfig.load()
    collected_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    monkeypatch.delenv("QUOTE_PROVIDER_URL", raising=False)
    monkeypatch.delenv("QUOTE_PROVIDER_API_KEY", raising=False)

    class FakeTicker:
        info = {"shortName": "삼성전자"}
        fast_info = {
            "last_price": 72000,
            "previous_close": 70000,
            "last_volume": 1000,
        }

        def __init__(self, ticker):
            self.ticker = ticker

    monkeypatch.setitem(
        __import__("sys").modules,
        "yfinance",
        SimpleNamespace(Ticker=FakeTicker),
    )

    result = collect(
        config,
        report_date="2026-04-27",
        collected_at=collected_at,
        dry_run=False,
        symbols=["005930"],
    )

    assert not result.missing_data
    assert result.price_snapshots[0].provider == "yfinance"
    assert result.price_snapshots[0].as_of == collected_at
    assert result.price_snapshots[0].trading_value == 72_000_000


def test_price_snapshot_sanitizes_yfinance_symbol_bundle_names(monkeypatch):
    config = AppConfig.load()
    collected_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    monkeypatch.delenv("QUOTE_PROVIDER_URL", raising=False)

    class FakeTicker:
        info = {"shortName": "065420.KS,0P0000CH5Y,794450"}
        fast_info = {"last_price": 1000}

        def __init__(self, ticker):
            self.ticker = ticker

    monkeypatch.setitem(
        __import__("sys").modules,
        "yfinance",
        SimpleNamespace(Ticker=FakeTicker),
    )

    result = collect(
        config,
        report_date="2026-04-27",
        collected_at=collected_at,
        dry_run=False,
        symbols=["065420"],
    )

    assert result.price_snapshots[0].name == "065420"
