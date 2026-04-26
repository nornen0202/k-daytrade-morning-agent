from datetime import datetime
from zoneinfo import ZoneInfo

from daytrade_agent.collectors.mock import collect_mock
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.prompt_builder import build_prompt
from daytrade_agent.normalizers.event_schema import ReportContext
from daytrade_agent.scoring.candidate_score import score_candidates


def test_prompt_contains_facts_json_and_policy():
    config = AppConfig.load()
    generated_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    result = collect_mock(config, "2026-04-27", generated_at)
    candidates = score_candidates(config, result.events, result.price_snapshots, generated_at)
    context = ReportContext(
        report_date="2026-04-27",
        generated_at=generated_at,
        data_status="ok",
        events=result.events,
        sources=result.sources,
        price_snapshots=result.price_snapshots,
        candidates=candidates,
        market_context=result.market_context,
    )

    prompt = build_prompt(context, config.root / "prompts" / "master_morning_briefing.md")

    assert "Facts JSON" in prompt
    assert "source_id" in prompt
    assert "데이터 부족" in prompt

