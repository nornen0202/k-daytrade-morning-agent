from datetime import datetime
from zoneinfo import ZoneInfo

from daytrade_agent.collectors.mock import collect_mock
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.normalizers.event_schema import ReportContext
from daytrade_agent.scoring.candidate_score import score_candidates


def _context() -> ReportContext:
    config = AppConfig.load()
    generated_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    result = collect_mock(config, "2026-04-27", generated_at)
    return ReportContext(
        report_date="2026-04-27",
        generated_at=generated_at,
        data_status="ok",
        events=result.events,
        sources=result.sources,
        price_snapshots=result.price_snapshots,
        candidates=score_candidates(config, result.events, result.price_snapshots, generated_at),
        market_context=result.market_context,
    )


def test_verifier_passes_fixture_report():
    context = _context()
    markdown = (
        "# Report\n"
        "- Samsung Electronics(005930) 관찰 우선순위 6.50/10 "
        "- source_id: src_policy_001; data_key: price_005930_20260427_0835\n"
    )
    result = verify_report(context, markdown)

    assert result.status == "pass"


def test_verifier_rejects_policy_violations():
    context = _context()
    bad_phrase = "\ubb34\uc870\uac74" + " " + "\ub9e4\uc218"
    markdown = f"# Report\n- {bad_phrase} 표현\n"
    result = verify_report(context, markdown)

    assert result.status == "fail"
    assert result.errors


def test_verifier_rejects_unknown_bare_symbol():
    context = _context()
    markdown = "# Report\n- 123456 신규 후보 관찰. source_id: src_policy_001\n"
    result = verify_report(context, markdown)

    assert result.status == "fail"
    assert any("unknown symbol" in error for error in result.errors)


def test_verifier_rejects_numeric_claim_without_evidence():
    context = _context()
    markdown = "# Report\n- 후보 점수 7.5로 확인되었습니다.\n"
    result = verify_report(context, markdown)

    assert result.status == "fail"
    assert any("numeric material claim" in error for error in result.errors)
