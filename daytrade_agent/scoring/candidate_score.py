from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from daytrade_agent.config import AppConfig
from daytrade_agent.normalizers.event_schema import Candidate, MarketEvent, PriceSnapshot
from daytrade_agent.normalizers.symbol_resolver import resolve_symbol_names
from daytrade_agent.scoring.risk_flags import risk_flags_for, risk_penalty


def score_candidates(
    config: AppConfig,
    events: list[MarketEvent],
    price_snapshots: list[PriceSnapshot],
    generated_at: datetime,
    limit: int | None = None,
) -> list[Candidate]:
    events_by_symbol: dict[str, list[MarketEvent]] = defaultdict(list)
    for event in events:
        for symbol in event.candidate_symbols:
            events_by_symbol[symbol].append(event)

    snapshots_by_symbol = {snapshot.symbol: snapshot for snapshot in price_snapshots}
    names = resolve_symbol_names(events, price_snapshots)
    candidates: list[Candidate] = []

    for symbol, symbol_events in events_by_symbol.items():
        snapshot = snapshots_by_symbol.get(symbol)
        flags = risk_flags_for(
            symbol_events,
            snapshot,
            high_volatility_abs=float(
                config.risk_rules.get("high_volatility_change_rate_abs", 8.0)
            ),
            low_source_quality_below=float(config.risk_rules.get("low_source_quality_below", 0.4)),
            low_confidence_below=float(config.risk_rules.get("low_confidence_below", 0.45)),
        )
        detail = _score_detail(config, symbol_events, snapshot, generated_at)
        total_score = (
            0.25 * detail["freshness_score"]
            + 0.25 * detail["materiality_score"]
            + 0.20 * detail["market_confirmation_score"]
            + 0.15 * detail["theme_strength_score"]
            + 0.10 * detail["source_quality_score"]
            + 0.05 * detail["liquidity_score"]
            - risk_penalty(flags)
        )
        score = max(0.0, min(10.0, round(total_score, 2)))
        categories = sorted({event.category for event in symbol_events})
        source_ids = sorted({event.source_id for event in symbol_events})
        candidates.append(
            Candidate(
                symbol=symbol,
                name=names.get(symbol, symbol),
                market=snapshot.market if snapshot else "KRX",
                categories=categories,
                score=score,
                main_reason=_main_reason(symbol_events),
                source_ids=source_ids,
                price_snapshot=snapshot,
                risk_flags=flags,
                observation_condition=_observation_condition(snapshot),
                invalidation_condition=_invalidation_condition(flags),
            )
        )

    return sorted(candidates, key=lambda item: item.score, reverse=True)[
        : limit or config.default_top_n
    ]


def _score_detail(
    config: AppConfig,
    events: list[MarketEvent],
    snapshot: PriceSnapshot | None,
    generated_at: datetime,
) -> dict[str, float]:
    category_weights = config.category_weights
    freshness_score = _freshness_score(events, generated_at)
    materiality_score = min(
        10.0,
        sum(6.0 * category_weights.get(event.category, 1.0) * event.confidence for event in events),
    )
    market_confirmation_score = _market_confirmation_score(snapshot)
    theme_strength_score = min(
        10.0,
        3.0 + len(events) * 1.7 + len({event.category for event in events}) * 1.2,
    )
    source_quality_score = round(
        10.0 * max((event.source_quality for event in events), default=0.0),
        2,
    )
    liquidity_score = _liquidity_score(snapshot)
    return {
        "freshness_score": freshness_score,
        "materiality_score": materiality_score,
        "market_confirmation_score": market_confirmation_score,
        "theme_strength_score": theme_strength_score,
        "source_quality_score": source_quality_score,
        "liquidity_score": liquidity_score,
    }


def _freshness_score(events: list[MarketEvent], generated_at: datetime) -> float:
    scores: list[float] = []
    for event in events:
        if event.data_status in {"insufficient", "stale"} or event.published_at is None:
            scores.append(2.0)
            continue
        age_hours = max(0.0, (generated_at - event.published_at).total_seconds() / 3600)
        if age_hours <= 12:
            scores.append(10.0)
        elif age_hours <= 24:
            scores.append(8.0)
        elif age_hours <= 48:
            scores.append(5.0)
        else:
            scores.append(2.0)
    return round(max(scores, default=0.0), 2)


def _market_confirmation_score(snapshot: PriceSnapshot | None) -> float:
    if snapshot is None or snapshot.data_status == "insufficient":
        return 0.0
    score = 3.0 if snapshot.as_of else 1.0
    if snapshot.change_rate is not None:
        score += 3.0 if -8.0 <= snapshot.change_rate <= 8.0 else 1.0
    if snapshot.trading_value:
        score += min(4.0, snapshot.trading_value / 20_000_000_000)
    return round(min(10.0, score), 2)


def _liquidity_score(snapshot: PriceSnapshot | None) -> float:
    if snapshot is None or not snapshot.trading_value:
        return 0.0
    if snapshot.trading_value >= 200_000_000_000:
        return 10.0
    if snapshot.trading_value >= 100_000_000_000:
        return 8.0
    if snapshot.trading_value >= 30_000_000_000:
        return 6.0
    if snapshot.trading_value >= 10_000_000_000:
        return 4.0
    return 2.0


def _main_reason(events: list[MarketEvent]) -> str:
    if not events:
        return "데이터 부족"
    event = sorted(events, key=lambda item: (item.confidence, item.source_quality), reverse=True)[0]
    return f"{event.title} (source_id: {event.source_id})"


def _observation_condition(snapshot: PriceSnapshot | None) -> str:
    if snapshot is None or snapshot.as_of is None:
        return "가격 확인 필요. 공식 시세 화면에서 가격, 등락률, 거래대금 재확인 필요."
    return f"{snapshot.as_of.isoformat()} 기준 시세와 거래대금 재확인."


def _invalidation_condition(flags: list[str]) -> str:
    if "data_gap" in flags or "missing_price_snapshot" in flags:
        return "핵심 데이터가 확인되지 않으면 관찰 대상에서 제외."
    if "high_volatility" in flags:
        return "장초 변동성이 과도하면 추적 우선순위 하향."
    return "관련 뉴스/공시의 후속 확인이 약해지면 우선순위 하향."
