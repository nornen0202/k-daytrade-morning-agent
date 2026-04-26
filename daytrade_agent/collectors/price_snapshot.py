from __future__ import annotations

from datetime import datetime
from importlib import import_module
from typing import Any

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

    provider_result = _collect_provider_quote(config, report_date, symbols)
    if provider_result.price_snapshots:
        return provider_result

    yfinance_result = _collect_yfinance_quotes(symbols or [], collected_at)
    if yfinance_result.price_snapshots:
        return yfinance_result

    reasons = [*provider_result.missing_data, *yfinance_result.missing_data]
    return insufficient_result(
        "price_snapshot",
        "; ".join(reasons) if reasons else "QUOTE_PROVIDER_URL and yfinance quote unavailable",
    )


def _collect_provider_quote(
    config: AppConfig,
    report_date: str,
    symbols: list[str] | None,
) -> CollectorResult:
    provider_url = config.env("QUOTE_PROVIDER_URL")
    if not provider_url:
        return CollectorResult(missing_data=["QUOTE_PROVIDER_URL is not configured"])

    headers = {}
    api_key = config.env("QUOTE_PROVIDER_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.get(
            provider_url,
            params={"date": report_date, "symbols": ",".join(sorted(set(symbols or [])))},
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return CollectorResult(missing_data=[f"quote provider failed: {type(exc).__name__}"])

    raw_snapshots = payload.get("snapshots", []) if isinstance(payload, dict) else []
    market_context = payload.get("market_context", {}) if isinstance(payload, dict) else {}
    snapshots = [_snapshot_from_raw(item) for item in raw_snapshots if isinstance(item, dict)]
    return CollectorResult(price_snapshots=snapshots, market_context=market_context)


def _collect_yfinance_quotes(symbols: list[str], collected_at: datetime) -> CollectorResult:
    if not symbols:
        return CollectorResult(missing_data=["no symbols available for yfinance quote"])
    try:
        yf = import_module("yfinance")
    except ImportError:
        return CollectorResult(missing_data=["yfinance is not installed"])

    snapshots: list[PriceSnapshot] = []
    missing: list[str] = []
    for symbol in sorted(set(symbols)):
        snapshot = _yfinance_snapshot(yf, symbol, collected_at)
        if snapshot:
            snapshots.append(snapshot)
        else:
            missing.append(f"yfinance quote unavailable for {symbol}")
    return CollectorResult(price_snapshots=snapshots, missing_data=missing)


def _yfinance_snapshot(module: Any, symbol: str, collected_at: datetime) -> PriceSnapshot | None:
    for yahoo_symbol in _yahoo_candidates(symbol):
        ticker = module.Ticker(yahoo_symbol)
        fast_info = getattr(ticker, "fast_info", {}) or {}
        last_price = _float_or_none(_fast_info_get(fast_info, "last_price", "lastPrice"))
        previous_close = _float_or_none(
            _fast_info_get(
                fast_info,
                "previous_close",
                "previousClose",
                "regularMarketPreviousClose",
            )
        )
        volume = _int_or_none(_fast_info_get(fast_info, "last_volume", "lastVolume"))
        if last_price is None:
            history_data = _history_data(ticker)
            last_price = history_data.get("last_price")
            previous_close = previous_close or history_data.get("previous_close")
            volume = volume or _int_or_none(history_data.get("volume"))
        if last_price is None:
            continue
        change_rate = None
        if previous_close and previous_close > 0:
            change_rate = round(((last_price - previous_close) / previous_close) * 100, 2)
        trading_value = int(last_price * volume) if volume else None
        market = _market_from_yahoo(yahoo_symbol)
        return PriceSnapshot(
            symbol=symbol,
            name=_name_from_ticker(ticker, symbol),
            market=market,
            last_price=last_price,
            change_rate=change_rate,
            volume=volume,
            trading_value=trading_value,
            session_type="regular",
            as_of=collected_at,
            provider="yfinance",
            data_key=stable_id("price", "yfinance", yahoo_symbol, collected_at.isoformat()),
            data_status="ok",
        )
    return None


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


def _yahoo_candidates(symbol: str) -> list[str]:
    normalized = symbol.upper().strip()
    if normalized.endswith((".KS", ".KQ")):
        return [normalized]
    if len(normalized) == 6 and normalized.isdigit():
        return [f"{normalized}.KS", f"{normalized}.KQ", normalized]
    return [normalized]


def _market_from_yahoo(yahoo_symbol: str) -> str:
    if yahoo_symbol.endswith(".KQ"):
        return "KOSDAQ"
    if yahoo_symbol.endswith(".KS"):
        return "KOSPI"
    return "KRX"


def _fast_info_get(info: object, *keys: str) -> object:
    for key in keys:
        try:
            if isinstance(info, dict) and key in info:
                return info[key]
            value = getattr(info, key)
        except (AttributeError, KeyError, TypeError):
            continue
        if value is not None:
            return value
    return None


def _history_data(ticker: object) -> dict[str, float | int | None]:
    try:
        history = ticker.history(period="5d")
    except Exception:
        return {}
    if history is None or getattr(history, "empty", True):
        return {}
    closes = history["Close"].dropna()
    volumes = history["Volume"].dropna() if "Volume" in history else []
    if len(closes) == 0:
        return {}
    last_price = _float_or_none(closes.iloc[-1])
    previous_close = _float_or_none(closes.iloc[-2]) if len(closes) >= 2 else None
    volume = _int_or_none(volumes.iloc[-1]) if len(volumes) else None
    return {"last_price": last_price, "previous_close": previous_close, "volume": volume}


def _name_from_ticker(ticker: object, fallback: str) -> str:
    try:
        info = getattr(ticker, "info", {}) or {}
    except Exception:
        info = {}
    if isinstance(info, dict):
        return str(info.get("shortName") or info.get("longName") or fallback)
    return fallback


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
