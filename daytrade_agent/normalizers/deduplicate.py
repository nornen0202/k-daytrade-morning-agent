from __future__ import annotations

from daytrade_agent.normalizers.event_schema import Candidate, MarketEvent


def deduplicate_events(events: list[MarketEvent]) -> list[MarketEvent]:
    seen: set[tuple[str, str]] = set()
    unique: list[MarketEvent] = []
    for event in events:
        key = (event.source_id, event.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def deduplicate_candidates(candidates: list[Candidate]) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for candidate in candidates:
        current = best.get(candidate.symbol)
        if current is None or candidate.score > current.score:
            best[candidate.symbol] = candidate
    return sorted(best.values(), key=lambda item: item.score, reverse=True)

