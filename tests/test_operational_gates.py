from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from daytrade_agent import cli
from daytrade_agent.collectors.base import CollectorResult
from daytrade_agent.config import AppConfig
from daytrade_agent.normalizers.event_schema import VerificationResult
from daytrade_agent.scoring.candidate_score import score_candidates
from daytrade_agent.storage.report_store import save_report
from tests.test_report_verifier import _context


def test_late_live_run_never_collects_or_generates_candidates(monkeypatch, tmp_path):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 26, 9, 5, tzinfo=ZoneInfo("Asia/Seoul"))

    monkeypatch.setattr(cli, "datetime", Clock)

    def reject(*args, **kwargs):
        raise AssertionError("late run must not collect or call an LLM")

    monkeypatch.setattr(cli, "_collect_all", reject)
    monkeypatch.setattr(cli, "write_report_markdown", reject)
    config = replace(AppConfig.load(), content_dir=tmp_path / "reports")
    assert cli.run_command(config, "2026-10-26", dry_run=False) == 0
    result = cli.load_report(config.content_dir, "2026-10-26")
    assert result["summary"]["market_context"]["market_status"] == "missed"
    assert result["summary"]["candidates"] == []
    assert result["verification"]["status"] != "fail"


def test_public_store_rejects_actual_configured_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("QUOTE_PROVIDER_API_KEY", "fixture-secret-for-public-boundary-test")
    with pytest.raises(ValueError, match="configured credential"):
        save_report(tmp_path, "2026-10-25", "fixture-secret-for-public-boundary-test",
                    {}, VerificationResult(status="pass"))
    assert not (tmp_path / "2026-10-25").exists()


def test_public_store_rejects_nested_raw_payload(tmp_path):
    with pytest.raises(ValueError, match="private payload"):
        save_report(tmp_path, "2026-10-25", "notice",
                    {"market_context": {"raw_response": {"unexpected": "payload"}}},
                    VerificationResult(status="pass"))


def test_market_context_does_not_copy_raw_provider_fields():
    result = CollectorResult(market_context={
        "account_number": "fixture-account",
        "kospi": {"value": 100, "raw_response": {"unexpected": "payload"}},
    })
    assert cli._merge_market_context([result]) == {}


def test_future_events_cannot_raise_candidate_rank():
    context = _context()
    for event in context.events:
        event.published_at = context.generated_at + timedelta(seconds=1)
    assert score_candidates(
        AppConfig.load(), context.events, context.price_snapshots, context.generated_at
    ) == []


def test_rejected_model_draft_is_not_reported_as_codex_output(monkeypatch, tmp_path):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))

    context = _context()
    monkeypatch.setattr(cli, "datetime", Clock)
    monkeypatch.setattr(cli, "_collect_all", lambda *args, **kwargs: [CollectorResult(
        events=context.events, sources=context.sources, price_snapshots=context.price_snapshots,
    )])

    def rejected_draft(config, context, **kwargs):
        context.market_context["writer_provider"] = "codex"
        context.market_context["writer_model"] = "gpt-6.1-sol"
        return "- unsupported quantity 12345"

    monkeypatch.setattr(cli, "write_report_markdown", rejected_draft)
    config = replace(AppConfig.load(), content_dir=tmp_path / "reports")
    assert cli.run_command(config, "2026-04-27", dry_run=False) == 0
    summary = cli.load_report(config.content_dir, "2026-04-27")["summary"]
    assert summary["metrics"]["writer_provider"] == "template"
    assert summary["metrics"]["writer_model"] is None
    assert summary["metrics"]["writer_fallback"] is True
    assert summary["market_context"]["rejected_writer_model"] == "gpt-6.1-sol"


def test_build_context_does_not_flag_deduplicated_events_as_rejected():
    context = _context()
    dup_event = context.events[0].model_copy(deep=True)
    result = CollectorResult(
        events=[*context.events, dup_event],
        sources=context.sources,
        price_snapshots=context.price_snapshots,
        market_context=context.market_context,
    )
    built = cli._build_context(AppConfig.load(), "2026-04-27", context.generated_at, [result])
    assert len(built.events) == len(context.events)
    assert not any("제외된 뉴스/공시" in item for item in built.missing_data)


def test_verify_command_fails_closed_when_summary_contains_unsafe_text(tmp_path):
    context = _context()
    config = replace(AppConfig.load(), content_dir=tmp_path / "reports")
    markdown = "- Samsung Electronics(005930) 관찰 우선순위 - source_id: src_policy_001"
    from daytrade_agent.llm.report_writer import build_summary

    summary = build_summary(context, markdown, "pass")
    summary["events"][0]["summary"] = "무조건 매수 추천 텍스트"
    save_report(
        config.content_dir,
        "2026-04-27",
        markdown,
        summary,
        VerificationResult(status="pass"),
    )

    assert cli.verify_command(config, "2026-04-27") == 1
    reloaded = cli.load_report(config.content_dir, "2026-04-27")
    assert reloaded["verification"]["status"] == "fail"
    assert reloaded["summary"]["candidates"] == []
    assert reloaded["summary"]["report_kind"] == "notice"
    assert "데이터 검증 실패 리포트" in reloaded["markdown"]


def test_verify_command_handles_malformed_summary_without_crashing(tmp_path):
    config = replace(AppConfig.load(), content_dir=tmp_path / "reports")
    save_report(
        config.content_dir,
        "2026-04-27",
        "# Broken",
        {"report_date": "2026-04-27", "generated_at": "not-a-timestamp"},
        VerificationResult(status="pass"),
    )
    assert cli.verify_command(config, "2026-04-27") == 1


def test_public_store_rejects_password_credential(monkeypatch, tmp_path):
    monkeypatch.setenv("SERVICE_PASSWORD", "fixture-password-value-1234")
    with pytest.raises(ValueError, match="configured credential"):
        save_report(
            tmp_path,
            "2026-10-25",
            "fixture-password-value-1234",
            {},
            VerificationResult(status="pass"),
        )
