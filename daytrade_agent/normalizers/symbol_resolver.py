from __future__ import annotations

from daytrade_agent.normalizers.event_schema import MarketEvent, PriceSnapshot


def resolve_symbol_names(
    events: list[MarketEvent],
    snapshots: list[PriceSnapshot],
    watchlist: dict[str, str] | None = None,
) -> dict[str, str]:
    names = dict(watchlist or {})
    for snapshot in snapshots:
        names[snapshot.symbol] = snapshot.name
    for event in events:
        for symbol in event.candidate_symbols:
            names.setdefault(symbol, symbol)
    return names

