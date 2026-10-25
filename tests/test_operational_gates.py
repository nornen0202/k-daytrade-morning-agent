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
