from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from daytrade_agent.collectors.mock import collect_mock
from daytrade_agent.config import AppConfig
from daytrade_agent.scoring.candidate_score import score_candidates


def test_candidate_score_is_deterministic():
    config = AppConfig.load()
    generated_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    result = collect_mock(config, "2026-04-27", generated_at)

    first = score_candidates(config, result.events, result.price_snapshots, generated_at)
    second = score_candidates(config, result.events, result.price_snapshots, generated_at)

    assert [candidate.model_dump() for candidate in first] == [
        candidate.model_dump() for candidate in second
    ]
    assert first[0].score >= 5
    assert first[0].source_ids

    missing_price = next(candidate for candidate in first if candidate.symbol == "277810")
    assert "가격 확인 필요" in missing_price.observation_condition


def test_candidate_score_honors_risk_rule_penalties():
    from dataclasses import replace

    config = AppConfig.load()
    generated_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    result = collect_mock(config, "2026-04-27", generated_at)
    base = score_candidates(config, result.events, result.price_snapshots, generated_at)
    base_score = next(item.score for item in base if item.symbol == "277810")

    harsher = replace(config, risk_rules={**config.risk_rules, "missing_price_penalty": 3.0})
    updated = score_candidates(harsher, result.events, result.price_snapshots, generated_at)
    updated_score = next(item.score for item in updated if item.symbol == "277810")
    assert updated_score < base_score


def test_one_article_counts_once_but_keeps_provenance():
    config = AppConfig.load()
    generated_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    batch = collect_mock(config, "2026-04-27", generated_at)
    article = batch.events[0]
    article.candidate_symbols = ["005930", "005930"]
    copies = [
        article.model_copy(update={"title": article.title + "!", "source_id": "src_fixture_1"}),
        article.model_copy(update={"title": "동일 기사 제목 변경", "source_id": "src_fixture_2",
                                   "source_url": HttpUrl(
                                       str(article.source_url) + "?utm_source=fixture",
                                   )}),
    ]
    original = score_candidates(config, [article], batch.price_snapshots, generated_at)[0]
    grouped = score_candidates(config, [article, *copies], batch.price_snapshots, generated_at)[0]
    distinct = article.model_copy(update={"title": "별도 실적 보도", "source_id": "src_distinct",
                                          "source_url": None})
    combined = score_candidates(config, [article, distinct], batch.price_snapshots, generated_at)
    assert grouped.score == original.score
    assert grouped.source_ids == sorted([article.source_id, "src_fixture_1", "src_fixture_2"])
    assert combined[0].score > original.score
