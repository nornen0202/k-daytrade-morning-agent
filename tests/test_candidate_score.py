from datetime import datetime
from zoneinfo import ZoneInfo

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

