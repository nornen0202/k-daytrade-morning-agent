from datetime import datetime
from zoneinfo import ZoneInfo

from daytrade_agent.collectors.mock import collect_mock
from daytrade_agent.config import AppConfig
from daytrade_agent.llm.report_verifier import verify_report
from daytrade_agent.llm.report_writer import build_summary, write_report_markdown
from daytrade_agent.normalizers.event_schema import ReportContext
from daytrade_agent.render.site_builder import build_site
from daytrade_agent.scoring.candidate_score import score_candidates
from daytrade_agent.storage.report_store import save_report


def test_site_builder_creates_expected_pages(tmp_path):
    config = AppConfig.load()
    config = AppConfig(
        **{
            **config.__dict__,
            "content_dir": tmp_path / "content" / "reports",
            "dist_dir": tmp_path / "dist",
        }
    )
    generated_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    result = collect_mock(config, "2026-04-27", generated_at)
    context = ReportContext(
        report_date="2026-04-27",
        generated_at=generated_at,
        data_status="ok",
        events=result.events,
        sources=result.sources,
        price_snapshots=result.price_snapshots,
        candidates=score_candidates(config, result.events, result.price_snapshots, generated_at),
        market_context=result.market_context,
    )
    markdown = write_report_markdown(config, context, dry_run=True)
    verification = verify_report(context, markdown)
    save_report(
        config.content_dir,
        "2026-04-27",
        markdown,
        build_summary(context, markdown, verification.status),
        verification,
    )

    build_site(config)

    assert (config.dist_dir / "index.html").exists()
    assert (config.dist_dir / "reports" / "index.html").exists()
    assert (config.dist_dir / "reports" / "2026-04-27" / "index.html").exists()
    assert (config.dist_dir / "assets" / "style.css").exists()

    index_html = (config.dist_dir / "index.html").read_text(encoding="utf-8")
    report_html = (config.dist_dir / "reports" / "2026-04-27" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "발행 현황" in index_html
    assert "오늘의 시장 분위기" not in index_html
    assert 'id="current-brief"' not in index_html
    assert 'href="/reports/' not in index_html
    assert 'href="/assets/' not in index_html
    assert "데이터 기준 시각" in report_html

    status_js = (config.dist_dir / "assets" / "status.js").read_text(encoding="utf-8")
    assert "Number.isFinite" in status_js


def test_site_builder_isolates_corrupt_report_and_handles_utc_timestamp(tmp_path):
    from datetime import UTC, timedelta

    from daytrade_agent.render.site_builder import apply_publication_gate

    config = AppConfig.load()
    config = AppConfig(
        **{
            **config.__dict__,
            "content_dir": tmp_path / "content" / "reports",
            "dist_dir": tmp_path / "dist",
        }
    )
    corrupt_dir = config.content_dir / "2026-04-28"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "summary.json").write_text("{corrupt", encoding="utf-8")
    (corrupt_dir / "verification.json").write_text('{"status": "pass"}', encoding="utf-8")
    (corrupt_dir / "report.md").write_text("# Broken", encoding="utf-8")

    generated_at = datetime(2026, 4, 27, 8, 45, tzinfo=ZoneInfo("Asia/Seoul"))
    result = collect_mock(config, "2026-04-27", generated_at)
    context = ReportContext(
        report_date="2026-04-27",
        generated_at=generated_at,
        data_status="ok",
        events=result.events,
        sources=result.sources,
        price_snapshots=result.price_snapshots,
        candidates=score_candidates(config, result.events, result.price_snapshots, generated_at),
        market_context=result.market_context,
    )
    for source in context.sources:
        source.source_name = "Evidence fixture"
        source.source_url = "https://news.example.test/article"
    markdown = write_report_markdown(config, context, dry_run=True)
    verification = verify_report(context, markdown)
    context.market_context.update(run_mode="live", market_status="open")
    summary = build_summary(context, markdown, verification.status)
    save_report(config.content_dir, "2026-04-27", markdown, summary, verification)

    build_site(config, now=generated_at.astimezone(UTC) + timedelta(minutes=5))
    assert (config.dist_dir / "reports" / "2026-04-28" / "index.html").exists()
    home = config.dist_dir / "index.html"
    assert 'data-report-date="2026-04-27" hidden' in home.read_text(encoding="utf-8")
    valid_report_html = (
        config.dist_dir / "reports" / "2026-04-27" / "index.html"
    ).read_text(encoding="utf-8")
    assert '<div class="snapshot-item"' in valid_report_html

    utc_summary = dict(summary)
    utc_summary["generated_at"] = generated_at.astimezone(UTC).isoformat()
    report = {
        "report_date": "2026-04-27",
        "summary": utc_summary,
        "markdown": markdown,
        "verification": verification.model_dump(),
    }
    apply_publication_gate(report, generated_at.astimezone(UTC) + timedelta(minutes=5))
    assert report["valid"] and report["current"]

    build_site(config, now=generated_at.replace(hour=9, minute=0))
    assert 'id="current-brief"' not in home.read_text(encoding="utf-8")
    assert "통합 관찰 후보 Top 3" not in home.read_text(encoding="utf-8")

    save_report(config.content_dir, "2026-04-27", markdown, summary,
                verification.model_copy(update={"status": "fail"}))
    build_site(config, now=generated_at + timedelta(minutes=5))
    failed_html = (config.dist_dir / "reports" / "2026-04-27" / "index.html").read_text(
        encoding="utf-8",
    )
    assert 'id="current-brief"' not in home.read_text(encoding="utf-8")
    assert "Samsung Electronics" not in failed_html
    assert "검증 실패 이유" in failed_html
