import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from daytrade_agent.calendar.trading_calendar import trading_status
from daytrade_agent.collectors.base import response_json
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.llm.report_writer import build_summary, verified_facts_markdown
from daytrade_agent.normalizers.freshness import temporal_status
from daytrade_agent.render.site_builder import _publication_gate
from tests.test_report_verifier import _context


@pytest.mark.parametrize("text", [
    "- 현재가 10,000원 source_id: src_policy_001",
    "- 현재가 10,000원 data_key: price_does_not_exist",
    "- 현재가 10,000원 data_key: price_005930_20260427_0835",
    "- 지원 규모 5억원 source_id: src_policy_001",
    "- 데이터 부족이지만 현재가 9,999원 투자 조언이 아닙니다.",
    "지원 규모 5억원",
    "# 현재가 10,000원",
    "# 2026-04-27 현재가 10,000원",
    "- 정책 확인 source_id: src_fabricated",
])
def test_claims_cannot_bypass_evidence(text):
    assert verify_report(_context(), text).status == "fail"


def test_verified_quote_has_value_unit_and_timestamp():
    context = _context()
    snapshot = context.price_snapshots[0]
    text = (
        f"- 현재가 {snapshot.last_price:,.0f}원 · {snapshot.as_of.isoformat()} "
        f"data_key: {snapshot.data_key}"
    )
    assert verify_report(context, text).status == "pass"
    assert verify_report(context, text.replace("원", "달러")).status == "fail"
    assert verify_report(context, text.replace(snapshot.as_of.isoformat(), "")).status == "fail"


def test_future_and_unzoned_time_are_unusable():
    stamp = datetime(2026, 10, 25, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    assert temporal_status(stamp + timedelta(seconds=1), stamp) == "insufficient"
    assert temporal_status(stamp.replace(tzinfo=None), stamp) == "insufficient"
    assert temporal_status(stamp - timedelta(hours=48), stamp) == "ok"
    assert temporal_status(stamp - timedelta(hours=48, seconds=1), stamp) == "stale"


@pytest.mark.parametrize("day", ["2026-05-01", "2026-06-03", "2026-07-17",
                                    "2026-08-17", "2026-09-24", "2026-10-05"])
def test_calendar_closures(day):
    assert trading_status(datetime.fromisoformat(day).date()) == "closed"


def test_calendar_unreviewed_year_is_unknown():
    assert trading_status(datetime(2027, 1, 4).date()) == "unknown"


def test_failure_gate_never_offers_candidates():
    report = {
        "report_date": "2026-10-23", "summary": {"candidates": [{"name": "sentinel"}]},
        "markdown": "sentinel", "verification": {"status": "fail", "errors": ["bad evidence"]},
    }
    _publication_gate(report, datetime.now(ZoneInfo("Asia/Seoul")))
    assert not report["valid"]
    assert not report["current"]


def test_utf8_json_ignores_incorrect_response_charset():
    class Response:
        content = json.dumps({"title": "정책 뉴스"}, ensure_ascii=False).encode()

        def json(self):
            raise AssertionError("must decode original bytes")

    assert response_json(Response())["title"] == "정책 뉴스"


def test_current_gate_expires_and_archives_remain_dated():
    context = _context()
    for source in context.sources:
        source.source_name = "Evidence fixture"
        source.source_url = "https://news.example.test/article"
    context.market_context["run_mode"] = "live"
    markdown = verified_facts_markdown(AppConfig.load(), context)
    result = verify_report(context, markdown)
    assert result.status != "fail", result.errors
    summary = build_summary(context, markdown, result.status)
    summary["run_mode"] = "live"
    report = {
        "report_date": context.report_date, "summary": summary, "markdown": markdown,
        "verification": result.model_dump(),
    }
    _publication_gate(report, context.generated_at + timedelta(minutes=5))
    assert report["valid"] and report["current"]
    _publication_gate(report, context.generated_at.replace(hour=9, minute=0))
    assert report["valid"] and not report["current"]
    _publication_gate(report, context.generated_at + timedelta(days=1))
    assert not report["current"]


def test_wrong_symbol_cannot_reuse_another_snapshot():
    context = _context()
    snapshot = context.price_snapshots[0]
    text = (
        f"- 000660 현재가 {snapshot.last_price:,.0f}원 · {snapshot.as_of.isoformat()} "
        f"data_key: {snapshot.data_key}"
    )
    assert verify_report(context, text).status == "fail"


@pytest.mark.parametrize("text", ["무조건매수", "무조건\u200b 매수", "상 한 가 확 정"])
def test_prohibited_spacing_cannot_bypass_verifier(text):
    assert verify_report(_context(), "- " + text + " source_id: src_policy_001").status == "fail"
