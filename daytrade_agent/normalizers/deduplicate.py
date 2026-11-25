from __future__ import annotations

import re
import unicodedata
from datetime import UTC
from urllib.parse import parse_qsl, urlsplit

from daytrade_agent.normalizers.event_schema import Candidate, MarketEvent


def _event_sort_timestamp(event: MarketEvent) -> tuple[bool, float]:
    if event.published_at is None:
        return (False, float("-inf"))
    stamp = (
        event.published_at.replace(tzinfo=UTC)
        if event.published_at.tzinfo is None
        else event.published_at
    )
    return (True, stamp.timestamp())


def deduplicate_events(events: list[MarketEvent]) -> list[MarketEvent]:
    unique: dict[tuple[str, str, str], MarketEvent] = {}
    for event in events:
        key = (event.category, event.source_id, event.title.strip().casefold())
        previous = unique.get(key)
        if previous is not None:
            best = max((previous, event), key=lambda item: (
                item.published_at is not None, item.source_quality, item.confidence,
            ))
            event = best.model_copy(update={
                "candidate_symbols": sorted(set(previous.candidate_symbols +
                                                event.candidate_symbols)),
            })
        unique[key] = event
    return list(unique.values())


def independent_events(events: list[MarketEvent]) -> list[MarketEvent]:
    """Count copies of an article once for ranking, including across feeds and categories."""
    seen: set[tuple[str, object]] = set()
    unique: list[MarketEvent] = []
    ordered = sorted(events, key=lambda event: (
        event.source_quality,
        event.confidence,
        *_event_sort_timestamp(event),
        event.source_id,
        event.category,
    ), reverse=True)
    for event in ordered:
        keys: set[tuple[str, object]] = {("source", event.source_id)}
        title = unicodedata.normalize("NFKC", event.title).casefold()
        title = re.sub(r"\s+", " ", title).strip(" !?…:;,.\"'")
        # A generic DART filing title can describe unrelated filings from different issuers.
        if event.category != "corporate_disclosure":
            if title and title != "데이터 부족":
                keys.add(("headline", title))
            if event.source_url:
                url = urlsplit(str(event.source_url))
                query = tuple(sorted((key, value) for key, value in parse_qsl(url.query)
                                     if not key.lower().startswith("utm_")
                                     and key.lower() not in {"gclid", "fbclid"}))
                if url.path not in ("", "/") or query:
                    keys.add(("url", (url.netloc, url.path.rstrip("/"), query)))
        if not keys & seen:
            unique.append(event)
        seen.update(keys)
    return unique


def deduplicate_candidates(candidates: list[Candidate]) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for candidate in candidates:
        current = best.get(candidate.symbol)
        if current is None or candidate.score > current.score:
            best[candidate.symbol] = candidate
    return sorted(best.values(), key=lambda item: item.score, reverse=True)

