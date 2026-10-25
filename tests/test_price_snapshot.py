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
        info = {
            "shortName": "삼성전자", "regularMarketTime": collected_at.timestamp() - 900,
            "regularMarketPrice": 72000, "regularMarketVolume": 1000,
            "regularMarketChangePercent": 2.86,
        }
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
    assert result.price_snapshots[0].as_of.timestamp() == collected_at.timestamp() - 900
    assert result.price_snapshots[0].session_type == "delayed_regular"
    assert result.price_snapshots[0].trading_value is None


def test_price_snapshot_sanitizes_yfinance_symbol_bundle_names(monkeypatch):
    config = AppConfig.load()
    collected_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    monkeypatch.delenv("QUOTE_PROVIDER_URL", raising=False)

    class FakeTicker:
        info = {"shortName": "065420.KS,0P0000CH5Y,794450", "regularMarketPrice": 1000}
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
    assert result.price_snapshots[0].as_of is None
    assert result.price_snapshots[0].data_status == "insufficient"


def test_yfinance_never_pairs_current_time_with_an_old_history_close(monkeypatch):
    from daytrade_agent.collectors.price_snapshot import _yfinance_snapshot

    stamp = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))

    class Ticker:
        info = {"regularMarketTime": stamp.timestamp()}
        fast_info = {"last_price": 99999}

        def history(self, **kwargs):
            raise AssertionError("daily history must not be relabeled as a current quote")

    assert _yfinance_snapshot(SimpleNamespace(Ticker=lambda symbol: Ticker()), "005930", stamp) \
        is None
