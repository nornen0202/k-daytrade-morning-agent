from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

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
    candidate = next(item for item in context.candidates if item.symbol == "005930")
    markdown = (
        "# Report\n"
        f"- Samsung Electronics(005930) 관찰 우선순위 {candidate.score:.2f}/10 "
        "- source_id: src_policy_001; data_key: score_005930\n"
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


def test_verifier_rejects_unsourced_price_like_claim():
    context = _context()
    markdown = "# Report\n- 현재가 10,000원 확인 필요.\n"
    result = verify_report(context, markdown)

    assert result.status == "fail"
    assert any("price-like claim" in error for error in result.errors)


@pytest.mark.parametrize("text", [
    "현재 시장 방향을 확정할 수 없다. 지수 확인은 데이터 부족이다.",
    "특정 정책의 확정, 수혜 업종을 뒷받침하는 정보는 데이터 부족이며 확장하지 않는다.",
    "데이터 부족으로 상승 방향을 확정하지 않는다.",
])
def test_data_gap_qualifications_are_not_certainty_assertions(text):
    context = _context()
    context.data_status = "partial"
    result = verify_report(context, f"- {text} (source_id: src_policy_001)")
    assert result.status == "warning", result.errors


@pytest.mark.parametrize("text", [
    "데이터 부족이지만 상승은 확정이다.",
    "데이터 부족이지만 주가 방향은 분명하다.",
    "데이터 부족으로 확정할 수 없다. 그러나 상승 확정.",
])
def test_affirmative_certainty_stays_blocked(text):
    context = _context()
    context.data_status = "partial"
    result = verify_report(context, f"- {text} (source_id: src_policy_001)")
    assert any("certainty wording" in error for error in result.errors)


def test_market_certainty_blocked_even_without_data_gap_phrase():
    context = _context()
    context.data_status = "partial"
    result = verify_report(context, "- 삼성전자 내일 상승은 확정이다. (source_id: src_policy_001)")
    assert result.status == "fail"
    assert any("certainty wording" in error for error in result.errors)


def test_candidate_name_with_digits_and_top_n_heading_pass_verifier():
    context = _context()
    context.candidates[0].name = "하나30호스팩"
    key = f"score_{context.candidates[0].symbol}"
    markdown = (
        "## 7. 통합 관심 후보 Top 10\n"
        f"- 하나30호스팩({context.candidates[0].symbol}): none (data_key: {key})\n"
    )
    result = verify_report(context, markdown)
    assert result.status == "pass", result.errors


def test_market_context_metric_is_verified_and_rendered():
    from daytrade_agent.llm.report_writer import verified_facts_markdown

    context = _context()
    markdown = verified_facts_markdown(AppConfig.load(), context)
    assert "KOSPI: 2,748.12" in markdown
    assert "data_key: mk_kospi_20260427" in markdown
    result = verify_report(context, markdown)
    assert result.status == "pass", result.errors


def test_missing_data_referencing_event_symbol_outside_top_n_passes():
    context = _context()
    context.candidates = [c for c in context.candidates if c.symbol != "277810"]
    context.missing_data = ["yfinance quote unavailable for 277810"]
    markdown = "- yfinance quote unavailable for 277810 (data_key: report_metadata)\n"
    result = verify_report(context, markdown)
    assert result.status == "warning", result.errors


def test_template_writer_redacts_candidate_price_news_and_passes_verifier():
    from daytrade_agent.llm.report_writer import build_summary, verified_facts_markdown

    context = _context()
    context.events[0].title = "Samsung Electronics 영업이익 10.5% 증가 보도"
    context.events[0].summary = "Samsung Electronics 관련 75,000원 전망 언급"
    markdown = verified_facts_markdown(AppConfig.load(), context)
    result = verify_report(context, markdown)
    assert result.status == "pass", result.errors
    summary = build_summary(context, markdown, result.status)
    assert summary["key_changes"][0]["title"] == "가격 관련 보도 수치 생략. 가격 확인 필요."
