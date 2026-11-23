from __future__ import annotations

import re
import unicodedata

from daytrade_agent.normalizers.event_schema import MarketEvent, PriceSnapshot


def news_symbol_mentions(title: str, summary: str, symbol_names: dict[str, str]) -> list[str]:
    text = unicodedata.normalize("NFKC", f"{title} {summary}")
    symbols = []
    for symbol, name in symbol_names.items():
        if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
            continue
        if not isinstance(name, str) or not name:
            continue
        # Keep exact names and common postpositions, excluding prefixes of other names.
        particles = r"(?:에서|으로|로|와|과|은|는|이|가|을|를|의|에|도)?"
        if re.search(rf"(?<!\w){re.escape(name)}{particles}(?!\w)", text, re.I):
            symbols.append(symbol)
    return symbols


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

