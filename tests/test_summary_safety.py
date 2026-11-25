from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from daytrade_agent import cli
from daytrade_agent.collectors.base import CollectorResult
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.llm.report_writer import build_summary, verified_facts_markdown
from daytrade_agent.render.site_builder import apply_publication_gate
from daytrade_agent.storage.public_safety import public_artifact_issues
from tests.test_report_verifier import _context


def test_diagnostics_hide_values_and_arbitrary_keys(monkeypatch):
    secret = "fixture-custom-secret-sentinel"
    monkeypatch.setenv("QUOTE_PROVIDER_API_KEY", secret)
    summary = {
        secret: {"raw_response": {"untrusted_name": "source payload"}},
        "sources": [{"source_url": "https://news.example.test/brief?%74oken=short"}],
    }
    messages = {issue.message() for issue in public_artifact_issues("", summary)}
    assert messages == {
        "public_safety field=summary.* code=configured_credential",
        "public_safety field=summary.*.raw_response code=private_payload_field",
        "public_safety field=summary.sources[].source_url code=credential_url",
    }
    assert all(secret not in message and "source payload" not in message for message in messages)


def test_dangerous_context_is_blocked_before_writer(monkeypatch, tmp_path, capsys):
    batch = _context()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(tz)

    def reject(*args, **kwargs):
        raise AssertionError("unsafe context must never reach the writer")

    url_marker = "https://news.example.test/article?token=fixture-secret-sentinel"
    batch.sources[0].source_url = url_marker
    monkeypatch.setattr(cli, "datetime", Clock)
    monkeypatch.setattr(cli, "write_report_markdown", reject)
    monkeypatch.setattr(cli, "_collect_all", lambda *args, **kwargs: [
        CollectorResult(events=batch.events, sources=batch.sources),
    ])
    config = replace(AppConfig.load(), content_dir=tmp_path)
    assert cli.run_command(config, batch.report_date, dry_run=False) == 0
    assert cli.verify_command(config, batch.report_date) == 1
    report = cli.load_report(config.content_dir, batch.report_date)
    issue = "public_safety field=summary.sources[].source_url code=credential_url"
    assert issue in capsys.readouterr().out
    assert issue in report["verification"]["errors"]
    assert url_marker not in str(report) and report["summary"]["candidates"] == []


def test_public_gate_checks_stored_fields_without_rendering_blocked_values():
    context = _context()
    markdown = verified_facts_markdown(AppConfig.load(), context)
    verification = verify_report(context, markdown)
    summary = build_summary(context, markdown, verification.status)
    assert public_artifact_issues(
        "",
        {"sources": [{"source_url": "https://news.example.test/article/2026-1125-12345"}]},
    ) == []
    assert public_artifact_issues(
        "",
        {"sources": [{"source_url": "https://news.example.test/article/123-456-7890"}]},
    ) == []
    summary["sources"][0]["source_name"] = "문의 계좌 123-456-7890"
    report = {"report_date": context.report_date, "summary": summary, "markdown": markdown,
              "verification": verification.model_dump()}
    apply_publication_gate(report, context.generated_at)
    assert not report["valid"] and not report["current"] and report["sources"] == []
    assert report["verification"]["errors"] == [
        "public_safety field=summary.sources[].source_name code=account_like_identifier",
    ]


def test_single_noisy_external_event_is_isolated_without_blocking_report(monkeypatch, tmp_path):
    batch = _context()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(tz)

    noisy_source = batch.sources[0].model_copy(update={
        "source_id": "src_noisy_external",
        "source_url": "https://news.example.test/article/2026-1125-12345",
    })
    noisy_event = batch.events[0].model_copy(update={
        "event_id": "evt_noisy_external",
        "source_id": "src_noisy_external",
        "source_url": "https://news.example.test/article/2026-1125-12345",
        "summary": "증권가 무조건 매수 추천 문의 031-200-1234",
    })
    batch.sources[0].source_url = "https://news.example.test/article/2026-1125-99999"
    monkeypatch.setattr(cli, "datetime", Clock)
    monkeypatch.setenv("REPORT_LLM_PROVIDER", "template")
    monkeypatch.setattr(cli, "_collect_all", lambda *args, **kwargs: [
        CollectorResult(
            events=[*batch.events, noisy_event],
            sources=[*batch.sources, noisy_source],
            price_snapshots=batch.price_snapshots,
        ),
    ])
    config = replace(AppConfig.load(), content_dir=tmp_path)
    assert cli.run_command(config, batch.report_date, dry_run=False) == 0
    assert cli.verify_command(config, batch.report_date) == 0
    saved = cli.load_report(config.content_dir, batch.report_date)
    assert saved["summary"]["data_status"] == "partial"
    assert "031-200-1234" not in str(saved)
    assert "src_noisy_external" not in str(saved)


def test_evidence_errors_never_echo_untrusted_refs_or_symbols():
    key = "raw_candidate_and_private_value"
    result = verify_report(_context(), f"- 999999 주의 source_id: {key}")
    assert result.status == "fail"
    assert "unknown symbol mentioned" in result.errors
    assert "999999" not in str(result.errors) and key not in str(result.errors)
